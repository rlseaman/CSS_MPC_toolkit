-- ==============================================================================
-- DAILY ORBIT NEWS — diff -> events (SKETCH / PROPOSAL)
-- ==============================================================================
-- Project: CSS_MPC_toolkit
-- Created: 2026-06-25
-- Design:  docs/2026-06-25_daily_orbit_news_design.md
--
-- Compares each watch-set object's two most recent snapshots and inserts one
-- row into css_orbit_watch.orbit_event per detected boundary crossing / revision.
-- Run nightly right after capture_snapshot.sql. Idempotent per event_date: it
-- deletes any events already stamped with the newer snapshot_date before
-- re-inserting, so a re-run is safe.
--
-- Element-change thresholds (tune on real output):
--   H_REVISION : |dH| >= 0.30 mag
--   ORBIT_SHIFT: |dq| >= 0.02 AU OR |da| >= 0.05 AU OR |de| >= 0.02
--
-- The newer/older snapshot pair is "the two latest snapshot_dates present",
-- not strictly yesterday/today, so a gap (pipeline skipped a night) still
-- diffs correctly.
-- ==============================================================================

-- The two most recent snapshot dates.
\set pair_cur '(SELECT MAX(snapshot_date) FROM css_orbit_watch.orbit_snapshot)'
\set pair_prev '(SELECT MAX(snapshot_date) FROM css_orbit_watch.orbit_snapshot WHERE snapshot_date < (SELECT MAX(snapshot_date) FROM css_orbit_watch.orbit_snapshot))'

WITH
cur  AS (SELECT * FROM css_orbit_watch.orbit_snapshot WHERE snapshot_date = :pair_cur),
prev AS (SELECT * FROM css_orbit_watch.orbit_snapshot WHERE snapshot_date = :pair_prev),
-- inner join: only objects present in BOTH snapshots can be diffed
j AS (
    SELECT c.snapshot_date AS event_date, p.snapshot_date AS prev_date,
           c.primary_desig, c.permid, c.disc_by,
           p.q AS pq, c.q AS cq, p.a AS pa, c.a AS ca, p.e AS pe, c.e AS ce,
           p.earth_moid AS pmoid, c.earth_moid AS cmoid,
           p.h AS ph, c.h AS ch,
           p.is_neo AS pneo, c.is_neo AS cneo,
           p.is_pha AS ppha, c.is_pha AS cpha,
           p.neo_subclass AS psub, c.neo_subclass AS csub
    FROM cur c JOIN prev p USING (primary_desig)
),
events AS (
    SELECT event_date, prev_date, primary_desig, permid, disc_by,
           'NEO_ENTER' AS event_type, pq, cq, pa, ca, pe, ce, pmoid, cmoid, ph, ch, psub, csub,
           format('q %s -> %s AU (entered NEO region)', round(pq::numeric,4), round(cq::numeric,4)) AS detail
    FROM j WHERE cneo AND NOT pneo
    UNION ALL
    SELECT event_date, prev_date, primary_desig, permid, disc_by,
           'NEO_EXIT', pq, cq, pa, ca, pe, ce, pmoid, cmoid, ph, ch, psub, csub,
           format('q %s -> %s AU (left NEO region)', round(pq::numeric,4), round(cq::numeric,4))
    FROM j WHERE pneo AND NOT cneo
    UNION ALL
    SELECT event_date, prev_date, primary_desig, permid, disc_by,
           'PHA_ENTER', pq, cq, pa, ca, pe, ce, pmoid, cmoid, ph, ch, psub, csub,
           format('Earth MOID %s -> %s AU, H %s (now PHA)', round(pmoid::numeric,4), round(cmoid::numeric,4), round(ch::numeric,1))
    FROM j WHERE cpha AND NOT ppha
    UNION ALL
    SELECT event_date, prev_date, primary_desig, permid, disc_by,
           'PHA_EXIT', pq, cq, pa, ca, pe, ce, pmoid, cmoid, ph, ch, psub, csub,
           format('Earth MOID %s -> %s AU (no longer PHA)', round(pmoid::numeric,4), round(cmoid::numeric,4))
    FROM j WHERE ppha AND NOT cpha
    UNION ALL
    SELECT event_date, prev_date, primary_desig, permid, disc_by,
           'SUBCLASS_CHANGE', pq, cq, pa, ca, pe, ce, pmoid, cmoid, ph, ch, psub, csub,
           format('%s -> %s', psub, csub)
    FROM j WHERE cneo AND pneo AND psub IS DISTINCT FROM csub
    UNION ALL
    SELECT event_date, prev_date, primary_desig, permid, disc_by,
           'H_REVISION', pq, cq, pa, ca, pe, ce, pmoid, cmoid, ph, ch, psub, csub,
           format('H %s -> %s', round(ph::numeric,2), round(ch::numeric,2))
    FROM j WHERE ph IS NOT NULL AND ch IS NOT NULL AND abs(ch - ph) >= 0.30
    UNION ALL
    SELECT event_date, prev_date, primary_desig, permid, disc_by,
           'ORBIT_SHIFT', pq, cq, pa, ca, pe, ce, pmoid, cmoid, ph, ch, psub, csub,
           format('dq=%s da=%s de=%s', round((cq-pq)::numeric,4), round((ca-pa)::numeric,4), round((ce-pe)::numeric,4))
    FROM j
    WHERE abs(cq - pq) >= 0.02
       OR abs(COALESCE(ca,0) - COALESCE(pa,0)) >= 0.05
       OR abs(ce - pe) >= 0.02
)
INSERT INTO css_orbit_watch.orbit_event (
    event_date, primary_desig, permid, disc_by, event_type, prev_date,
    prev_q, new_q, prev_a, new_a, prev_e, new_e,
    prev_moid, new_moid, prev_h, new_h, prev_subclass, new_subclass, detail
)
SELECT event_date, primary_desig, permid, disc_by, event_type, prev_date,
       pq, cq, pa, ca, pe, ce, pmoid, cmoid, ph, ch, psub, csub, detail
FROM events;

-- NOTE on idempotency: in production wrap the INSERT with a guard such as
--   DELETE FROM css_orbit_watch.orbit_event WHERE event_date = <cur snapshot>;
-- before re-inserting, so a nightly re-run does not duplicate. Omitted here to
-- keep the sketch a single readable statement.

-- Convenience: today's news, newest first (what the dashboard tab/card reads).
-- SELECT event_date, event_type, primary_desig, permid, disc_by, detail
-- FROM css_orbit_watch.orbit_event
-- WHERE event_date = (SELECT MAX(event_date) FROM css_orbit_watch.orbit_event)
-- ORDER BY event_type, primary_desig;
