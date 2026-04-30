-- ===========================================================================
-- CSS Utilities Extensions — helpers and predicates
-- ===========================================================================
--
-- Extends the css_utilities schema (created by css_utilities_functions.sql)
-- with a few small functions that come up repeatedly in CSS workflow scripts:
--
--   is_published(status)            — encapsulates `status IN ('P','p')`
--   is_active(deprecated)           — encapsulates `deprecated IS NULL`
--   is_neo(q, e)                    — q ≤ 1.3 AU (matches obs_sbn_neo)
--   is_pha(q, e, h)                 — q ≤ 1.3 AND H ≤ 22 AND e < 1
--   tisserand(a, e, i)              — Tisserand parameter w.r.t. Jupiter
--   format_obs80_with_uncertainty   — rewrites cols 56–66 of an obs80 line
--                                     with rmsra/rmsdec, mirroring the
--                                     CSS NEOfixer broker formatter
--   obs_to_ades_optical(obs_sbn)    — emits an <optical> XML element from
--                                     an obs_sbn row, with proper escaping
--
-- Install:
--   psql -h $PGHOST -U <owner> mpc_sbn -f css_utilities_extensions.sql
--
-- ===========================================================================

CREATE SCHEMA IF NOT EXISTS css_utilities;


-- ---------------------------------------------------------------------------
-- Predicates: is_published, is_active
-- ---------------------------------------------------------------------------
-- Trivial wrappers that document intent and are immutable enough to use in
-- partial-index expressions.

CREATE OR REPLACE FUNCTION css_utilities.is_published(p_status char)
  RETURNS boolean
  LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
    SELECT p_status IN ('P','p')
$$;

CREATE OR REPLACE FUNCTION css_utilities.is_active(p_deprecated char)
  RETURNS boolean
  LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
    SELECT p_deprecated IS NULL
$$;


-- ---------------------------------------------------------------------------
-- NEO / PHA classifications matching obs_sbn_neo and the IAU PHA criterion
-- ---------------------------------------------------------------------------
-- is_neo: matches the obs_sbn_neo matview's filter (q ≤ 1.3 AU). Hyperbolic
--         orbits (e ≥ 1) are intentionally INCLUDED — see neo_consensus.md.
-- is_pha: q ≤ 1.3, H ≤ 22, and not hyperbolic. Caller passes nulls if the
--         element is unknown; result is NULL in that case (SQL three-valued).

CREATE OR REPLACE FUNCTION css_utilities.is_neo(p_q double precision,
                                                p_e double precision DEFAULT NULL)
  RETURNS boolean
  LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
    SELECT p_q IS NOT NULL AND p_q <= 1.3
$$;

CREATE OR REPLACE FUNCTION css_utilities.is_pha(p_q double precision,
                                                p_e double precision,
                                                p_h double precision)
  RETURNS boolean
  LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
    SELECT p_q IS NOT NULL AND p_e IS NOT NULL AND p_h IS NOT NULL
       AND p_q <= 1.3 AND p_e < 1.0 AND p_h <= 22.0
$$;


-- ---------------------------------------------------------------------------
-- Tisserand parameter w.r.t. Jupiter
-- ---------------------------------------------------------------------------
-- T_J = a_J/a + 2 * sqrt((a/a_J) * (1 - e^2)) * cos(i)
-- with a_J = 5.20336301 AU (J2000 Jupiter semimajor axis).

CREATE OR REPLACE FUNCTION css_utilities.tisserand(p_a double precision,
                                                   p_e double precision,
                                                   p_i double precision)
  RETURNS double precision
  LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
    SELECT
      CASE WHEN p_a IS NULL OR p_e IS NULL OR p_i IS NULL OR p_a <= 0
        THEN NULL
        ELSE 5.20336301 / p_a
             + 2.0 * sqrt((p_a / 5.20336301) * (1.0 - p_e * p_e))
                   * cos(radians(p_i))
      END
$$;


-- ---------------------------------------------------------------------------
-- format_obs80_with_uncertainty
-- ---------------------------------------------------------------------------
-- Rewrites cols 56–66 of an MPC 80-column observation line with rmsra
-- and rmsdec values, in the same encoding the CSS NEOfixer broker scripts
-- (getneos_80col_obs_sbn.sql, add_neocp_unc.sql) use:
--
--   rmsra = NULL OR rmsdec = NULL  →  pass through unchanged
--   rmsra ≥ 10 OR rmsdec ≥ 10      →  '999 999 '   (whole arcsec, padded)
--   both < 1                        →  ' NNN NNNm'  (milliarcsec)
--   else                            →  'X.XX Y.YY'  (decimal arcsec)
--
-- Handles 80- and 160-character (two-line) variants — for 160-char input
-- the second line is preserved verbatim, separated by chr(10). A trailing
-- chr(10) is appended to the result so the function output can be streamed
-- directly to a file without further newline handling at the call site.

CREATE OR REPLACE FUNCTION css_utilities.format_obs80_with_uncertainty(
    p_obs80  text,
    p_rmsra  numeric,
    p_rmsdec numeric)
  RETURNS text
  LANGUAGE plpgsql IMMUTABLE PARALLEL SAFE AS $$
DECLARE
    rms_field text;
    line_end  text := chr(10);
    second    text;
BEGIN
    second :=
      CASE WHEN length(p_obs80) = 160
           THEN line_end || substr(p_obs80, 81) || line_end
           ELSE line_end
      END;

    IF p_rmsra IS NULL OR p_rmsdec IS NULL THEN
        IF length(p_obs80) = 160 THEN
            RETURN substr(p_obs80, 1, 80) || second;
        ELSE
            RETURN p_obs80 || line_end;
        END IF;
    END IF;

    rms_field :=
      CASE
        WHEN p_rmsra >= 10 OR p_rmsdec >= 10
          THEN to_char(p_rmsra, '999') || to_char(p_rmsdec, '999') || ' '
        WHEN p_rmsra <  1 AND p_rmsdec <  1
          THEN ' '
            || to_char(p_rmsra  * 1000, 'FM000') || ' '
            || to_char(p_rmsdec * 1000, 'FM000') || 'm'
        ELSE
             to_char(p_rmsra,  'FM0.00') || ' '
          || to_char(p_rmsdec, 'FM0.00')
      END;

    RETURN substr(p_obs80, 1, 56) || rms_field || substr(p_obs80, 66, 15)
        || second;
END;
$$;


-- ---------------------------------------------------------------------------
-- obs_to_ades_optical(obs_sbn) → xml
-- ---------------------------------------------------------------------------
-- Builds an ADES <optical> element from an obs_sbn row.  Replaces the
-- ~40-line concat() chain used in CSS_examples/getades.sql and gets XML
-- escaping right (the original concat-based version emits raw values into
-- text fields like `notes` and `remarks` and could produce invalid XML if
-- those fields ever contain `<`, `&`, etc.).
--
-- xmlconcat() drops NULL elements, so each child is guarded by a CASE so
-- absent fields don't render as empty tags.

CREATE OR REPLACE FUNCTION css_utilities.obs_to_ades_optical(o obs_sbn)
  RETURNS xml
  LANGUAGE sql IMMUTABLE AS $$
  SELECT xmlelement(name optical, xmlconcat(
    CASE WHEN o.permid   IS NOT NULL THEN xmlelement(name "permID",   o.permid)   END,
    CASE WHEN o.provid   IS NOT NULL THEN xmlelement(name "provID",   o.provid)   END,
    CASE WHEN o.trksub   IS NOT NULL THEN xmlelement(name "trkSub",   o.trksub)   END,
    CASE WHEN o.obsid    IS NOT NULL THEN xmlelement(name "obsID",    o.obsid)    END,
    CASE WHEN o.trkid    IS NOT NULL THEN xmlelement(name "trkID",    o.trkid)    END,
    CASE WHEN o.trkmpc   IS NOT NULL THEN xmlelement(name "trkMPC",   o.trkmpc)   END,
    CASE WHEN o.mode     IS NOT NULL THEN xmlelement(name "mode",     o.mode)     END,
    CASE WHEN o.stn      IS NOT NULL THEN xmlelement(name "stn",      o.stn)      END,
    CASE WHEN o.sys      IS NOT NULL THEN xmlelement(name "sys",      o.sys)      END,
    CASE WHEN o.ctr      IS NOT NULL THEN xmlelement(name "ctr",      o.ctr)      END,
    CASE WHEN o.pos1     IS NOT NULL THEN xmlelement(name "pos1",     o.pos1)     END,
    CASE WHEN o.pos2     IS NOT NULL THEN xmlelement(name "pos2",     o.pos2)     END,
    CASE WHEN o.pos3     IS NOT NULL THEN xmlelement(name "pos3",     o.pos3)     END,
    CASE WHEN o.prog     IS NOT NULL THEN xmlelement(name "prog",     o.prog)     END,
    CASE WHEN o.obstime  IS NOT NULL THEN xmlelement(name "obsTime",
                                            to_char(o.obstime, 'YYYY-MM-DD"T"HH24:MI:SS.US"Z"')) END,
    CASE WHEN o.rmstime  IS NOT NULL THEN xmlelement(name "rmsTime",  o.rmstime)  END,
    CASE WHEN o.ra       IS NOT NULL THEN xmlelement(name "ra",       o.ra)       END,
    CASE WHEN o.dec      IS NOT NULL THEN xmlelement(name "dec",      o.dec)      END,
    CASE WHEN o.rmsra    IS NOT NULL THEN xmlelement(name "rmsRA",    o.rmsra)    END,
    CASE WHEN o.rmsdec   IS NOT NULL THEN xmlelement(name "rmsDec",   o.rmsdec)   END,
    CASE WHEN o.rmscorr  IS NOT NULL THEN xmlelement(name "rmsCorr",  o.rmscorr)  END,
    CASE WHEN o.astcat   IS NOT NULL THEN xmlelement(name "astCat",   o.astcat)   END,
    CASE WHEN o.mag      IS NOT NULL THEN xmlelement(name "mag",      o.mag)      END,
    CASE WHEN o.rmsmag   IS NOT NULL THEN xmlelement(name "rmsMag",   o.rmsmag)   END,
    CASE WHEN o.band     IS NOT NULL THEN xmlelement(name "band",     o.band)     END,
    CASE WHEN o.photcat  IS NOT NULL THEN xmlelement(name "photCat",  o.photcat)  END,
    CASE WHEN o.photap   IS NOT NULL THEN xmlelement(name "photAp",   o.photap)   END,
    CASE WHEN o.logsnr   IS NOT NULL THEN xmlelement(name "logSNR",   o.logsnr)   END,
    CASE WHEN o.seeing   IS NOT NULL THEN xmlelement(name "seeing",   o.seeing)   END,
    CASE WHEN o.exp      IS NOT NULL THEN xmlelement(name "exp",      o.exp)      END,
    CASE WHEN o.rmsfit   IS NOT NULL THEN xmlelement(name "rmsFit",   o.rmsfit)   END,
    CASE WHEN o.nstars   IS NOT NULL THEN xmlelement(name "nStars",   o.nstars)   END,
    CASE WHEN o.ref      IS NOT NULL THEN xmlelement(name "ref",      o.ref)      END,
    CASE WHEN o.disc     IS NOT NULL THEN xmlelement(name "disc",     o.disc)     END,
    CASE WHEN o.subfmt   IS NOT NULL THEN xmlelement(name "subFmt",   o.subfmt)   END,
    CASE WHEN o.prectime IS NOT NULL THEN xmlelement(name "precTime", o.prectime) END,
    CASE WHEN o.precra   IS NOT NULL THEN xmlelement(name "precRA",   o.precra)   END,
    CASE WHEN o.precdec  IS NOT NULL THEN xmlelement(name "precDec",  o.precdec)  END,
    CASE WHEN o.notes    IS NOT NULL THEN xmlelement(name "notes",    o.notes)    END,
    CASE WHEN o.remarks  IS NOT NULL THEN xmlelement(name "remarks",  o.remarks)  END,
    CASE WHEN o.unctime  IS NOT NULL THEN xmlelement(name "uncTime",  o.unctime)  END
  ))
$$;
