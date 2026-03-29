-- ==============================================================================
-- NEO DISCOVERY COUNTS BY STATION AND YEAR
-- ==============================================================================
-- Replicates the MPC YearlyBreakdown page from the mpc_sbn database.
--
-- For each NEO, finds the discovery observation (disc='*'), then counts
-- discoveries per station per year with breakdowns by orbit class and size.
--
-- NEO selection: q <= 1.30 AU
--
-- Discovery matching uses the standard 3-branch UNION:
--   Branch 1: numbered objects via obs.permid
--   Branch 2: unnumbered objects via obs.provid
--   Branch 3: numbered objects via obs.provid = packed provisional
--
-- USAGE:
--   psql -h $PGHOST -U claude_ro mpc_sbn -f sql/yearly_breakdown.sql --csv
--
-- ==============================================================================

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
        mo.h::double precision AS h,
        mo.q::double precision AS q,
        mo.e::double precision AS e,
        mo.i::double precision AS i,
        mo.orbit_type_int
    FROM mpc_orbits mo
    LEFT JOIN numbered_identifications ni
        ON ni.packed_primary_provisional_designation
         = mo.packed_primary_provisional_designation
    WHERE mo.q <= 1.30
),

discovery_obs_all AS (
    -- Branch 1: numbered via obs.permid
    SELECT neo.unpacked_desig, obs.stn, obs.obstime
    FROM neo_list neo
    INNER JOIN obs_sbn obs ON obs.permid = neo.asteroid_number
    WHERE neo.is_numbered AND obs.disc = '*'

    UNION ALL

    -- Branch 2: unnumbered via obs.provid
    SELECT neo.unpacked_desig, obs.stn, obs.obstime
    FROM neo_list neo
    INNER JOIN obs_sbn obs ON obs.provid = neo.provisional_desig
    WHERE NOT neo.is_numbered AND obs.disc = '*'

    UNION ALL

    -- Branch 3: numbered via obs.provid = packed provisional
    SELECT neo.unpacked_desig, obs.stn, obs.obstime
    FROM neo_list neo
    INNER JOIN obs_sbn obs ON obs.provid = neo.num_provid
    WHERE neo.num_provid IS NOT NULL AND obs.disc = '*'
),

-- Deduplicate: one discovery per object (earliest disc='*' observation)
discovery_info AS (
    SELECT DISTINCT ON (unpacked_desig)
        unpacked_desig, stn, obstime
    FROM discovery_obs_all
    ORDER BY unpacked_desig, obstime
),

-- Join back to orbital elements for classification
discovery_with_orbit AS (
    SELECT
        di.unpacked_desig,
        di.stn,
        EXTRACT(YEAR FROM di.obstime)::int AS disc_year,
        neo.h,
        neo.q,
        neo.e,
        neo.i,
        neo.orbit_type_int,
        -- Derive semi-major axis for classification
        CASE WHEN neo.e < 1 THEN neo.q / (1.0 - neo.e) END AS a,
        -- Aphelion distance Q = a(1+e) = q(1+e)/(1-e)
        CASE WHEN neo.e < 1 THEN neo.q * (1.0 + neo.e) / (1.0 - neo.e) END AS cap_q
    FROM discovery_info di
    JOIN neo_list neo ON neo.unpacked_desig = di.unpacked_desig
)

SELECT
    stn,
    disc_year,
    COUNT(*) AS neos,
    -- Size breakdowns
    COUNT(*) FILTER (WHERE h < 17.75) AS neos_1km,
    COUNT(*) FILTER (WHERE h <= 22.0) AS neos_h22,
    -- Orbit class breakdowns (geometric, matching MPC definitions)
    -- Atira: a < 1.0 AND Q < 0.983
    COUNT(*) FILTER (WHERE a IS NOT NULL AND a < 1.0 AND cap_q < 0.983) AS n_atira,
    -- Aten: a < 1.0 AND Q >= 0.983
    COUNT(*) FILTER (WHERE a IS NOT NULL AND a < 1.0 AND cap_q >= 0.983) AS n_aten,
    -- Apollo: a >= 1.0 AND q < 1.017
    COUNT(*) FILTER (WHERE a IS NOT NULL AND a >= 1.0 AND q < 1.017) AS n_apollo,
    -- Amor: a >= 1.0 AND q >= 1.017 (AND q <= 1.3 by NEO definition)
    COUNT(*) FILTER (WHERE a IS NOT NULL AND a >= 1.0 AND q >= 1.017) AS n_amor,
    -- Unclassified (hyperbolic, parabolic, or missing elements)
    COUNT(*) FILTER (WHERE a IS NULL OR e >= 1) AS n_unclass
FROM discovery_with_orbit
GROUP BY stn, disc_year
ORDER BY disc_year DESC, neos DESC;
