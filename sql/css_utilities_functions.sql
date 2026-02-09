-- ===========================================================================
-- CSS-Derived Utility Functions for PostgreSQL
-- ===========================================================================
--
-- Conversion functions for MPC 80-column observation format fields.
-- Designed to be installed in a local css_utilities schema on the
-- mpc_sbn replica, keeping them separate from replicated MPC tables.
--
-- Usage:
--   psql -h sibyl -U <owner> mpc_sbn -f css_utilities_functions.sql
--
-- Requires: CREATE SCHEMA and CREATE FUNCTION privileges.
--
-- Reference:
--   MPC 80-col format: https://minorplanetcenter.net/iau/info/ObsFormat.html
--   ADES standard: https://github.com/IAU-ADES/ADES-Master
--   Catalog codes: https://minorplanetcenter.net/iau/info/CatalogueCodes.html
-- ===========================================================================

CREATE SCHEMA IF NOT EXISTS css_utilities;


-- ---------------------------------------------------------------------------
-- MPC fractional-day date to ISO 8601 timestamp
-- ---------------------------------------------------------------------------
-- Input:  '2024 12 27.238073' (obs80 cols 16-32)
-- Output: '2024-12-27T05:42:49.5Z'
--
-- Precision of fractional seconds matches input precision:
--   5 decimal places on day -> integer seconds
--   6 -> 1 decimal place, 7 -> 2, 8 -> 3

CREATE OR REPLACE FUNCTION css_utilities.mpc_date_to_iso8601(date_str text)
RETURNS text
LANGUAGE plpgsql IMMUTABLE STRICT PARALLEL SAFE
AS $$
DECLARE
    parts    text[];
    yr       text;
    mo       text;
    day_frac text;
    dot_pos  int;
    day_int  int;
    frac     double precision;
    total_s  double precision;
    hh       int;
    mm       int;
    ss       double precision;
    n_dec    int;   -- input decimal places on day fraction
    s_dec    int;   -- output decimal places on seconds
    sec_str  text;
BEGIN
    parts := string_to_array(trim(date_str), ' ');
    IF array_length(parts, 1) != 3 THEN
        RETURN NULL;
    END IF;

    yr := parts[1];
    mo := lpad(parts[2], 2, '0');
    day_frac := parts[3];

    dot_pos := position('.' in day_frac);
    IF dot_pos = 0 THEN
        RETURN yr || '-' || mo || '-' || lpad(day_frac, 2, '0') || 'T00:00:00Z';
    END IF;

    day_int := substring(day_frac, 1, dot_pos - 1)::int;
    frac    := ('0' || substring(day_frac, dot_pos))::double precision;
    n_dec   := length(day_frac) - dot_pos;

    total_s := frac * 86400.0;
    hh := floor(total_s / 3600)::int;
    total_s := total_s - hh * 3600;
    mm := floor(total_s / 60)::int;
    ss := total_s - mm * 60;

    -- Map input day-fraction decimals to second decimals
    IF n_dec <= 5 THEN
        s_dec := 0;
    ELSE
        s_dec := n_dec - 5;
    END IF;

    IF s_dec = 0 THEN
        sec_str := lpad(round(ss)::int::text, 2, '0');
    ELSE
        sec_str := to_char(ss, 'FM00.' || repeat('0', s_dec));
    END IF;

    RETURN yr || '-' || mo || '-' || lpad(day_int::text, 2, '0')
        || 'T' || lpad(hh::text, 2, '0')
        || ':' || lpad(mm::text, 2, '0')
        || ':' || sec_str || 'Z';
END;
$$;

COMMENT ON FUNCTION css_utilities.mpc_date_to_iso8601(text) IS
    'Convert MPC obs80 date (cols 16-32) to ISO 8601 UTC timestamp';


-- ---------------------------------------------------------------------------
-- RA: sexagesimal HH MM SS.sss -> decimal degrees
-- ---------------------------------------------------------------------------
-- Input:  '08 56 40.968' (obs80 cols 33-44)
-- Output: 134.170700 (decimal degrees)

CREATE OR REPLACE FUNCTION css_utilities.ra_hms_to_deg(ra_str text)
RETURNS double precision
LANGUAGE plpgsql IMMUTABLE STRICT PARALLEL SAFE
AS $$
DECLARE
    parts text[];
    h     int;
    m     int;
    s     double precision;
BEGIN
    parts := string_to_array(trim(ra_str), ' ');
    IF array_length(parts, 1) != 3 THEN
        RETURN NULL;
    END IF;

    h := parts[1]::int;
    m := parts[2]::int;
    s := parts[3]::double precision;

    RETURN (h + m / 60.0 + s / 3600.0) * 15.0;
END;
$$;

COMMENT ON FUNCTION css_utilities.ra_hms_to_deg(text) IS
    'Convert RA from HH MM SS.sss to decimal degrees [0, 360)';


-- ---------------------------------------------------------------------------
-- Dec: sexagesimal sDD MM SS.ss -> decimal degrees
-- ---------------------------------------------------------------------------
-- Input:  '-00 16 11.93' (obs80 cols 45-56)
-- Output: -0.269981 (decimal degrees)

CREATE OR REPLACE FUNCTION css_utilities.dec_dms_to_deg(dec_str text)
RETURNS double precision
LANGUAGE plpgsql IMMUTABLE STRICT PARALLEL SAFE
AS $$
DECLARE
    trimmed text;
    sign    int := 1;
    parts   text[];
    d       int;
    m       int;
    s       double precision;
BEGIN
    trimmed := trim(dec_str);
    IF left(trimmed, 1) = '-' THEN
        sign := -1;
        trimmed := substring(trimmed from 2);
    ELSIF left(trimmed, 1) = '+' THEN
        trimmed := substring(trimmed from 2);
    END IF;

    parts := string_to_array(trim(trimmed), ' ');
    IF array_length(parts, 1) != 3 THEN
        RETURN NULL;
    END IF;

    d := parts[1]::int;
    m := parts[2]::int;
    s := parts[3]::double precision;

    RETURN sign * (d + m / 60.0 + s / 3600.0);
END;
$$;

COMMENT ON FUNCTION css_utilities.dec_dms_to_deg(text) IS
    'Convert Dec from sDD MM SS.ss to decimal degrees [-90, 90]';


-- ---------------------------------------------------------------------------
-- Catalog code: MPC single-char -> ADES astCat name
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION css_utilities.mpc_cat_to_ades(code char)
RETURNS text
LANGUAGE sql IMMUTABLE STRICT PARALLEL SAFE
AS $$
    SELECT CASE code
        WHEN 'a' THEN 'USNOA1'  WHEN 'b' THEN 'USNOSA1'
        WHEN 'c' THEN 'USNOA2'  WHEN 'd' THEN 'USNOSA2'
        WHEN 'e' THEN 'UCAC1'   WHEN 'f' THEN 'Tycho1'
        WHEN 'g' THEN 'Tycho2'  WHEN 'h' THEN 'GSC1.0'
        WHEN 'i' THEN 'GSC1.1'  WHEN 'j' THEN 'GSC1.2'
        WHEN 'k' THEN 'GSC2.2'  WHEN 'l' THEN 'ACT'
        WHEN 'm' THEN 'GSCACT'  WHEN 'n' THEN 'SDSSDR8'
        WHEN 'o' THEN 'USNOB1'  WHEN 'p' THEN 'PPM'
        WHEN 'q' THEN 'UCAC4'   WHEN 'r' THEN 'UCAC2'
        WHEN 's' THEN 'USNOB2'  WHEN 't' THEN 'PPMXL'
        WHEN 'u' THEN 'UCAC3'   WHEN 'v' THEN 'NOMAD'
        WHEN 'w' THEN 'CMC14'   WHEN 'x' THEN 'Hip2'
        WHEN 'y' THEN 'Hip'     WHEN 'z' THEN 'GSC'
        WHEN 'A' THEN 'AC'      WHEN 'B' THEN 'SAO1984'
        WHEN 'C' THEN 'SAO'     WHEN 'D' THEN 'AGK3'
        WHEN 'E' THEN 'FK4'     WHEN 'F' THEN 'ACRS'
        WHEN 'G' THEN 'LickGas' WHEN 'H' THEN 'Ida93'
        WHEN 'I' THEN 'Perth70' WHEN 'J' THEN 'COSMOS'
        WHEN 'K' THEN 'Yale'    WHEN 'L' THEN '2MASS'
        WHEN 'M' THEN 'GSC2.3'  WHEN 'N' THEN 'SDSSDR7'
        WHEN 'O' THEN 'SSTRC1'  WHEN 'P' THEN 'MPOSC3'
        WHEN 'Q' THEN 'CMC15'   WHEN 'R' THEN 'SSTRC4'
        WHEN 'S' THEN 'URAT1'   WHEN 'T' THEN 'URAT2'
        WHEN 'U' THEN 'Gaia1'   WHEN 'V' THEN 'Gaia2'
        WHEN 'W' THEN 'Gaia3'   WHEN 'X' THEN 'Gaia3E'
        WHEN 'Y' THEN 'UCAC5'   WHEN 'Z' THEN 'ATLAS2'
        WHEN '0' THEN 'IHW'     WHEN '1' THEN 'PS1DR1'
        WHEN '2' THEN 'PS1DR2'  WHEN '3' THEN 'GaiaInt'
        WHEN '4' THEN 'GZ'      WHEN '5' THEN 'UBAD'
        WHEN '6' THEN 'Gaia16'
        ELSE NULL
    END;
$$;

COMMENT ON FUNCTION css_utilities.mpc_cat_to_ades(char) IS
    'Map MPC single-char catalog code to ADES astCat name';


-- ---------------------------------------------------------------------------
-- Mode code: MPC col-15 -> ADES mode
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION css_utilities.mpc_mode_to_ades(code char)
RETURNS text
LANGUAGE sql IMMUTABLE STRICT PARALLEL SAFE
AS $$
    SELECT CASE code
        WHEN 'C' THEN 'CCD'  WHEN 'B' THEN 'CMO'
        WHEN 'V' THEN 'VID'  WHEN 'T' THEN 'TDI'
        WHEN 'P' THEN 'PHO'  WHEN 'E' THEN 'ENC'
        WHEN 'M' THEN 'MIC'  WHEN 'e' THEN 'PMT'
        WHEN 'O' THEN 'OCC'  WHEN 'A' THEN 'PHO'
        WHEN 'N' THEN 'PHO'  WHEN ' ' THEN 'PHO'
        WHEN 'S' THEN 'CCD'  WHEN 's' THEN 'CCD'
        WHEN 'X' THEN 'CCD'  WHEN 'x' THEN 'CCD'
        ELSE 'UNK'
    END;
$$;

COMMENT ON FUNCTION css_utilities.mpc_mode_to_ades(char) IS
    'Map MPC observation type code (col 15) to ADES mode';


-- ---------------------------------------------------------------------------
-- Band code: MPC single-char -> ADES band
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION css_utilities.mpc_band_to_ades(code char)
RETURNS text
LANGUAGE sql IMMUTABLE STRICT PARALLEL SAFE
AS $$
    SELECT CASE code
        WHEN 'B' THEN 'Bj'  WHEN 'V' THEN 'Vj'
        WHEN 'R' THEN 'Rc'  WHEN 'I' THEN 'Ic'
        WHEN 'J' THEN 'J'   WHEN 'H' THEN 'H'
        WHEN 'K' THEN 'K'   WHEN 'U' THEN 'Uj'
        WHEN 'W' THEN 'W'   WHEN 'G' THEN 'G'
        WHEN 'g' THEN 'Sg'  WHEN 'r' THEN 'Sr'
        WHEN 'i' THEN 'Si'  WHEN 'z' THEN 'Sz'
        WHEN 'w' THEN 'Pw'  WHEN 'y' THEN 'Py'
        WHEN 'o' THEN 'Ao'  WHEN 'c' THEN 'Ac'
        WHEN 'C' THEN 'CV'  WHEN 'L' THEN 'CV'
        WHEN 'T' THEN 'Gr'
        ELSE NULL
    END;
$$;

COMMENT ON FUNCTION css_utilities.mpc_band_to_ades(char) IS
    'Map MPC photometric band character to ADES band code';


-- ---------------------------------------------------------------------------
-- Unpack MPC packed provisional designation
-- ---------------------------------------------------------------------------
-- Input:  'K24Y04R' -> '2024 YR4'
-- Input:  '00433  ' -> '433'
-- Handles century codes I=18xx, J=19xx, K=20xx and base-62 cycle counts.

CREATE OR REPLACE FUNCTION css_utilities.unpack_designation(packed text)
RETURNS text
LANGUAGE plpgsql IMMUTABLE STRICT PARALLEL SAFE
AS $$
DECLARE
    s        text;
    century  text;
    yr       text;
    half_mo  char;
    cycle_hi char;
    cycle_lo char;
    cycle    int;
    ord_char char;
    b62      text := '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz';
BEGIN
    s := trim(packed);
    IF length(s) = 0 THEN
        RETURN '';
    END IF;

    -- Numbered object: up to 5 chars, digits with optional leading letter
    IF length(s) <= 5 THEN
        IF s ~ '^\d+$' THEN
            RETURN ltrim(s, '0');
        ELSIF s ~ '^[A-Za-z]\d{4}$' THEN
            -- Extended numbering: A0001 = 100001, a0001 = 360001
            RETURN ((position(left(s, 1) in b62) - 1) * 10000
                    + substring(s, 2)::int)::text;
        END IF;
    END IF;

    -- Provisional designation: 7 chars
    IF length(s) < 7 THEN
        RETURN s;
    END IF;

    century := CASE left(s, 1)
        WHEN 'I' THEN '18'
        WHEN 'J' THEN '19'
        WHEN 'K' THEN '20'
        ELSE NULL
    END;
    IF century IS NULL THEN
        RETURN s;
    END IF;

    yr       := century || substring(s, 2, 2);
    half_mo  := substring(s, 4, 1);
    cycle_hi := substring(s, 5, 1);
    cycle_lo := substring(s, 6, 1);
    ord_char := substring(s, 7, 1);

    -- Decode cycle count (base-62 tens digit + units digit)
    IF cycle_hi >= '0' AND cycle_hi <= '9' THEN
        cycle := (ascii(cycle_hi) - ascii('0')) * 10 + (ascii(cycle_lo) - ascii('0'));
    ELSE
        cycle := (position(cycle_hi in b62) - 1) * 10 + (ascii(cycle_lo) - ascii('0'));
    END IF;

    IF cycle = 0 THEN
        RETURN yr || ' ' || half_mo || ord_char;
    ELSE
        RETURN yr || ' ' || half_mo || ord_char || cycle::text;
    END IF;
END;
$$;

COMMENT ON FUNCTION css_utilities.unpack_designation(text) IS
    'Unpack MPC packed designation to human-readable form';


-- ---------------------------------------------------------------------------
-- Convenience: extract all ADES fields from an obs80 line
-- ---------------------------------------------------------------------------
-- Returns a composite row with all parseable fields.

CREATE TYPE css_utilities.ades_obs AS (
    packed_desig text,
    unpacked_desig text,
    disc         char,
    notes        char,
    mode         text,
    obs_time     text,
    ra_deg       double precision,
    dec_deg      double precision,
    mag          double precision,
    band         text,
    ast_cat      text,
    stn          text
);

CREATE OR REPLACE FUNCTION css_utilities.parse_obs80(obs80 text)
RETURNS css_utilities.ades_obs
LANGUAGE plpgsql IMMUTABLE STRICT PARALLEL SAFE
AS $$
DECLARE
    line    text;
    result  css_utilities.ades_obs;
    mag_str text;
BEGIN
    line := rpad(obs80, 80);

    result.packed_desig  := trim(substring(line, 1, 12));
    result.unpacked_desig := css_utilities.unpack_designation(result.packed_desig);
    result.disc          := nullif(substring(line, 13, 1), ' ');
    result.notes         := nullif(substring(line, 14, 1), ' ');
    result.mode          := css_utilities.mpc_mode_to_ades(substring(line, 15, 1));
    result.obs_time      := css_utilities.mpc_date_to_iso8601(substring(line, 16, 17));
    result.ra_deg        := css_utilities.ra_hms_to_deg(substring(line, 33, 12));
    result.dec_deg       := css_utilities.dec_dms_to_deg(substring(line, 45, 12));

    mag_str := trim(substring(line, 66, 5));
    IF mag_str != '' THEN
        result.mag := mag_str::double precision;
    END IF;

    result.band    := css_utilities.mpc_band_to_ades(substring(line, 71, 1));
    result.ast_cat := css_utilities.mpc_cat_to_ades(substring(line, 72, 1));
    result.stn     := trim(substring(line, 78, 3));

    RETURN result;
END;
$$;

COMMENT ON FUNCTION css_utilities.parse_obs80(text) IS
    'Parse MPC 80-col observation line into ADES-compatible fields';


-- ===========================================================================
-- Verification queries (run after installation)
-- ===========================================================================

-- Test date conversion
-- SELECT css_utilities.mpc_date_to_iso8601('2024 12 27.238073');
--   -> '2024-12-27T05:42:49.5Z'

-- Test RA/Dec conversion
-- SELECT css_utilities.ra_hms_to_deg('08 56 40.968');
--   -> 134.17070000...
-- SELECT css_utilities.dec_dms_to_deg('-00 16 11.93');
--   -> -0.26998055...

-- Test designation unpacking
-- SELECT css_utilities.unpack_designation('K24Y04R');
--   -> '2024 YR4'

-- Test full obs80 parse against real data
-- SELECT (css_utilities.parse_obs80(obs80)).*
-- FROM neocp_obs_archive
-- LIMIT 5;
