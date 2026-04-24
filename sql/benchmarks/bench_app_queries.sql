-- bench_app_queries.sql
--
-- Reality-check harness for the three dashboard-driving queries
-- (LOAD_SQL, APPARITION_SQL, BOXSCORE_SQL). Reports wall-clock time,
-- row count, and a content-fingerprint md5 for each. Designed to run
-- identically on Gizmo (source=obs_sbn_neo) and Sibyl (source=obs_sbn);
-- compare the outputs for both speed and content drift.
--
-- Usage:
--   # Against Gizmo via its matview (dashboard's production path):
--   psql -d mpc_sbn \
--        -v source=obs_sbn_neo \
--        -f sql/benchmarks/bench_app_queries.sql \
--        > bench_gizmo_neo_$(date +%Y%m%d_%H%M).txt
--
--   # Against Sibyl without the matview (baseline, pre-rewrite path):
--   psql -h sibyl -U claude_ro -d mpc_sbn \
--        -v source=obs_sbn \
--        -f sql/benchmarks/bench_app_queries.sql \
--        > bench_sibyl_raw_$(date +%Y%m%d_%H%M).txt
--
--   # Against Gizmo without the matview (isolates hardware from matview):
--   psql -d mpc_sbn \
--        -v source=obs_sbn \
--        -f sql/benchmarks/bench_app_queries.sql \
--        > bench_gizmo_raw_$(date +%Y%m%d_%H%M).txt
--
--   diff <(grep '^FP' bench_sibyl_raw.txt) <(grep '^FP' bench_gizmo_neo.txt)
--
-- Fingerprint choice: md5 of ORDER BY-stable string_agg of designation
-- (present in all three queries). Content match → replicas + matview
-- agree up to replication drift. Mismatches by >~100 rows or a changed
-- hash at the same row count mean there's a real divergence to chase.
--
-- BOXSCORE is unaffected by source (doesn't touch obs_sbn) and acts as
-- a control — its timing + fingerprint should match cross-host modulo
-- the observable drift in mpc_orbits.

\set ON_ERROR_STOP on
\timing on
\pset format unaligned
\pset fieldsep ' | '
\pset footer off

\echo '# bench_app_queries — source=' :source ' ts=' `date -u +%Y-%m-%dT%H:%M:%SZ`

SELECT 'META',
       now()::text AS wall_clock,
       current_setting('server_version') AS pg_version,
       coalesce(inet_server_addr()::text, 'local') AS server,
       current_database() AS dbname,
       :'source' AS source_table;


-- ============================================================================
-- 1. LOAD_SQL — neo cache driver
-- ============================================================================
\echo
\echo '### LOAD_SQL (source=:source) ###'

CREATE TEMP TABLE _load_result AS
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
    INNER JOIN :source obs ON obs.permid = neo.asteroid_number
    WHERE neo.is_numbered AND obs.disc = '*'
    UNION ALL
    SELECT neo.unpacked_desig, obs.stn, obs.obsid, obs.trkid, obs.obstime
    FROM neo_list neo
    INNER JOIN :source obs ON obs.provid = neo.provisional_desig
    WHERE NOT neo.is_numbered AND obs.disc = '*'
    UNION ALL
    SELECT neo.unpacked_desig, obs.stn, obs.obsid, obs.trkid, obs.obstime
    FROM neo_list neo
    INNER JOIN :source obs ON obs.provid = neo.num_provid
    WHERE neo.num_provid IS NOT NULL AND obs.disc = '*'
)
SELECT DISTINCT ON (unpacked_desig) unpacked_desig AS designation, stn, obstime
FROM discovery_obs_all
ORDER BY unpacked_desig, obstime;

SELECT 'FP', 'LOAD_SQL',
       count(*) AS nrows,
       md5(string_agg(designation, '|' ORDER BY designation)) AS content_hash,
       min(obstime)::text AS min_obstime,
       max(obstime)::text AS max_obstime
FROM _load_result;

DROP TABLE _load_result;


-- ============================================================================
-- 2. APPARITION_SQL — station-level observations within +/- 200 days
-- ============================================================================
\echo
\echo '### APPARITION_SQL (source=:source) ###'

CREATE TEMP TABLE _apparition_result AS
WITH neo_list AS MATERIALIZED (
    SELECT
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
    SELECT neo.unpacked_desig, obs.stn, obs.obstime
    FROM neo_list neo
    INNER JOIN :source obs ON obs.permid = neo.asteroid_number
    WHERE neo.is_numbered AND obs.disc = '*'
    UNION ALL
    SELECT neo.unpacked_desig, obs.stn, obs.obstime
    FROM neo_list neo
    INNER JOIN :source obs ON obs.provid = neo.provisional_desig
    WHERE NOT neo.is_numbered AND obs.disc = '*'
    UNION ALL
    SELECT neo.unpacked_desig, obs.stn, obs.obstime
    FROM neo_list neo
    INNER JOIN :source obs ON obs.provid = neo.num_provid
    WHERE neo.num_provid IS NOT NULL AND obs.disc = '*'
),
discovery_info AS (
    SELECT DISTINCT ON (unpacked_desig)
        unpacked_desig, stn, obstime
    FROM discovery_obs_all
    ORDER BY unpacked_desig, obstime
),
neo_discovery AS MATERIALIZED (
    SELECT
        di.unpacked_desig AS designation,
        di.obstime AS disc_obstime,
        neo.asteroid_number,
        COALESCE(neo.provisional_desig, neo.num_provid) AS provid_key
    FROM discovery_info di
    JOIN neo_list neo ON neo.unpacked_desig = di.unpacked_desig
)
SELECT nd.designation, o.station_code, nd.disc_obstime,
       o.first_obs, o.first_post_disc
FROM neo_discovery nd
CROSS JOIN LATERAL (
    SELECT stn AS station_code,
           MIN(obstime) AS first_obs,
           MIN(CASE WHEN obstime >= nd.disc_obstime
                    THEN obstime END) AS first_post_disc
    FROM :source
    WHERE (permid = nd.asteroid_number OR provid = nd.provid_key)
      AND obstime BETWEEN nd.disc_obstime - INTERVAL '200 days'
                    AND nd.disc_obstime + INTERVAL '200 days'
    GROUP BY stn
) o;

SELECT 'FP', 'APPARITION_SQL',
       count(*) AS nrows,
       md5(string_agg(designation || '|' || station_code, ',' ORDER BY designation, station_code))
           AS content_hash,
       min(disc_obstime)::text AS min_disc_obstime,
       max(disc_obstime)::text AS max_disc_obstime
FROM _apparition_result;

DROP TABLE _apparition_result;


-- ============================================================================
-- 3. BOXSCORE_SQL — object catalog (does not touch obs_sbn; a control)
-- ============================================================================
\echo
\echo '### BOXSCORE_SQL (control — does not touch :source) ###'

CREATE TEMP TABLE _boxscore_result AS
SELECT
    mo.unpacked_primary_provisional_designation AS provid,
    ni.permid AS permid,
    mo.orbit_type_int,
    mo.q::double precision,
    mo.e::double precision,
    mo.i::double precision,
    mo.h::double precision
FROM mpc_orbits mo
LEFT JOIN numbered_identifications ni
    ON ni.packed_primary_provisional_designation
     = mo.packed_primary_provisional_designation;

SELECT 'FP', 'BOXSCORE_SQL',
       count(*) AS nrows,
       md5(string_agg(provid, '|' ORDER BY provid)) AS content_hash,
       count(DISTINCT orbit_type_int) AS n_orbit_types,
       count(*) FILTER (WHERE permid IS NOT NULL) AS n_numbered
FROM _boxscore_result;

DROP TABLE _boxscore_result;

\echo
\echo '# end of bench_app_queries'
