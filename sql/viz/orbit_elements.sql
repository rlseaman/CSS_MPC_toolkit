-- ==============================================================================
-- ORBITAL ELEMENTS QUERY (parameterized reference)
-- ==============================================================================
-- Extracts orbital elements from mpc_orbits with optional filters.
-- This is the psql-runnable equivalent of lib/orbits.build_orbit_query().
--
-- NOTE: Only ~43% of mpc_orbits have the flat 'a' column populated
-- (Keplerian elements).  All rows have cometary elements (q, e, i, node,
-- argperi).  We derive a = q/(1-e) for elliptical orbits (e < 1) when
-- the flat column is NULL.
--
-- Usage:
--   psql -h $PGHOST -d mpc_sbn -v orbit_types="1,2,3,4" -f sql/viz/orbit_elements.sql
--
-- For all objects (no filter), comment out the WHERE clause.
-- ==============================================================================

SELECT
    packed_primary_provisional_designation AS packed_desig,
    unpacked_primary_provisional_designation AS unpacked_desig,
    orbit_type_int,
    q,
    e,
    i,
    node,
    argperi,
    -- Semi-major axis: use flat column if present, else derive from q/(1-e)
    COALESCE(a, CASE WHEN e < 1 THEN q / NULLIF(1.0 - e, 0) END) AS a,
    h,
    earth_moid,
    epoch_mjd,
    -- Aphelion distance
    CASE WHEN e < 1
         THEN COALESCE(a, q / NULLIF(1.0 - e, 0)) * (1.0 + e)
    END AS aphelion_q,
    -- Orbital period (years, Kepler's third law)
    COALESCE(period,
        CASE WHEN e < 1 THEN POWER(q / NULLIF(1.0 - e, 0), 1.5) END
    ) AS period_yr,
    -- Tisserand parameter w.r.t. Jupiter
    5.2026 / NULLIF(COALESCE(a, CASE WHEN e < 1 THEN q / NULLIF(1.0 - e, 0) END), 0)
        + 2.0 * COS(RADIANS(i))
        * SQRT(GREATEST(
            COALESCE(a, CASE WHEN e < 1 THEN q / NULLIF(1.0 - e, 0) END)
            / 5.2026 * (1.0 - e * e), 0))
    AS tisserand_j
FROM mpc_orbits
-- WHERE orbit_type_int IN (0, 1, 2, 3)   -- NEAs only (0=Atira,1=Aten,2=Apollo,3=Amor)
-- AND h BETWEEN 18 AND 30                 -- faint objects
-- AND earth_moid < 0.05                   -- PHO candidates
ORDER BY packed_desig
-- LIMIT 10000
;
