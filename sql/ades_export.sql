-- ===========================================================================
-- ADES Export Query: NEOCP Observations
-- ===========================================================================
--
-- Produces ADES-ready columns from neocp_obs_archive, suitable for
-- generating valid ADES XML (general.xsd) or PSV output.
--
-- Requires: css_derived schema functions (css_derived_functions.sql)
--
-- Usage:
--   psql -h sibyl -U claude_ro mpc_sbn -f ades_export.sql
--
-- For production export, pipe to lib/ades_export.py or use COPY.
-- ===========================================================================

-- Export all archived NEOCP observations with resolved designations.
-- Joins neocp_prev_des to replace temporary NEOCP designations with
-- final IAU designations when available.

WITH resolved AS (
    SELECT
        oa.id,
        oa.desig AS neocp_desig,
        -- Resolve to final designation if available
        COALESCE(pd.iau_desig, '') AS iau_desig,
        COALESCE(pd.pkd_desig, '') AS pkd_desig,
        oa.obs80,
        oa.trkid,
        oa.rmsra,
        oa.rmsdec,
        oa.rmscorr,
        oa.rmstime,
        oa.created_at
    FROM neocp_obs_archive oa
    LEFT JOIN neocp_prev_des pd ON pd.desig = oa.desig
)
SELECT
    r.id,
    r.neocp_desig,
    -- Use resolved IAU designation if available; fall back to obs80 desig
    CASE
        WHEN r.iau_desig != '' THEN r.iau_desig
        ELSE (css_derived.parse_obs80(r.obs80)).unpacked_desig
    END AS desig,
    -- Determine if numbered (pure digits) or provisional
    CASE
        WHEN r.iau_desig ~ '^\d+$' THEN 'permID'
        ELSE 'provID'
    END AS id_type,
    -- Core ADES fields parsed from obs80
    (css_derived.parse_obs80(r.obs80)).mode      AS mode,
    (css_derived.parse_obs80(r.obs80)).stn        AS stn,
    (css_derived.parse_obs80(r.obs80)).obs_time   AS "obsTime",
    (css_derived.parse_obs80(r.obs80)).ra_deg     AS ra,
    (css_derived.parse_obs80(r.obs80)).dec_deg    AS dec,
    (css_derived.parse_obs80(r.obs80)).ast_cat    AS "astCat",
    -- Optional fields
    (css_derived.parse_obs80(r.obs80)).disc       AS disc,
    (css_derived.parse_obs80(r.obs80)).notes      AS notes,
    (css_derived.parse_obs80(r.obs80)).mag        AS mag,
    (css_derived.parse_obs80(r.obs80)).band       AS band,
    -- ADES-native uncertainty fields
    r.rmsra   AS "rmsRA",
    r.rmsdec  AS "rmsDec",
    r.rmscorr AS "rmsCorr",
    r.rmstime AS "rmsTime",
    -- Tracklet ID (ADES trkSub)
    r.trkid   AS "trkSub",
    -- Metadata
    r.created_at AS db_created
FROM resolved r
ORDER BY r.neocp_desig, r.created_at;

-- ===========================================================================
-- Optimized variant: parse obs80 once per row using a lateral join
-- ===========================================================================
-- The query above calls parse_obs80 multiple times per row.  This version
-- parses once and is more efficient for large exports:

-- WITH resolved AS (
--     SELECT
--         oa.id, oa.desig AS neocp_desig,
--         COALESCE(pd.iau_desig, '') AS iau_desig,
--         oa.obs80, oa.trkid,
--         oa.rmsra, oa.rmsdec, oa.rmscorr, oa.rmstime,
--         oa.created_at
--     FROM neocp_obs_archive oa
--     LEFT JOIN neocp_prev_des pd ON pd.desig = oa.desig
-- )
-- SELECT
--     r.id, r.neocp_desig,
--     CASE WHEN r.iau_desig != '' THEN r.iau_desig
--          ELSE p.unpacked_desig END AS desig,
--     CASE WHEN r.iau_desig ~ '^\d+$' THEN 'permID'
--          ELSE 'provID' END AS id_type,
--     p.mode, p.stn, p.obs_time AS "obsTime",
--     p.ra_deg AS ra, p.dec_deg AS dec, p.ast_cat AS "astCat",
--     p.disc, p.notes, p.mag, p.band,
--     r.rmsra AS "rmsRA", r.rmsdec AS "rmsDec",
--     r.rmscorr AS "rmsCorr", r.rmstime AS "rmsTime",
--     r.trkid AS "trkSub", r.created_at AS db_created
-- FROM resolved r,
--      LATERAL (SELECT (css_derived.parse_obs80(r.obs80)).*) p
-- ORDER BY r.neocp_desig, r.created_at;
