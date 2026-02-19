-- ===========================================================================
-- Install orbit classification functions into css_utilities schema
-- ===========================================================================
--
-- Run as schema owner (postgres):
--   psql -h $PGHOST -U postgres mpc_sbn -f sql/install_classify_orbit.sql
--
-- After install, grant execute to readonly role:
--   GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA css_utilities TO claude_ro;
--
-- These functions use JPL/CNEOS dynamical boundaries to classify orbits
-- from cometary elements (q, e).  Validated against mpc_orbits Feb 2026:
-- zero discrepancies among 8,744 NEOs with orbit_type_int populated,
-- plus 32,371 recoverable NEOs in the NULL pool.
-- ===========================================================================

-- ---------------------------------------------------------------------------
-- classify_orbit: returns MPC orbit_type_int integer code
-- ---------------------------------------------------------------------------
-- Boundaries (JPL/CNEOS):
--   0  Atira (IEO):  a < 1.0, Q < 0.983 AU
--   1  Aten:         a < 1.0, Q >= 0.983 AU
--   2  Apollo:       a >= 1.0, q <= 1.017 AU
--   3  Amor:         a >= 1.0, 1.017 < q <= 1.3 AU
--   10 Mars-crossing: 1.3 < q < 1.666 AU
--
-- Derives a = q/(1-e) and Q = q(1+e)/(1-e) from cometary elements.
-- Returns NULL for non-elliptical orbits (e >= 1) or outer solar system.
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION css_utilities.classify_orbit(
    p_q double precision,
    p_e double precision,
    p_i double precision DEFAULT NULL
)
RETURNS integer
LANGUAGE sql IMMUTABLE PARALLEL SAFE
AS $$
    SELECT CASE
        WHEN p_q IS NULL OR p_e IS NULL OR p_e >= 1.0 THEN NULL

        WHEN p_q / (1.0 - p_e) < 1.0
             AND p_q * (1.0 + p_e) / (1.0 - p_e) < 0.983
            THEN 0   -- Atira (IEO)

        WHEN p_q / (1.0 - p_e) < 1.0
            THEN 1   -- Aten

        WHEN p_q <= 1.017
            THEN 2   -- Apollo

        WHEN p_q <= 1.3
            THEN 3   -- Amor

        WHEN p_q < 1.666
            THEN 10  -- Mars-crossing

        ELSE NULL
    END
$$;

COMMENT ON FUNCTION css_utilities.classify_orbit(double precision, double precision, double precision) IS
    'Classify orbit into MPC orbit_type_int from cometary elements (q, e). JPL/CNEOS boundaries: 0=Atira, 1=Aten, 2=Apollo, 3=Amor, 10=Mars-X.';


-- ---------------------------------------------------------------------------
-- classify_orbit_label: returns text label
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION css_utilities.classify_orbit_label(
    p_q double precision,
    p_e double precision,
    p_i double precision DEFAULT NULL
)
RETURNS text
LANGUAGE sql IMMUTABLE PARALLEL SAFE
AS $$
    SELECT CASE css_utilities.classify_orbit(p_q, p_e, p_i)
        WHEN 0  THEN 'Atira'
        WHEN 1  THEN 'Aten'
        WHEN 2  THEN 'Apollo'
        WHEN 3  THEN 'Amor'
        WHEN 10 THEN 'Mars-crossing'
        ELSE NULL
    END
$$;

COMMENT ON FUNCTION css_utilities.classify_orbit_label(double precision, double precision, double precision) IS
    'Classify orbit from cometary elements (q, e) and return text label.';


-- ---------------------------------------------------------------------------
-- Grant execute to readonly role
-- ---------------------------------------------------------------------------
GRANT EXECUTE ON FUNCTION css_utilities.classify_orbit(double precision, double precision, double precision) TO claude_ro;
GRANT EXECUTE ON FUNCTION css_utilities.classify_orbit_label(double precision, double precision, double precision) TO claude_ro;


-- ---------------------------------------------------------------------------
-- Verification queries (run after install)
-- ---------------------------------------------------------------------------

-- Quick sanity check:
SELECT css_utilities.classify_orbit_label(0.502, 0.322)  AS expect_atira,
       css_utilities.classify_orbit_label(0.464, 0.450)  AS expect_aten,
       css_utilities.classify_orbit_label(1.017, 0.651)  AS expect_apollo,
       css_utilities.classify_orbit_label(1.018, 0.491)  AS expect_amor,
       css_utilities.classify_orbit_label(0.949, 0.026)  AS expect_aten_borderline;

-- Full validation against mpc_orbits (should return 0 rows):
-- SELECT unpacked_primary_provisional_designation, orbit_type_int,
--        css_utilities.classify_orbit(q, e) AS computed,
--        q, e, q/(1-e) AS a, q*(1+e)/(1-e) AS Q
-- FROM mpc_orbits
-- WHERE orbit_type_int IN (0, 1, 2, 3)
--   AND e < 1.0 AND q IS NOT NULL
--   AND orbit_type_int != css_utilities.classify_orbit(q, e);
