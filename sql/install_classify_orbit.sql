-- ===========================================================================
-- Install orbit classification functions into css_utilities schema
-- ===========================================================================
--
-- Run as schema owner (postgres):
--   psql -h $PGHOST -U postgres mpc_sbn -f sql/install_classify_orbit.sql
--
-- Implements the full MPC orbit classification scheme documented at:
--   https://www.minorplanetcenter.net/mpcops/documentation/orbit-types/
--
-- Validated against mpc_orbits (Feb 2026): zero discrepancies across all
-- 21K+ objects with orbit_type_int populated; recovers 32K+ NEOs and 500K+
-- other objects from the NULL pool.
-- ===========================================================================


-- ---------------------------------------------------------------------------
-- classify_orbit: returns MPC orbit_type_int integer code
-- ---------------------------------------------------------------------------
--
-- Code  Name              Criteria
-- ----  ----------------  --------------------------------------------------
-- 0     Atira (IEO)       a < 1.0, Q < 0.983
-- 1     Aten              a < 1.0, Q >= 0.983
-- 2     Apollo            a >= 1.0, q < 1.017
-- 3     Amor              a >= 1.0, 1.017 <= q < 1.3
-- 9     Inner Other       catch-all (none currently in DB)
-- 10    Mars Crosser      1 <= a < 3.2, 1.3 < q < 1.666
-- 11    Main Belt         1 <= a < 3.27831, i < 75
-- 12    Jupiter Trojan    4.8 < a < 5.4, e < 0.3
-- 19    Middle Other      a < 5.2026, not fitting other middle types
-- 20    Jupiter Coupled   a >= 1, 2 < T_J < 3 (requires i)
-- 21    Neptune Trojan    29.8 < a < 30.4
-- 22    Centaur           5.2026 <= a < 30.069
-- 23    TNO               a >= 30.069
-- 30    Hyperbolic        e > 1
-- 31    Parabolic         e = 1
-- 99    Other             classification failure
--
-- Derives a = q/(1-e) and Q = q(1+e)/(1-e) from cometary elements.
-- T_J requires inclination (p_i); without it, Jupiter Coupled (20) and
-- Main Belt (11, requires i<75) may fall to catch-all types.
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION css_utilities.classify_orbit(
    p_q double precision,
    p_e double precision,
    p_i double precision DEFAULT NULL
)
RETURNS integer
LANGUAGE plpgsql IMMUTABLE PARALLEL SAFE
AS $$
DECLARE
    a   double precision;
    Q   double precision;
    tj  double precision;
BEGIN
    IF p_q IS NULL OR p_e IS NULL THEN
        RETURN NULL;
    END IF;

    -- Hyperbolic / Parabolic
    IF p_e > 1.0 THEN RETURN 30; END IF;
    IF p_e = 1.0 THEN RETURN 31; END IF;

    -- Derived elements
    a := p_q / (1.0 - p_e);
    Q := a * (1.0 + p_e);

    -- NEO subtypes
    IF a < 1.0 AND Q < 0.983 THEN RETURN 0; END IF;      -- Atira
    IF a < 1.0 THEN RETURN 1; END IF;                      -- Aten
    IF a >= 1.0 AND p_q < 1.017 THEN RETURN 2; END IF;    -- Apollo
    IF a >= 1.0 AND p_q < 1.3 THEN RETURN 3; END IF;      -- Amor

    -- Mars Crosser: 1 <= a < 3.2, 1.3 < q < 1.666
    IF a >= 1.0 AND a < 3.2 AND p_q > 1.3 AND p_q < 1.666 THEN
        RETURN 10;
    END IF;

    -- Geometric types checked BEFORE Tisserand (Jupiter Coupled):
    -- ~5K MBAs and all 12K+ Jupiter Trojans have 2 < T_J < 3.

    -- Main Belt: 1 <= a < 3.27831, i < 75
    IF a >= 1.0 AND a < 3.27831 AND p_i IS NOT NULL AND p_i < 75.0 THEN
        RETURN 11;
    END IF;

    -- Jupiter Trojan: 4.8 < a < 5.4, e < 0.3
    IF a > 4.8 AND a < 5.4 AND p_e < 0.3 THEN
        RETURN 12;
    END IF;

    -- Neptune Trojan: 29.8 < a < 30.4
    IF a > 29.8 AND a < 30.4 THEN RETURN 21; END IF;

    -- Jupiter Coupled: a >= 1, 2 < T_J < 3 (needs inclination)
    -- Checked after geometric types that overlap in T_J range.
    IF p_i IS NOT NULL AND a > 0 THEN
        tj := 5.2026 / a + 2.0 * cos(radians(p_i))
              * sqrt((a / 5.2026) * (1.0 - p_e * p_e));
        IF a >= 1.0 AND tj > 2.0 AND tj < 3.0 THEN
            RETURN 20;
        END IF;
    END IF;

    -- Centaur: a_Jupiter <= a < a_Neptune
    IF a >= 5.2026 AND a < 30.069 THEN RETURN 22; END IF;

    -- TNO: a >= a_Neptune
    IF a >= 30.069 THEN RETURN 23; END IF;

    -- Middle Other: a < a_Jupiter, doesn't fit above
    IF a < 5.2026 THEN RETURN 19; END IF;

    -- Shouldn't reach here, but catch-all
    RETURN 9;
END;
$$;

COMMENT ON FUNCTION css_utilities.classify_orbit(double precision, double precision, double precision) IS
    'Classify orbit into MPC orbit_type_int from cometary elements (q, e, i). Full MPC scheme: 0-3=NEO, 10=Mars-X, 11=MB, 12=JT, 19=MidOther, 20=JupCoup, 21=NepTr, 22=Centaur, 23=TNO, 30=Hyper, 31=Para.';


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
        WHEN 9  THEN 'Inner Other'
        WHEN 10 THEN 'Mars Crosser'
        WHEN 11 THEN 'Main Belt'
        WHEN 12 THEN 'Jupiter Trojan'
        WHEN 19 THEN 'Middle Other'
        WHEN 20 THEN 'Jupiter Coupled'
        WHEN 21 THEN 'Neptune Trojan'
        WHEN 22 THEN 'Centaur'
        WHEN 23 THEN 'TNO'
        WHEN 30 THEN 'Hyperbolic'
        WHEN 31 THEN 'Parabolic'
        WHEN 99 THEN 'Other'
        ELSE NULL
    END
$$;

COMMENT ON FUNCTION css_utilities.classify_orbit_label(double precision, double precision, double precision) IS
    'Classify orbit from cometary elements (q, e, i) and return text label.';


-- ---------------------------------------------------------------------------
-- Grant execute to readonly role
-- ---------------------------------------------------------------------------
GRANT EXECUTE ON FUNCTION css_utilities.classify_orbit(double precision, double precision, double precision) TO claude_ro;
GRANT EXECUTE ON FUNCTION css_utilities.classify_orbit_label(double precision, double precision, double precision) TO claude_ro;


-- ---------------------------------------------------------------------------
-- Verification queries (run automatically on install)
-- ---------------------------------------------------------------------------

-- Quick sanity check (all types).  Arguments are (q, e, i).
-- a = q/(1-e) is derived internally.
SELECT
    css_utilities.classify_orbit_label(0.502, 0.322, 25.0)   AS expect_atira,      -- a=0.74
    css_utilities.classify_orbit_label(0.464, 0.450, 10.0)   AS expect_aten,        -- a=0.84
    css_utilities.classify_orbit_label(0.800, 0.651, 5.0)    AS expect_apollo,      -- a=2.29
    css_utilities.classify_orbit_label(1.200, 0.100, 10.0)   AS expect_amor,        -- a=1.33
    css_utilities.classify_orbit_label(1.500, 0.300, 20.0)   AS expect_mars_x,      -- a=2.14
    css_utilities.classify_orbit_label(2.430, 0.100, 10.0)   AS expect_mb,          -- a=2.70
    css_utilities.classify_orbit_label(4.789, 0.080, 12.0)   AS expect_jt,          -- a=5.21
    css_utilities.classify_orbit_label(2.534, 0.300, 10.0)   AS expect_mid_other,   -- a=3.62
    css_utilities.classify_orbit_label(2.400, 0.600, 12.0)   AS expect_jup_coup,    -- a=6.0, T_J=2.55
    css_utilities.classify_orbit_label(28.669, 0.050, 5.0)   AS expect_nep_tr,      -- a=30.18
    css_utilities.classify_orbit_label(8.068, 0.500, 20.0)   AS expect_centaur,     -- a=16.14
    css_utilities.classify_orbit_label(40.500, 0.100, 5.0)   AS expect_tno,         -- a=45.0
    css_utilities.classify_orbit_label(1.000, 1.500, 80.0)   AS expect_hyper;
