-- ==============================================================================
-- NEO DISCOVERY TRACKLET STATISTICS
-- ==============================================================================
-- Project: CSS_SBN_derived
-- Authors: Rob Seaman (Catalina Sky Survey) / Claude (Anthropic)
-- Created: 2026-01-08
-- Updated: 2026-02-08
--
-- Computes discovery tracklet statistics for Near-Earth Objects (NEOs)
-- sourced directly from the MPC/SBN PostgreSQL database.  Includes both
-- near-Earth asteroids (Atira, Aten, Apollo, Amor) and near-Earth comets.
--
-- NEO SELECTION (from mpc_orbits):
--   q < 1.32 AU  OR  orbit_type_int IN (0, 1, 2, 3, 20)
--   Orbit types: 0=Atira, 1=Aten, 2=Apollo, 3=Amor, 20=dual-nature
--   The q threshold slightly exceeds the IAU definition (q < 1.3 AU) to
--   retain objects near the boundary whose orbits may shift on refinement.
--
-- USAGE:
--   psql -h host -d mpc_sbn -f sql/discovery_tracklets.sql --csv -o output.csv
--
-- OUTPUT COLUMNS (12):
--   primary_designation                     Number (for numbered) or provisional designation
--   packed_primary_provisional_designation  Packed format (e.g., "I98P00A" or "K24A01A")
--   avg_mjd_discovery_tracklet              Mean MJD of discovery tracklet
--   avg_ra_deg                              Mean RA in decimal degrees
--   avg_dec_deg                             Mean Dec in decimal degrees
--   median_v_magnitude                      Median V-band magnitude (corrected)
--   nobs                                    Number of observations in discovery tracklet
--   span_hours                              Time span of discovery tracklet in hours
--   rate_deg_per_day                        Great-circle rate of motion (deg/day)
--   position_angle_deg                      Position angle of motion [0, 360) degrees
--   discovery_site_code                     MPC observatory code
--   discovery_site_name                     Observatory name from obscodes table
--
-- TRACKLET GROUPING:
--   Uses trkid (MPC-assigned, globally unique tracklet identifier) to group
--   discovery observations.  A ±12 hour time cap around the disc='*' observation
--   guards against non-standard trkid semantics (e.g., older X05 submissions
--   where a single trkid could span weeks; C51/WISE half-day arcs).
--   When trkid is NULL, falls back to the single disc='*' observation.
--
-- KNOWN LIMITATIONS:
--   - NEOs without any disc='*' observation in obs_sbn cannot be matched
--     (as of 2026-02-07: 2009 US19 and 2024 TZ7; reported to MPC)
--   - NEOs without a published orbit in mpc_orbits cannot be selected
--     (as of 2026-02-08: 2020 GZ1; primary_objects has no NEO classification)
--   - A small number of older observations have NULL trkid; for these,
--     statistics are computed from the single disc='*' observation
-- ==============================================================================

-- Suppress command-tag messages (CREATE INDEX, DROP TABLE, COPY nnn, etc.)
-- so they don't contaminate CSV output
\set QUIET on

-- Partial index on disc='*' (not part of the MPC/SBN default index set).
-- The other columns used in joins (permid, provid, trkid) already have
-- MPC-provided indexes (obs_sbn_permid_idx, obs_sbn_provid_idx, etc.).
-- Wrapped in exception handler so readonly roles can run this script.
DO $$
BEGIN
    CREATE INDEX IF NOT EXISTS idx_obs_sbn_disc ON obs_sbn(disc) WHERE disc = '*';
EXCEPTION WHEN insufficient_privilege THEN
    RAISE NOTICE 'Index creation skipped (insufficient privileges)';
END
$$;

-- ==============================================================================
-- MAIN QUERY
-- ==============================================================================

WITH neo_list AS (
    -- NEOs from mpc_orbits: orbital element + classification filter
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
        ON ni.packed_primary_provisional_designation = mo.packed_primary_provisional_designation
    WHERE mo.q < 1.32 OR mo.orbit_type_int IN (0, 1, 2, 3, 20)
),

-- ==============================================================================
-- UNION-based discovery observation lookup
-- Each branch targets a single index for efficient execution:
--   Branch 1: Numbered asteroids via obs.permid  (idx_obs_sbn_permid)
--   Branch 2: Unnumbered asteroids via obs.provid (idx_obs_sbn_provid)
--   Branch 3: Numbered asteroids via obs.provid = num_provid (idx_obs_sbn_provid)
-- UNION ALL is used here; DISTINCT ON deduplicates afterward.
-- ==============================================================================
discovery_obs_all AS (
    -- Branch 1: Numbered asteroids matched by permid
    SELECT
        neo.unpacked_desig,
        neo.packed_desig,
        neo.is_numbered,
        neo.asteroid_number,
        neo.provisional_desig,
        neo.num_provid,
        obs.stn,
        obs.obsid,
        obs.trkid,
        obs.obstime
    FROM neo_list neo
    INNER JOIN obs_sbn obs ON obs.permid = neo.asteroid_number
    WHERE neo.is_numbered
      AND obs.disc = '*'

    UNION ALL

    -- Branch 2: Unnumbered asteroids matched by provid
    SELECT
        neo.unpacked_desig,
        neo.packed_desig,
        neo.is_numbered,
        neo.asteroid_number,
        neo.provisional_desig,
        neo.num_provid,
        obs.stn,
        obs.obsid,
        obs.trkid,
        obs.obstime
    FROM neo_list neo
    INNER JOIN obs_sbn obs ON obs.provid = neo.provisional_desig
    WHERE NOT neo.is_numbered
      AND obs.disc = '*'

    UNION ALL

    -- Branch 3: Numbered asteroids matched by num_provid via provid
    SELECT
        neo.unpacked_desig,
        neo.packed_desig,
        neo.is_numbered,
        neo.asteroid_number,
        neo.provisional_desig,
        neo.num_provid,
        obs.stn,
        obs.obsid,
        obs.trkid,
        obs.obstime
    FROM neo_list neo
    INNER JOIN obs_sbn obs ON obs.provid = neo.num_provid
    WHERE neo.num_provid IS NOT NULL
      AND obs.disc = '*'
),

discovery_info AS (
    -- Pick the earliest discovery observation per NEA
    -- DISTINCT ON deduplicates across the UNION ALL branches
    SELECT DISTINCT ON (unpacked_desig)
        unpacked_desig,
        packed_desig,
        is_numbered,
        asteroid_number,
        provisional_desig,
        num_provid,
        stn as discovery_stn,
        obsid as discovery_obsid,
        NULLIF(trkid, '') as discovery_trkid,
        obstime as discovery_obstime
    FROM discovery_obs_all
    ORDER BY unpacked_desig, obstime
),

-- ==============================================================================
-- Tracklet observation lookup via trkid
-- trkid is globally unique, so a single join suffices (no UNION needed).
-- A ±12 hour window around the disc='*' observation guards against
-- non-standard trkid semantics (e.g., older X05 multi-week arcs, C51
-- half-day sessions).  When trkid is NULL, falls back to the single
-- disc='*' observation via obsid.
-- ==============================================================================
tracklet_obs_all AS (
    -- Primary path: trkid grouping with ±12 hour safety cap
    SELECT
        di.unpacked_desig,
        di.packed_desig,
        obs.obstime,
        obs.ra,
        obs.dec,
        obs.mag,
        obs.band
    FROM discovery_info di
    INNER JOIN obs_sbn obs ON obs.trkid = di.discovery_trkid
    WHERE di.discovery_trkid IS NOT NULL
      AND ABS(EXTRACT(EPOCH FROM (obs.obstime - di.discovery_obstime))) / 3600.0 <= 12.0

    UNION ALL

    -- Fallback: NULL trkid — return just the discovery observation itself
    SELECT
        di.unpacked_desig,
        di.packed_desig,
        obs.obstime,
        obs.ra,
        obs.dec,
        obs.mag,
        obs.band
    FROM discovery_info di
    INNER JOIN obs_sbn obs ON obs.obsid = di.discovery_obsid
    WHERE di.discovery_trkid IS NULL
),

discovery_tracklet_stats AS (
    -- Calculate statistics from all observations in the discovery tracklet
    SELECT
        unpacked_desig,
        packed_desig,

        -- Average MJD of discovery tracklet
        AVG(
            EXTRACT(EPOCH FROM obstime) / 86400.0 + 40587.0
        ) as avg_mjd,

        -- Average position
        AVG(ra) as avg_ra_deg,
        AVG(dec) as avg_dec_deg,

        -- Median V magnitude with band corrections
        -- Corrections from: https://minorplanetcenter.net/iau/info/BandConversion.txt
        PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY
            mag + CASE band
                WHEN 'V' THEN 0.0    -- V-band (reference)
                WHEN 'v' THEN 0.0
                WHEN 'B' THEN -0.8   -- Blue
                WHEN 'U' THEN -1.3   -- Ultraviolet
                WHEN 'R' THEN 0.4    -- Red
                WHEN 'I' THEN 0.8    -- Infrared
                WHEN 'g' THEN -0.35  -- SDSS green
                WHEN 'r' THEN 0.14   -- SDSS red
                WHEN 'i' THEN 0.32   -- SDSS infrared
                WHEN 'z' THEN 0.26   -- SDSS z
                WHEN 'y' THEN 0.32   -- SDSS y
                WHEN 'u' THEN 2.5    -- SDSS ultraviolet
                WHEN 'w' THEN -0.13  -- ATLAS white
                WHEN 'c' THEN -0.05  -- ATLAS cyan
                WHEN 'o' THEN 0.33   -- ATLAS orange
                WHEN 'G' THEN 0.28   -- Gaia
                WHEN 'J' THEN 1.2    -- 2MASS J
                WHEN 'H' THEN 1.4    -- 2MASS H
                WHEN 'K' THEN 1.7    -- 2MASS K
                WHEN 'C' THEN 0.4    -- Clear/unfiltered
                WHEN 'W' THEN 0.4    -- Wide
                WHEN 'L' THEN 0.2
                WHEN 'Y' THEN 0.7
                WHEN '' THEN -0.8    -- Blank = B-band default
                ELSE 0.0             -- Unknown = assume V
            END
        ) FILTER (WHERE mag IS NOT NULL) as median_v_mag,

        -- Observation count
        COUNT(*) as nobs,

        -- Time span of tracklet in hours
        EXTRACT(EPOCH FROM (MAX(obstime) - MIN(obstime))) / 3600.0 as span_hours,

        -- Time span in days (for rate computation)
        EXTRACT(EPOCH FROM (MAX(obstime) - MIN(obstime))) / 86400.0 as span_days,

        -- First and last observation coordinates for rate/PA computation
        (array_agg(ra  ORDER BY obstime ASC))[1] as first_ra,
        (array_agg(dec ORDER BY obstime ASC))[1] as first_dec,
        (array_agg(ra  ORDER BY obstime DESC))[1] as last_ra,
        (array_agg(dec ORDER BY obstime DESC))[1] as last_dec

    FROM tracklet_obs_all
    GROUP BY unpacked_desig, packed_desig
)

-- ==============================================================================
-- Final output with derived motion columns and observatory name
-- ==============================================================================
SELECT
    -- For numbered objects, output just the number; for unnumbered, output the provisional designation
    CASE
        WHEN di.is_numbered THEN di.asteroid_number
        ELSE dts.unpacked_desig
    END as primary_designation,
    dts.packed_desig as packed_primary_provisional_designation,
    ROUND(dts.avg_mjd::numeric, 6) as avg_mjd_discovery_tracklet,
    ROUND(dts.avg_ra_deg::numeric, 5) as avg_ra_deg,
    ROUND(dts.avg_dec_deg::numeric, 5) as avg_dec_deg,
    ROUND(dts.median_v_mag::numeric, 2) as median_v_magnitude,
    dts.nobs,
    ROUND(dts.span_hours::numeric, 4) as span_hours,

    -- Great-circle rate of motion (degrees per day) via Haversine formula
    -- Handles RA wraparound correctly (sin(dra/2)^2 is always positive)
    -- NULL when span_days = 0 (single observation)
    CASE WHEN dts.span_days > 0 THEN
        ROUND((
            2.0 * DEGREES(ASIN(SQRT(
                SIN(RADIANS(dts.last_dec - dts.first_dec) / 2.0) ^ 2
                + COS(RADIANS(dts.first_dec)) * COS(RADIANS(dts.last_dec))
                  * SIN(RADIANS(dts.last_ra - dts.first_ra) / 2.0) ^ 2
            ))) / dts.span_days
        )::numeric, 4)
    END as rate_deg_per_day,

    -- Position angle of motion (degrees, 0=N, 90=E, [0,360))
    -- Spherical bearing formula; handles RA wraparound via sin/cos of dra
    -- NULL when span_days = 0 (single observation)
    CASE WHEN dts.span_days > 0 THEN
        ROUND((
            (360.0 + DEGREES(ATAN2(
                SIN(RADIANS(dts.last_ra - dts.first_ra)) * COS(RADIANS(dts.last_dec)),
                COS(RADIANS(dts.first_dec)) * SIN(RADIANS(dts.last_dec))
                - SIN(RADIANS(dts.first_dec)) * COS(RADIANS(dts.last_dec))
                  * COS(RADIANS(dts.last_ra - dts.first_ra))
            )))::numeric % 360.0
        )::numeric, 2)
    END as position_angle_deg,

    di.discovery_stn as discovery_site_code,
    -- Clean observatory name: trim trailing spaces (dirty source data)
    -- and fix backslash-escaped apostrophes (PostgreSQL loading artifact)
    REPLACE(TRIM(oc.name), E'\\''', '''') as discovery_site_name

FROM discovery_info di
INNER JOIN discovery_tracklet_stats dts
    ON di.unpacked_desig = dts.unpacked_desig
LEFT JOIN obscodes oc
    ON oc.obscode = di.discovery_stn
ORDER BY
    -- Sort numbered objects numerically first, then unnumbered alphabetically
    di.is_numbered DESC,
    CASE WHEN di.is_numbered THEN LPAD(di.asteroid_number, 10, '0') ELSE dts.unpacked_desig END;
