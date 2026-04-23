-- obs_sbn_neo.sql
--
-- PROTOTYPE — NOT YET DEPLOYED. See
-- docs/obs_sbn_memory_optimization.md for evaluation context.
--
-- A materialized view containing every obs_sbn row whose object is an
-- NEO in mpc_orbits (q <= 1.30). Goal: give Gizmo (16 GB RAM) a cached
-- subset of the 535M-row obs_sbn it can actually hold in memory, so
-- that NEO-centric queries (LOAD_SQL, APPARITION_SQL, MPEC browser,
-- future live-DB apps) don't suffer the 11× slowdown observed when
-- they probe the full 55 GB of B-tree indexes on a 16 GB host.
--
-- Expected size (to be verified by running the CREATE): 20-35M rows,
-- 8-12 GB heap, 2-4 GB of indexes. Fits in Gizmo's page cache with
-- room for other data.
--
-- Lifecycle:
--   1. Build once on Gizmo (expected ~15 min, same order as a raw
--      LOAD_SQL on Gizmo — we pay it here so we don't pay it per
--      query afterwards).
--   2. `REFRESH MATERIALIZED VIEW CONCURRENTLY obs_sbn_neo` nightly
--      (alongside the MBP-driven cache refresh, or on its own
--      schedule). CONCURRENTLY requires a UNIQUE index (provided
--      below on `id`) and keeps readers unblocked during refresh.
--   3. Queries against obs_sbn_neo replace queries against obs_sbn
--      for NEO-scoped work. A rewritten LOAD_SQL is at the bottom of
--      this file as a reference.
--
-- Columns kept (everything any likely NEO-facing query needs — the
-- matview should be complete enough that a query can substitute
-- obs_sbn_neo for obs_sbn without touching any other table):
--
--   id              -- obs_sbn pkey, preserved for uniqueness in
--                     matview (needed for REFRESH CONCURRENTLY)
--   obsid           -- MPC-assigned observation ID (text)
--   permid          -- numbered-object permanent number (text)
--   provid          -- packed primary provisional designation (text)
--   trkid, trksub   -- tracklet identifiers
--   stn             -- observatory code
--   obstime         -- observation timestamp
--   disc            -- discovery flag ('*' on one observation per
--                     object)
--   ra, dec, mag, band   -- astrometry + photometry
--   created_at, updated_at -- replication-timestamp for incremental
--                            queries
--
-- Intentionally omitted (not needed by current NEO queries):
--   trkmpc (MPC tracklet identifier — 0 scans on Sibyl)
--   submission_block_id (low-value)
--   Anything JSONB — can join back to obs_sbn on obsid if needed.

-- ---------------------------------------------------------------------
-- 1. Build
-- ---------------------------------------------------------------------

CREATE MATERIALIZED VIEW IF NOT EXISTS obs_sbn_neo AS
WITH neo_provids AS (
    -- All NEO objects by their packed primary provisional designation.
    -- ~41K rows, fits in one hash table.
    SELECT DISTINCT mo.packed_primary_provisional_designation AS key
    FROM mpc_orbits mo
    WHERE mo.q <= 1.30
),
neo_permids AS (
    -- The subset of NEOs that are numbered; we need permid for
    -- obs_sbn.permid = neo.asteroid_number joins.
    SELECT DISTINCT ni.permid AS key
    FROM mpc_orbits mo
    JOIN numbered_identifications ni
      ON ni.packed_primary_provisional_designation
       = mo.packed_primary_provisional_designation
    WHERE mo.q <= 1.30
      AND ni.permid IS NOT NULL
)
SELECT obs.id,
       obs.obsid,
       obs.permid,
       obs.provid,
       obs.trkid,
       obs.trksub,
       obs.stn,
       obs.obstime,
       obs.disc,
       obs.ra,
       obs.dec,
       obs.mag,
       obs.band,
       obs.created_at,
       obs.updated_at
FROM obs_sbn obs
WHERE obs.provid IN (SELECT key FROM neo_provids)
   OR obs.permid IN (SELECT key FROM neo_permids);

-- No indexes exist yet at this point; the CREATE above produced a
-- plain heap. Build indexes separately — CREATE INDEX CONCURRENTLY
-- is not supported inside the CREATE MATERIALIZED VIEW statement.

-- ---------------------------------------------------------------------
-- 2. Indexes
-- ---------------------------------------------------------------------

-- UNIQUE index on `id` — required for REFRESH CONCURRENTLY.
-- Also happens to be the canonical row identity.
CREATE UNIQUE INDEX IF NOT EXISTS obs_sbn_neo_id_idx
    ON obs_sbn_neo (id);

-- Query-driving indexes. Small enough to stay resident.
CREATE INDEX IF NOT EXISTS obs_sbn_neo_permid_idx
    ON obs_sbn_neo (permid);
CREATE INDEX IF NOT EXISTS obs_sbn_neo_provid_idx
    ON obs_sbn_neo (provid);
CREATE INDEX IF NOT EXISTS obs_sbn_neo_trkid_idx
    ON obs_sbn_neo (trkid);
CREATE INDEX IF NOT EXISTS obs_sbn_neo_obstime_idx
    ON obs_sbn_neo (obstime);
CREATE INDEX IF NOT EXISTS obs_sbn_neo_disc_permid_idx
    ON obs_sbn_neo (permid) WHERE disc = '*';
CREATE INDEX IF NOT EXISTS obs_sbn_neo_disc_provid_idx
    ON obs_sbn_neo (provid) WHERE disc = '*';

-- Gather stats so the planner picks good plans from the start.
ANALYZE obs_sbn_neo;


-- ---------------------------------------------------------------------
-- 3. Refresh (for reference; run on a schedule)
-- ---------------------------------------------------------------------

-- REFRESH MATERIALIZED VIEW CONCURRENTLY obs_sbn_neo;
-- -- online, no read blocking, requires the UNIQUE index above


-- ---------------------------------------------------------------------
-- 4. Rewritten LOAD_SQL using obs_sbn_neo
-- ---------------------------------------------------------------------
--
-- Identical to app/discovery_stats.py::LOAD_SQL (lines 508-646) except
-- every reference to `obs_sbn` is replaced with `obs_sbn_neo`. The
-- join keys, CTE structure, and output columns are unchanged. Wrap
-- this in EXPLAIN ANALYZE and run it on both obs_sbn_neo and obs_sbn
-- (the latter being the current production path) to compare.
--
-- Uncomment to execute:

-- EXPLAIN (ANALYZE, BUFFERS, TIMING)
-- WITH neo_list AS (
--     SELECT
--         mo.packed_primary_provisional_designation AS packed_desig,
--         mo.unpacked_primary_provisional_designation AS unpacked_desig,
--         ni.permid IS NOT NULL AS is_numbered,
--         ni.permid AS asteroid_number,
--         CASE WHEN ni.permid IS NULL
--              THEN mo.unpacked_primary_provisional_designation
--         END AS provisional_desig,
--         ni.unpacked_primary_provisional_designation AS num_provid,
--         mo.h, mo.orbit_type_int,
--         mo.q, mo.e, mo.i
--     FROM mpc_orbits mo
--     LEFT JOIN numbered_identifications ni
--         ON ni.packed_primary_provisional_designation
--          = mo.packed_primary_provisional_designation
--     WHERE mo.q <= 1.30
-- ),
-- discovery_obs_all AS (
--     SELECT neo.unpacked_desig, obs.stn, obs.obsid, obs.trkid, obs.obstime
--     FROM neo_list neo
--     INNER JOIN obs_sbn_neo obs ON obs.permid = neo.asteroid_number
--     WHERE neo.is_numbered AND obs.disc = '*'
--     UNION ALL
--     SELECT neo.unpacked_desig, obs.stn, obs.obsid, obs.trkid, obs.obstime
--     FROM neo_list neo
--     INNER JOIN obs_sbn_neo obs ON obs.provid = neo.provisional_desig
--     WHERE NOT neo.is_numbered AND obs.disc = '*'
--     UNION ALL
--     SELECT neo.unpacked_desig, obs.stn, obs.obsid, obs.trkid, obs.obstime
--     FROM neo_list neo
--     INNER JOIN obs_sbn_neo obs ON obs.provid = neo.num_provid
--     WHERE neo.num_provid IS NOT NULL AND obs.disc = '*'
-- ),
-- discovery_info AS (
--     SELECT DISTINCT ON (unpacked_desig)
--         unpacked_desig, stn, obsid, NULLIF(trkid, '') AS trkid, obstime
--     FROM discovery_obs_all
--     ORDER BY unpacked_desig, obstime
-- ),
-- tracklet_obs_all AS (
--     SELECT di.unpacked_desig, obs.obstime, obs.ra, obs.dec, obs.mag, obs.band
--     FROM discovery_info di
--     INNER JOIN obs_sbn_neo obs ON obs.trkid = di.trkid
--     WHERE di.trkid IS NOT NULL
--       AND ABS(EXTRACT(EPOCH FROM (obs.obstime - di.obstime))) / 3600.0 <= 12.0
--     UNION ALL
--     SELECT di.unpacked_desig, obs.obstime, obs.ra, obs.dec, obs.mag, obs.band
--     FROM discovery_info di
--     INNER JOIN obs_sbn_neo obs ON obs.obsid = di.obsid
--     WHERE di.trkid IS NULL
-- )
-- SELECT count(*) AS rows_produced,
--        count(DISTINCT unpacked_desig) AS distinct_neos
-- FROM discovery_info
-- ;  -- or join back to neo_list + discovery_tracklet_stats like the real LOAD_SQL


-- ---------------------------------------------------------------------
-- 5. Teardown (for re-running / cleanup)
-- ---------------------------------------------------------------------
--
-- DROP MATERIALIZED VIEW IF EXISTS obs_sbn_neo;


-- ---------------------------------------------------------------------
-- 6. Evaluation checklist (before committing to deploy)
-- ---------------------------------------------------------------------
--
-- [ ] Run the CREATE MATERIALIZED VIEW above on Gizmo. Capture build
--     time with `\timing on`. Expected 10-20 min.
-- [ ] Verify row count is in the 15-40M range. If it's way outside that,
--     we've miscounted NEO obs and the memory-fit assumption is wrong.
-- [ ] Measure final size: `SELECT pg_size_pretty(pg_total_relation_size('obs_sbn_neo'))`
-- [ ] Run the rewritten LOAD_SQL under EXPLAIN ANALYZE on Gizmo.
--     Measure against the baseline (raw obs_sbn LOAD_SQL on Gizmo,
--     previously 935 s).
-- [ ] Run REFRESH MATERIALIZED VIEW CONCURRENTLY obs_sbn_neo.
--     Measure refresh time. This is the critical steady-state number.
-- [ ] Run the rewritten APPARITION_SQL against obs_sbn_neo (will
--     require editing that SQL analogously) — confirm it's bounded.
-- [ ] Decide: deploy permanently (add to refresh_cron.sh as a step
--     on Gizmo?), or discard if the wins are marginal.
