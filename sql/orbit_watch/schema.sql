-- ==============================================================================
-- DAILY ORBIT NEWS — schema (SKETCH / PROPOSAL)
-- ==============================================================================
-- Project: CSS_MPC_toolkit
-- Created: 2026-06-25
-- Design:  docs/2026-06-25_daily_orbit_news_design.md
--
-- Two tables in a new css_orbit_watch schema:
--   orbit_snapshot  per-(object, day) element state of the watch set
--                   (q <= 1.5 watch set; ~50 K rows/day; prune to a rolling
--                   window -- orbit_event is the durable record)
--   orbit_event     append-only log of boundary crossings / revisions; this is
--                   both the daily news feed and the longitudinal churn record
--
-- NOTE: requires a superuser (creates schema + tables). The nightly capture
-- (capture_snapshot.sql) and diff (daily_diff.sql) then run as the owner; the
-- read-only dashboard role only needs SELECT, granted at the bottom.
-- This is a sketch -- column set and thresholds are expected to change once
-- it has run against real output.
-- ==============================================================================

CREATE SCHEMA IF NOT EXISTS css_orbit_watch;

-- ------------------------------------------------------------------------------
-- Daily element snapshot of the watch set
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS css_orbit_watch.orbit_snapshot (
    snapshot_date   date        NOT NULL,
    primary_desig   text        NOT NULL,   -- unpacked primary provisional
    permid          text,                   -- numbered designation, if any
    disc_by         text,                   -- discovery obscode (from obs_summary)
    -- elements (top-level mpc_orbits, q reliable; a derived when KEP absent)
    q               double precision,
    e               double precision,
    i               double precision,
    a               double precision,       -- COALESCE(a, q/(1-e)) at capture
    earth_moid      double precision,
    h               double precision,
    u_param         text,
    nobs_total      integer,
    -- derived classification (element-based, NOT scattershot orbit_type_int)
    is_neo          boolean,                 -- q <= 1.3
    is_pha          boolean,                 -- earth_moid <= 0.05 AND h <= 22
    neo_subclass    text,                    -- Atira/Aten/Apollo/Amor or NULL
    src_updated_at  timestamptz,             -- mpc_orbits.updated_at at capture
    PRIMARY KEY (snapshot_date, primary_desig)
);

CREATE INDEX IF NOT EXISTS orbit_snapshot_desig_idx
    ON css_orbit_watch.orbit_snapshot (primary_desig, snapshot_date);

-- ------------------------------------------------------------------------------
-- Append-only event log (the "news feed" + longitudinal churn record)
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS css_orbit_watch.orbit_event (
    event_id        bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    event_date      date        NOT NULL,    -- diff date (= newer snapshot_date)
    primary_desig   text        NOT NULL,
    permid          text,
    disc_by         text,
    event_type      text        NOT NULL,    -- NEO_ENTER, PHA_EXIT, H_REVISION, ...
    prev_date       date,                    -- older snapshot_date compared
    -- before/after values (only the relevant ones populated per event_type)
    prev_q          double precision,  new_q          double precision,
    prev_a          double precision,  new_a          double precision,
    prev_e          double precision,  new_e          double precision,
    prev_moid       double precision,  new_moid       double precision,
    prev_h          double precision,  new_h          double precision,
    prev_subclass   text,              new_subclass   text,
    detail          text                     -- free-text summary for display
);

CREATE INDEX IF NOT EXISTS orbit_event_date_idx  ON css_orbit_watch.orbit_event (event_date);
CREATE INDEX IF NOT EXISTS orbit_event_desig_idx ON css_orbit_watch.orbit_event (primary_desig);
CREATE INDEX IF NOT EXISTS orbit_event_type_idx  ON css_orbit_watch.orbit_event (event_type, event_date);

-- Read-only dashboard access
GRANT USAGE ON SCHEMA css_orbit_watch TO claude_ro;
GRANT SELECT ON ALL TABLES IN SCHEMA css_orbit_watch TO claude_ro;
ALTER DEFAULT PRIVILEGES IN SCHEMA css_orbit_watch GRANT SELECT ON TABLES TO claude_ro;

-- ------------------------------------------------------------------------------
-- compute_events(p_cur, p_prev): diff one snapshot pair into orbit_event.
--   Idempotent for p_cur (clears that event_date first). Returns rows inserted.
--   Called by daily_diff.sql for the latest pair, and by rebuild_events.sql /
--   any backfill for arbitrary historical pairs (e.g. DOU-derived snapshots).
--
--   Boundary GAINS distinguish a genuine threshold crossing from a FIRST
--   DETERMINATION: if the prior snapshot lacked the deciding input (q NULL for
--   NEO; Earth MOID or H NULL for PHA) the object could not be classified
--   before, so the flip reflects new characterization (a fresh discovery
--   getting its first full orbit), NOT dynamical motion. These fire as
--   NEO_FIRST_DETERMINED / PHA_FIRST_DETERMINED rather than NEO_ENTER / PHA_ENTER.
-- ------------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION css_orbit_watch.compute_events(p_cur date, p_prev date)
RETURNS integer
LANGUAGE plpgsql AS $fn$
DECLARE n_inserted integer;
BEGIN
  DELETE FROM css_orbit_watch.orbit_event WHERE event_date = p_cur;

  WITH j AS (
    SELECT c.snapshot_date AS event_date, p.snapshot_date AS prev_date,
           c.primary_desig, c.permid, c.disc_by,
           p.q AS pq, c.q AS cq, p.a AS pa, c.a AS ca, p.e AS pe, c.e AS ce,
           p.earth_moid AS pmoid, c.earth_moid AS cmoid, p.h AS ph, c.h AS ch,
           p.is_neo AS pneo, c.is_neo AS cneo, p.is_pha AS ppha, c.is_pha AS cpha,
           p.neo_subclass AS psub, c.neo_subclass AS csub
    FROM css_orbit_watch.orbit_snapshot c
    JOIN css_orbit_watch.orbit_snapshot p ON p.primary_desig = c.primary_desig
    WHERE c.snapshot_date = p_cur AND p.snapshot_date = p_prev
  ),
  ev AS (
    -- NEO gained: first determination (prev q absent) vs genuine crossing
    SELECT event_date, prev_date, primary_desig, permid, disc_by,
           CASE WHEN pq IS NULL THEN 'NEO_FIRST_DETERMINED' ELSE 'NEO_ENTER' END AS event_type,
           pq,cq,pa,ca,pe,ce,pmoid,cmoid,ph,ch,psub,csub,
           CASE WHEN pq IS NULL
                THEN format('first NEO determination: q %s AU', round(cq::numeric,4))
                ELSE format('q %s -> %s AU (entered NEO region)', round(pq::numeric,4), round(cq::numeric,4)) END AS detail
    FROM j WHERE cneo IS TRUE AND pneo IS NOT TRUE
    UNION ALL
    SELECT event_date, prev_date, primary_desig, permid, disc_by, 'NEO_EXIT',
           pq,cq,pa,ca,pe,ce,pmoid,cmoid,ph,ch,psub,csub,
           format('q %s -> %s AU (left NEO region)', round(pq::numeric,4), round(cq::numeric,4))
    FROM j WHERE pneo IS TRUE AND cneo IS NOT TRUE AND pq IS NOT NULL
    UNION ALL
    -- PHA gained: first determination (prev MOID or H absent) vs genuine crossing
    SELECT event_date, prev_date, primary_desig, permid, disc_by,
           CASE WHEN pmoid IS NULL OR ph IS NULL THEN 'PHA_FIRST_DETERMINED' ELSE 'PHA_ENTER' END,
           pq,cq,pa,ca,pe,ce,pmoid,cmoid,ph,ch,psub,csub,
           CASE WHEN pmoid IS NULL OR ph IS NULL
                THEN format('first PHA determination: MOID %s AU, H %s', round(cmoid::numeric,4), round(ch::numeric,1))
                ELSE format('Earth MOID %s -> %s AU, H %s (now PHA)', round(pmoid::numeric,4), round(cmoid::numeric,4), round(ch::numeric,1)) END
    FROM j WHERE cpha AND NOT ppha
    UNION ALL
    SELECT event_date, prev_date, primary_desig, permid, disc_by, 'PHA_EXIT',
           pq,cq,pa,ca,pe,ce,pmoid,cmoid,ph,ch,psub,csub,
           format('Earth MOID %s -> %s AU (no longer PHA)', round(pmoid::numeric,4), round(cmoid::numeric,4))
    FROM j WHERE ppha AND NOT cpha
    UNION ALL
    SELECT event_date, prev_date, primary_desig, permid, disc_by, 'SUBCLASS_CHANGE',
           pq,cq,pa,ca,pe,ce,pmoid,cmoid,ph,ch,psub,csub,
           format('%s -> %s', psub, csub)
    FROM j WHERE cneo IS TRUE AND pneo IS TRUE AND psub IS DISTINCT FROM csub
    UNION ALL
    SELECT event_date, prev_date, primary_desig, permid, disc_by, 'H_REVISION',
           pq,cq,pa,ca,pe,ce,pmoid,cmoid,ph,ch,psub,csub,
           format('H %s -> %s', round(ph::numeric,2), round(ch::numeric,2))
    FROM j WHERE ph IS NOT NULL AND ch IS NOT NULL AND abs(ch - ph) >= 0.30
    UNION ALL
    SELECT event_date, prev_date, primary_desig, permid, disc_by, 'ORBIT_SHIFT',
           pq,cq,pa,ca,pe,ce,pmoid,cmoid,ph,ch,psub,csub,
           format('dq=%s da=%s de=%s', round((cq-pq)::numeric,4), round((ca-pa)::numeric,4), round((ce-pe)::numeric,4))
    FROM j
    WHERE pq IS NOT NULL AND cq IS NOT NULL
      AND (abs(cq - pq) >= 0.02 OR abs(COALESCE(ca,0)-COALESCE(pa,0)) >= 0.05 OR abs(ce - pe) >= 0.02)
  )
  INSERT INTO css_orbit_watch.orbit_event
    (event_date, primary_desig, permid, disc_by, event_type, prev_date,
     prev_q,new_q,prev_a,new_a,prev_e,new_e,prev_moid,new_moid,prev_h,new_h,prev_subclass,new_subclass,detail)
  SELECT event_date, primary_desig, permid, disc_by, event_type, prev_date,
         pq,cq,pa,ca,pe,ce,pmoid,cmoid,ph,ch,psub,csub,detail
  FROM ev;

  GET DIAGNOSTICS n_inserted = ROW_COUNT;
  RETURN n_inserted;
END
$fn$;

-- ------------------------------------------------------------------------------
-- v_epoch_migration: standard-epoch migration monitor (see
--   docs/2026-06-27_dou_orbit_logistics.md and sql/epoch_migration.sql).
--   One row per standard-epoch grid point (MJD multiples of 200), newest first,
--   with the current-epoch flag, the catalog/NEO migration shares, and the
--   lost-NEO signal (single-opposition % per bucket). Headline figures are
--   derivable as the is_current row's pct_all / pct_neo.
-- ------------------------------------------------------------------------------
CREATE OR REPLACE VIEW css_orbit_watch.v_epoch_migration AS
WITH cur AS (   -- current standard epoch = the grid epoch fresh fits get
  SELECT round(epoch_mjd)::int AS cur_epoch
  FROM mpc_orbits
  WHERE epoch_mjd IS NOT NULL AND updated_at >= CURRENT_DATE - 7
  GROUP BY 1 ORDER BY count(*) DESC LIMIT 1
),
g AS (
  SELECT round(epoch_mjd)::int AS epoch_mjd,
         count(*)                                                   AS objects,
         count(*) FILTER (WHERE q <= 1.3 AND e < 1)                 AS neos,
         count(*) FILTER (WHERE q <= 1.3 AND e < 1 AND nopp <= 1)   AS neo_single_opp
  FROM mpc_orbits
  WHERE epoch_mjd IS NOT NULL
  GROUP BY 1
)
SELECT g.epoch_mjd,
       (DATE '1858-11-17' + g.epoch_mjd)               AS epoch_date,
       (g.epoch_mjd = c.cur_epoch)                     AS is_current,
       (c.cur_epoch - g.epoch_mjd) / 200               AS epochs_behind,
       g.objects,
       round(100.0*g.objects/sum(g.objects) OVER (),1) AS pct_all,
       g.neos,
       round(100.0*g.neos/NULLIF(sum(g.neos) OVER (),0),1) AS pct_neo,
       CASE WHEN g.neos > 0 THEN round(100.0*g.neo_single_opp/g.neos,0) END AS neo_pct_single_opp
FROM g CROSS JOIN cur c
WHERE g.epoch_mjd % 200 = 0          -- standard-epoch grid only (drop off-grid singletons)
ORDER BY g.epoch_mjd DESC;

GRANT SELECT ON css_orbit_watch.v_epoch_migration TO claude_ro;
