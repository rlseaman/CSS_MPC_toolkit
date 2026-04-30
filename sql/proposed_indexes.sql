-- ===========================================================================
-- Proposed indexes for obs_sbn — driven by the CSS_examples script review
-- ===========================================================================
--
-- Empirical motivation:
--   - Most CSS workflow queries (getades.sql, getneos_80col_obs_sbn.sql,
--     and the dashboard's own LOAD_SQL) filter `deprecated IS NULL AND
--     status IN ('P','p')` — i.e., active and published rows only.
--   - The existing full btrees on permid / provid / (stn, obstime) cover
--     these same access shapes but include deprecated and unpublished
--     rows that the queries then filter out.
--
-- The partial-indexed variants below are smaller (1.5 GB instead of 3.6
-- GB for permid; ~similar gains for provid and the (stn, obstime)
-- composite) and let the planner skip the deprecated/status recheck for
-- the dominant query shape.
--
-- DO NOT run blindly on production. Each CREATE INDEX CONCURRENTLY on
-- obs_sbn (526 M rows, 280 GB) takes ~minutes-to-tens-of-minutes and
-- consumes substantial I/O. Schedule for a quiet maintenance window.
--
-- Sibyl-first if at all possible — its workload is the better calibration
-- target. Roll forward to Gizmo after measuring the impact there.
--
-- Each statement is independent; comment out the ones you don't want.
-- ===========================================================================

-- ---------------------------------------------------------------------------
-- 1. Active+published permid lookup (getades.sql primary path)
-- ---------------------------------------------------------------------------
-- The existing idx_obs_sbn_permid (3.6 GB) covers this column unconditionally.
-- A partial covering only the active+published rows is roughly 50-60 % of
-- that size and saves the recheck on every getades-style query.
--
-- Caveat: if the partial filter changes (e.g., status set widens), the
-- index becomes unusable. Document the filter expression alongside any
-- workflow that depends on it.

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_obs_sbn_permid_active
    ON obs_sbn (permid)
    WHERE deprecated IS NULL AND status IN ('P','p');


-- ---------------------------------------------------------------------------
-- 2. Active+published provid lookup
-- ---------------------------------------------------------------------------
-- Same shape, for the provisional-designation access path.

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_obs_sbn_provid_active
    ON obs_sbn (provid)
    WHERE deprecated IS NULL AND status IN ('P','p');


-- ---------------------------------------------------------------------------
-- 3. Active+published (stn, obstime) composite
-- ---------------------------------------------------------------------------
-- Sibling to the existing idx_obs_stn_time (4.5 GB). Per-station
-- date-range queries that also want the active+published filter — which
-- is most of them — get index seeks without recheck.

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_obs_stn_time_active
    ON obs_sbn (stn, obstime)
    WHERE deprecated IS NULL AND status IN ('P','p');


-- ---------------------------------------------------------------------------
-- 4. (Optional) prev_ref pattern lookup
-- ---------------------------------------------------------------------------
-- For "what discoveries from this site are recoverable as discovery
-- MPECs via prev_ref?" queries. Filter is sparse (most rows have NULL
-- prev_ref), so a partial index is small. Indexed as text_pattern_ops
-- so LIKE 'MPEC%' works.
--
-- Skip if no workflow currently queries by prev_ref — easy to add later.

-- CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_obs_sbn_prev_ref_mpec
--     ON obs_sbn (prev_ref text_pattern_ops)
--     WHERE prev_ref IS NOT NULL AND prev_ref LIKE 'MPEC%';


-- ===========================================================================
-- After installation, verify with:
--
--   SELECT indexname,
--          pg_size_pretty(pg_relation_size(quote_ident(indexname)::regclass)) AS size
--     FROM pg_indexes
--    WHERE tablename = 'obs_sbn'
--    ORDER BY indexname;
--
-- And benchmark with EXPLAIN (ANALYZE, BUFFERS) on a representative query
-- (e.g. getades.sql for an old numbered NEO).
-- ===========================================================================
