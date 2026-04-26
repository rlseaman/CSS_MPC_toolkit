-- ===========================================================================
-- css_neo_consensus schema — multi-source NEO list reconciliation.
--
-- Tracks which institutions (MPC, CNEOS, NEOCC, NEOfixer, ...) recognize
-- which objects as Near-Earth Objects, keyed on the canonical MPC unpacked
-- primary provisional designation. v1 stores only membership facts
-- (designation × source × timestamps); per-source metadata (H, MOID,
-- orbit class, etc.) lives in mpc_sbn or in future per-source tables.
--
-- Idempotent install: safe to re-run.
--
-- Two design choices baked in:
--   * Canonical key = unpacked primary provisional designation. permid is
--     an auxiliary column. Numbering an object does NOT change its row.
--   * Comets are stored with is_comet=TRUE and excluded from
--     v_membership_wide by default. Asteroid-only is the v1 surface.
--
-- Run on Gizmo as a user with CREATE SCHEMA privilege:
--   psql -d mpc_sbn -f sql/consensus/install.sql
-- ===========================================================================

CREATE SCHEMA IF NOT EXISTS css_neo_consensus;


-- ---------------------------------------------------------------------------
-- source_membership — one row per (source, NEO).
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS css_neo_consensus.source_membership (
    source            TEXT        NOT NULL,
    primary_desig     TEXT        NOT NULL,
    packed_desig      TEXT,
        -- packed primary provisional; NULL only if desig_parsed=FALSE
    permid            TEXT,
        -- nullable; for numbered NEOs ("433", "99942", "780896").
        -- TEXT not INTEGER to match numbered_identifications.permid.
    raw_string        TEXT        NOT NULL,
        -- exactly what the source emitted, before any normalization
    desig_parsed      BOOLEAN     NOT NULL DEFAULT FALSE,
        -- TRUE iff mpc-designation accepted the source string AND we
        -- recovered the packed/unpacked forms successfully.
    orbit_in_mpc      BOOLEAN     NOT NULL DEFAULT FALSE,
        -- TRUE iff mpc_orbits has a row whose
        -- packed_primary_provisional_designation = packed_desig.
        -- Independent of desig_parsed: a designation can parse cleanly
        -- without yet appearing in mpc_orbits (e.g., NEOCC virtual
        -- impactor candidate MPC hasn't ingested).
    is_comet          BOOLEAN     NOT NULL DEFAULT FALSE,
        -- detected from designation form (C/, P/, fragments, etc.)
    first_seen        TIMESTAMPTZ NOT NULL,
    last_seen         TIMESTAMPTZ NOT NULL,
        -- updated on every refresh that re-finds this row.
    last_refreshed    TIMESTAMPTZ NOT NULL,
        -- timestamp of the run that last touched this row.
    PRIMARY KEY (source, primary_desig)
);

CREATE INDEX IF NOT EXISTS source_membership_primary_desig_idx
    ON css_neo_consensus.source_membership (primary_desig);
CREATE INDEX IF NOT EXISTS source_membership_packed_desig_idx
    ON css_neo_consensus.source_membership (packed_desig)
    WHERE packed_desig IS NOT NULL;
CREATE INDEX IF NOT EXISTS source_membership_permid_idx
    ON css_neo_consensus.source_membership (permid)
    WHERE permid IS NOT NULL;


-- ---------------------------------------------------------------------------
-- source_runs — refresh history.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS css_neo_consensus.source_runs (
    source         TEXT        NOT NULL,
    started_at     TIMESTAMPTZ NOT NULL,
    finished_at    TIMESTAMPTZ,
    status         TEXT        NOT NULL,
        -- 'running' | 'ok' | 'fail' | 'partial'
    n_rows         INTEGER,
        -- successful canonicalizations + upserts on this run
    n_unresolved   INTEGER,
        -- rows the source emitted that mpc-designation rejected, or
        -- whose numbered-id lookup failed
    error_text     TEXT,
    PRIMARY KEY (source, started_at)
);


-- ===========================================================================
-- Views — convenience layer for common queries.
-- ===========================================================================

-- Wide pivot. One row per asteroid recognized as an NEO by any source,
-- with one boolean per source. Comets filtered out by default; query
-- source_membership directly to include them.
--
-- DROP+CREATE rather than CREATE OR REPLACE because Postgres rejects
-- column-list reordering / additions in REPLACE; this lets new sources
-- be added cleanly at re-install time.
DROP VIEW IF EXISTS css_neo_consensus.v_membership_wide;
CREATE VIEW css_neo_consensus.v_membership_wide AS
SELECT primary_desig,
       MAX(packed_desig) AS packed_desig,
       MAX(permid)       AS permid,
       bool_or(source = 'mpc')        AS in_mpc,
       bool_or(source = 'cneos')      AS in_cneos,
       bool_or(source = 'neocc')      AS in_neocc,
       bool_or(source = 'neofixer')   AS in_neofixer,
       bool_or(source = 'mpc_orbits') AS in_mpc_orbits,
       bool_or(source = 'lowell')     AS in_lowell,
       MAX(last_refreshed) FILTER (WHERE source='mpc')        AS mpc_refreshed_at,
       MAX(last_refreshed) FILTER (WHERE source='cneos')      AS cneos_refreshed_at,
       MAX(last_refreshed) FILTER (WHERE source='neocc')      AS neocc_refreshed_at,
       MAX(last_refreshed) FILTER (WHERE source='neofixer')   AS neofixer_refreshed_at,
       MAX(last_refreshed) FILTER (WHERE source='mpc_orbits') AS mpc_orbits_refreshed_at,
       MAX(last_refreshed) FILTER (WHERE source='lowell')     AS lowell_refreshed_at
  FROM css_neo_consensus.source_membership
 WHERE NOT is_comet
 GROUP BY primary_desig;

COMMENT ON VIEW css_neo_consensus.v_membership_wide IS
    'One row per asteroid NEO recognized by at least one source. Comets filtered (is_comet=TRUE excluded). Drives boolean cross-source predicates: WHERE in_mpc AND in_cneos AND NOT in_neocc, etc.';


-- All known designations for any object in source_membership, expanded
-- via current_identifications (secondaries) and numbered_identifications
-- (permids). One designation per row.
CREATE OR REPLACE VIEW css_neo_consensus.v_member_designations AS
SELECT DISTINCT sm.primary_desig,
                sm.primary_desig AS designation,
                'primary'::text  AS kind
  FROM css_neo_consensus.source_membership sm
UNION
SELECT DISTINCT sm.primary_desig,
                ci.unpacked_secondary_provisional_designation,
                'secondary'
  FROM css_neo_consensus.source_membership sm
  JOIN public.current_identifications ci
    ON ci.packed_primary_provisional_designation = sm.packed_desig
 WHERE sm.packed_desig IS NOT NULL
   AND ci.unpacked_secondary_provisional_designation IS NOT NULL
UNION
SELECT DISTINCT sm.primary_desig,
                ni.permid,
                'permid'
  FROM css_neo_consensus.source_membership sm
  JOIN public.numbered_identifications ni
    ON ni.packed_primary_provisional_designation = sm.packed_desig
 WHERE sm.packed_desig IS NOT NULL
   AND ni.permid IS NOT NULL;

COMMENT ON VIEW css_neo_consensus.v_member_designations IS
    'Expand source_membership rows to every known alias. (primary_desig, designation, kind) where kind in {primary, secondary, permid}. Use case 6 driver: cross-source intersections that should include alias forms.';


-- Source health summary. One row per source, surfacing recency of
-- successful runs.
CREATE OR REPLACE VIEW css_neo_consensus.v_source_health AS
WITH last_per_source AS (
    SELECT source, MAX(started_at) AS last_run_started
      FROM css_neo_consensus.source_runs
     GROUP BY source
),
last_ok_per_source AS (
    SELECT source, MAX(started_at) AS last_ok_started
      FROM css_neo_consensus.source_runs
     WHERE status = 'ok'
     GROUP BY source
)
SELECT lp.source,
       lp.last_run_started,
       lo.last_ok_started,
       sr_last.status      AS last_status,
       sr_ok.finished_at   AS last_ok_finished,
       sr_ok.n_rows        AS last_ok_n_rows,
       sr_ok.n_unresolved  AS last_ok_n_unresolved,
       (now() - sr_ok.finished_at) AS time_since_last_ok
  FROM last_per_source lp
  LEFT JOIN last_ok_per_source lo ON lo.source = lp.source
  LEFT JOIN css_neo_consensus.source_runs sr_last
         ON sr_last.source = lp.source AND sr_last.started_at = lp.last_run_started
  LEFT JOIN css_neo_consensus.source_runs sr_ok
         ON sr_ok.source = lo.source AND sr_ok.started_at = lo.last_ok_started;

COMMENT ON VIEW css_neo_consensus.v_source_health IS
    'Per-source recency and last-run summary. Watch time_since_last_ok for staleness alerting.';


-- ===========================================================================
-- Grants — claude_ro reads everything; writes restricted to the schema owner.
-- ===========================================================================

GRANT USAGE ON SCHEMA css_neo_consensus TO claude_ro;
GRANT SELECT ON ALL TABLES IN SCHEMA css_neo_consensus TO claude_ro;
ALTER DEFAULT PRIVILEGES IN SCHEMA css_neo_consensus
    GRANT SELECT ON TABLES TO claude_ro;
