-- bench_load_sql_via_matview.sql
--
-- Benchmarks the dashboard's LOAD_SQL rewritten to use the obs_sbn_neo
-- materialized view instead of raw obs_sbn. Runs two variants:
--
--   Run 1: LOAD_SQL → discard rows, just measure wall time.
--   Run 2: EXPLAIN (ANALYZE, BUFFERS) LOAD_SQL — per-node timing and
--          cache hit / read buffer stats.
--
-- Compare to the baseline on Gizmo: the same LOAD_SQL against raw
-- obs_sbn took 934.6 s (measured 2026-04-23 in timed refresh).
--
-- Semantically identical to app/discovery_stats.py:508-646 except every
-- reference to obs_sbn is replaced with obs_sbn_neo. That matview
-- includes only NEO observations (q <= 1.30 + designation resolution
-- across numbered_identifications and current_identifications) so
-- the query reads a much smaller working set.

\timing on
\pset border 2

\echo
\echo '#############################################'
\echo '# Run 1: wall time (rows discarded)'
\echo '#############################################'
\o /dev/null
WITH neo_list AS (
    SELECT
        mo.packed_primary_provisional_designation AS packed_desig,
        mo.unpacked_primary_provisional_designation AS unpacked_desig,
        ni.permid IS NOT NULL AS is_numbered,
        ni.permid AS asteroid_number,
        CASE WHEN ni.permid IS NULL
             THEN mo.unpacked_primary_provisional_designation
        END AS provisional_desig,
        ni.unpacked_primary_provisional_designation AS num_provid,
        mo.h,
        mo.orbit_type_int,
        mo.q, mo.e, mo.i
    FROM mpc_orbits mo
    LEFT JOIN numbered_identifications ni
        ON ni.packed_primary_provisional_designation
         = mo.packed_primary_provisional_designation
    WHERE mo.q <= 1.30
),
discovery_obs_all AS (
    SELECT neo.unpacked_desig, obs.stn, obs.obsid, obs.trkid, obs.obstime
    FROM neo_list neo
    INNER JOIN obs_sbn_neo obs ON obs.permid = neo.asteroid_number
    WHERE neo.is_numbered AND obs.disc = '*'
    UNION ALL
    SELECT neo.unpacked_desig, obs.stn, obs.obsid, obs.trkid, obs.obstime
    FROM neo_list neo
    INNER JOIN obs_sbn_neo obs ON obs.provid = neo.provisional_desig
    WHERE NOT neo.is_numbered AND obs.disc = '*'
    UNION ALL
    SELECT neo.unpacked_desig, obs.stn, obs.obsid, obs.trkid, obs.obstime
    FROM neo_list neo
    INNER JOIN obs_sbn_neo obs ON obs.provid = neo.num_provid
    WHERE neo.num_provid IS NOT NULL AND obs.disc = '*'
),
discovery_info AS (
    SELECT DISTINCT ON (unpacked_desig)
        unpacked_desig, stn, obsid, NULLIF(trkid, '') AS trkid, obstime
    FROM discovery_obs_all
    ORDER BY unpacked_desig, obstime
),
tracklet_obs_all AS (
    SELECT di.unpacked_desig, obs.obstime, obs.ra, obs.dec, obs.mag, obs.band
    FROM discovery_info di
    INNER JOIN obs_sbn_neo obs ON obs.trkid = di.trkid
    WHERE di.trkid IS NOT NULL
      AND ABS(EXTRACT(EPOCH FROM (obs.obstime - di.obstime))) / 3600.0 <= 12.0
    UNION ALL
    SELECT di.unpacked_desig, obs.obstime, obs.ra, obs.dec, obs.mag, obs.band
    FROM discovery_info di
    INNER JOIN obs_sbn_neo obs ON obs.obsid = di.obsid
    WHERE di.trkid IS NULL
),
discovery_tracklet_stats AS (
    SELECT
        unpacked_desig,
        AVG(ra) AS avg_ra_deg,
        AVG(dec) AS avg_dec_deg,
        PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY
            mag + CASE band
                WHEN 'V' THEN 0.0  WHEN 'v' THEN 0.0  WHEN 'B' THEN -0.8
                WHEN 'U' THEN -1.3 WHEN 'R' THEN 0.4  WHEN 'I' THEN 0.8
                WHEN 'g' THEN -0.35 WHEN 'r' THEN 0.14 WHEN 'i' THEN 0.32
                WHEN 'z' THEN 0.26 WHEN 'y' THEN 0.32 WHEN 'u' THEN 2.5
                WHEN 'w' THEN -0.13 WHEN 'c' THEN -0.05 WHEN 'o' THEN 0.33
                WHEN 'G' THEN 0.28 WHEN 'J' THEN 1.2  WHEN 'H' THEN 1.4
                WHEN 'K' THEN 1.7  WHEN 'C' THEN 0.4  WHEN 'W' THEN 0.4
                WHEN 'L' THEN 0.2  WHEN 'Y' THEN 0.7  WHEN '' THEN -0.8
                ELSE 0.0
            END
        ) FILTER (WHERE mag IS NOT NULL) AS median_v_mag,
        COUNT(*) AS nobs,
        EXTRACT(EPOCH FROM (MAX(obstime) - MIN(obstime))) / 86400.0 AS span_days,
        (array_agg(ra  ORDER BY obstime ASC))[1]  AS first_ra,
        (array_agg(dec ORDER BY obstime ASC))[1]  AS first_dec,
        (array_agg(ra  ORDER BY obstime DESC))[1] AS last_ra,
        (array_agg(dec ORDER BY obstime DESC))[1] AS last_dec
    FROM tracklet_obs_all
    GROUP BY unpacked_desig
)
SELECT
    di.unpacked_desig AS designation,
    EXTRACT(YEAR FROM di.obstime)::int AS disc_year,
    EXTRACT(MONTH FROM di.obstime)::int AS disc_month,
    di.obstime::date AS disc_date,
    di.obstime AS disc_obstime,
    di.stn AS station_code,
    neo.h, neo.orbit_type_int, neo.q, neo.e, neo.i,
    dts.avg_ra_deg, dts.avg_dec_deg, dts.median_v_mag,
    dts.nobs AS tracklet_nobs
FROM discovery_info di
JOIN neo_list neo ON neo.unpacked_desig = di.unpacked_desig
LEFT JOIN discovery_tracklet_stats dts
    ON dts.unpacked_desig = di.unpacked_desig
LEFT JOIN obscodes oc ON oc.obscode = di.stn
ORDER BY di.obstime;
\o

\echo
\echo '#############################################'
\echo '# Run 2: row count + sanity check'
\echo '#############################################'
SELECT count(*)                       AS rows,
       count(DISTINCT designation)    AS distinct_neos
FROM (
    WITH neo_list AS (
        SELECT
            mo.packed_primary_provisional_designation AS packed_desig,
            mo.unpacked_primary_provisional_designation AS unpacked_desig,
            ni.permid IS NOT NULL AS is_numbered,
            ni.permid AS asteroid_number,
            CASE WHEN ni.permid IS NULL
                 THEN mo.unpacked_primary_provisional_designation
            END AS provisional_desig,
            ni.unpacked_primary_provisional_designation AS num_provid
        FROM mpc_orbits mo
        LEFT JOIN numbered_identifications ni
            ON ni.packed_primary_provisional_designation
             = mo.packed_primary_provisional_designation
        WHERE mo.q <= 1.30
    ),
    discovery_obs_all AS (
        SELECT neo.unpacked_desig, obs.obsid, NULLIF(obs.trkid,'') AS trkid, obs.obstime
        FROM neo_list neo
        INNER JOIN obs_sbn_neo obs ON obs.permid = neo.asteroid_number
        WHERE neo.is_numbered AND obs.disc = '*'
        UNION ALL
        SELECT neo.unpacked_desig, obs.obsid, NULLIF(obs.trkid,''), obs.obstime
        FROM neo_list neo
        INNER JOIN obs_sbn_neo obs ON obs.provid = neo.provisional_desig
        WHERE NOT neo.is_numbered AND obs.disc = '*'
        UNION ALL
        SELECT neo.unpacked_desig, obs.obsid, NULLIF(obs.trkid,''), obs.obstime
        FROM neo_list neo
        INNER JOIN obs_sbn_neo obs ON obs.provid = neo.num_provid
        WHERE neo.num_provid IS NOT NULL AND obs.disc = '*'
    )
    SELECT DISTINCT ON (unpacked_desig) unpacked_desig AS designation
    FROM discovery_obs_all
    ORDER BY unpacked_desig, obstime
) q;

\echo
\echo '#############################################'
\echo '# Run 3: EXPLAIN (ANALYZE, BUFFERS)'
\echo '#############################################'
EXPLAIN (ANALYZE, BUFFERS, TIMING, SETTINGS)
WITH neo_list AS (
    SELECT
        mo.packed_primary_provisional_designation AS packed_desig,
        mo.unpacked_primary_provisional_designation AS unpacked_desig,
        ni.permid IS NOT NULL AS is_numbered,
        ni.permid AS asteroid_number,
        CASE WHEN ni.permid IS NULL
             THEN mo.unpacked_primary_provisional_designation
        END AS provisional_desig,
        ni.unpacked_primary_provisional_designation AS num_provid,
        mo.h, mo.orbit_type_int, mo.q, mo.e, mo.i
    FROM mpc_orbits mo
    LEFT JOIN numbered_identifications ni
        ON ni.packed_primary_provisional_designation
         = mo.packed_primary_provisional_designation
    WHERE mo.q <= 1.30
),
discovery_obs_all AS (
    SELECT neo.unpacked_desig, obs.stn, obs.obsid, obs.trkid, obs.obstime
    FROM neo_list neo
    INNER JOIN obs_sbn_neo obs ON obs.permid = neo.asteroid_number
    WHERE neo.is_numbered AND obs.disc = '*'
    UNION ALL
    SELECT neo.unpacked_desig, obs.stn, obs.obsid, obs.trkid, obs.obstime
    FROM neo_list neo
    INNER JOIN obs_sbn_neo obs ON obs.provid = neo.provisional_desig
    WHERE NOT neo.is_numbered AND obs.disc = '*'
    UNION ALL
    SELECT neo.unpacked_desig, obs.stn, obs.obsid, obs.trkid, obs.obstime
    FROM neo_list neo
    INNER JOIN obs_sbn_neo obs ON obs.provid = neo.num_provid
    WHERE neo.num_provid IS NOT NULL AND obs.disc = '*'
),
discovery_info AS (
    SELECT DISTINCT ON (unpacked_desig)
        unpacked_desig, stn, obsid, NULLIF(trkid, '') AS trkid, obstime
    FROM discovery_obs_all
    ORDER BY unpacked_desig, obstime
),
tracklet_obs_all AS (
    SELECT di.unpacked_desig, obs.obstime, obs.ra, obs.dec, obs.mag, obs.band
    FROM discovery_info di
    INNER JOIN obs_sbn_neo obs ON obs.trkid = di.trkid
    WHERE di.trkid IS NOT NULL
      AND ABS(EXTRACT(EPOCH FROM (obs.obstime - di.obstime))) / 3600.0 <= 12.0
    UNION ALL
    SELECT di.unpacked_desig, obs.obstime, obs.ra, obs.dec, obs.mag, obs.band
    FROM discovery_info di
    INNER JOIN obs_sbn_neo obs ON obs.obsid = di.obsid
    WHERE di.trkid IS NULL
)
SELECT di.unpacked_desig, di.stn, count(*) AS tracklet_nobs
FROM discovery_info di
LEFT JOIN tracklet_obs_all t ON t.unpacked_desig = di.unpacked_desig
GROUP BY di.unpacked_desig, di.stn;

\echo
\echo '=== bench complete ==='
