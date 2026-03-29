-- ==============================================================================
-- STATION DISCOVERY PROFILE (Query A — fast, discovery-based columns only)
-- ==============================================================================
-- For every station with at least one disc='*' observation, compute:
--   1. Total all-class discoveries (distinct objects with disc='*')
--   2. NEO discoveries using q <= 1.30 definition
--   3. NEO discoveries using orbit_type_int IN (0,1,2,3) definition
--   4. Year of first and last NEO discovery (q <= 1.30)
--
-- Runs in ~3 minutes using the disc='*' partial index.
-- ==============================================================================

-- CTE 1: All discoveries (any class) per station
WITH all_disc AS (
    SELECT
        stn,
        COUNT(DISTINCT COALESCE(NULLIF(permid, ''), provid)) AS disc_all
    FROM obs_sbn
    WHERE disc = '*'
    GROUP BY stn
),

-- CTE 2: NEO list (q <= 1.30)
neo_q AS (
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

-- CTE 3: NEO list (orbit_type_int classes only)
neo_class AS (
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
    WHERE mo.orbit_type_int IN (0, 1, 2, 3)
),

-- CTE 4: Discovery observations for NEOs (q <= 1.30)
-- Standard 3-branch UNION
neo_q_disc AS (
    SELECT neo.unpacked_desig, obs.stn, obs.obstime
    FROM neo_q neo
    INNER JOIN obs_sbn obs ON obs.permid = neo.asteroid_number
    WHERE neo.is_numbered AND obs.disc = '*'
    UNION ALL
    SELECT neo.unpacked_desig, obs.stn, obs.obstime
    FROM neo_q neo
    INNER JOIN obs_sbn obs ON obs.provid = neo.provisional_desig
    WHERE NOT neo.is_numbered AND obs.disc = '*'
    UNION ALL
    SELECT neo.unpacked_desig, obs.stn, obs.obstime
    FROM neo_q neo
    INNER JOIN obs_sbn obs ON obs.provid = neo.num_provid
    WHERE neo.num_provid IS NOT NULL AND obs.disc = '*'
),

-- CTE 5: Deduplicate to one discovery per NEO (q <= 1.30)
neo_q_info AS (
    SELECT DISTINCT ON (unpacked_desig)
        unpacked_desig, stn, obstime
    FROM neo_q_disc
    ORDER BY unpacked_desig, obstime
),

-- CTE 6: Per-station NEO discovery counts (q <= 1.30)
neo_q_by_stn AS (
    SELECT
        stn,
        COUNT(*) AS disc_neo_q,
        MIN(EXTRACT(YEAR FROM obstime))::int AS first_neo_year,
        MAX(EXTRACT(YEAR FROM obstime))::int AS last_neo_year
    FROM neo_q_info
    GROUP BY stn
),

-- CTE 7: Discovery observations for NEOs (orbit class)
neo_class_disc AS (
    SELECT neo.unpacked_desig, obs.stn, obs.obstime
    FROM neo_class neo
    INNER JOIN obs_sbn obs ON obs.permid = neo.asteroid_number
    WHERE neo.is_numbered AND obs.disc = '*'
    UNION ALL
    SELECT neo.unpacked_desig, obs.stn, obs.obstime
    FROM neo_class neo
    INNER JOIN obs_sbn obs ON obs.provid = neo.provisional_desig
    WHERE NOT neo.is_numbered AND obs.disc = '*'
    UNION ALL
    SELECT neo.unpacked_desig, obs.stn, obs.obstime
    FROM neo_class neo
    INNER JOIN obs_sbn obs ON obs.provid = neo.num_provid
    WHERE neo.num_provid IS NOT NULL AND obs.disc = '*'
),

-- CTE 8: Deduplicate to one discovery per NEO (orbit class)
neo_class_info AS (
    SELECT DISTINCT ON (unpacked_desig)
        unpacked_desig, stn, obstime
    FROM neo_class_disc
    ORDER BY unpacked_desig, obstime
),

-- CTE 9: Per-station NEO discovery counts (orbit class)
neo_class_by_stn AS (
    SELECT
        stn,
        COUNT(*) AS disc_neo_class
    FROM neo_class_info
    GROUP BY stn
)

-- Final: join all per-station counts
SELECT
    COALESCE(a.stn, q.stn, c.stn) AS stn,
    a.disc_all,
    q.disc_neo_q,
    c.disc_neo_class,
    q.first_neo_year,
    q.last_neo_year
FROM all_disc a
FULL OUTER JOIN neo_q_by_stn q ON q.stn = a.stn
FULL OUTER JOIN neo_class_by_stn c ON c.stn = COALESCE(a.stn, q.stn)
ORDER BY q.disc_neo_q DESC NULLS LAST, a.disc_all DESC NULLS LAST;
