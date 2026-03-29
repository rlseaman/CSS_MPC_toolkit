-- ==============================================================================
-- STATION OBSERVATION PROFILE (Query B — slow, full obs_sbn scan)
-- ==============================================================================
-- For every station in obs_sbn, compute:
--   1. Total observations
--   2. Total distinct tracklets (trkid)
--   3. Total unique objects (distinct COALESCE(NULLIF(permid,''), provid))
--   4. First and last observation timestamps
--
-- This is a full sequential scan of obs_sbn (~526M rows, ~240 GB).
-- Estimated runtime: 20-40 minutes.
--
-- USAGE:
--   Run via Python with timed_query for progress monitoring:
--     python scripts/run_station_obs_profile.py
-- ==============================================================================

-- Phase 1: COUNT and MIN/MAX only (no DISTINCT — fast)
SELECT
    stn,
    COUNT(*) AS n_obs,
    MIN(obstime) AS first_obs,
    MAX(obstime) AS last_obs
FROM obs_sbn
GROUP BY stn
ORDER BY n_obs DESC;
