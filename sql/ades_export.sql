-- ===========================================================================
-- ADES Export Queries: Live NEOCP Observations
-- ===========================================================================
--
-- Produces ADES-ready columns from neocp_obs (the live NEOCP table),
-- suitable for generating valid ADES XML (general.xsd) or PSV output.
--
-- Two use cases:
--   1. Dump all current NEOCP observations
--   2. Dump one designation's observations
--
-- Requires: css_utilities schema functions (css_utilities_functions.sql)
--
-- Usage:
--   -- All current NEOCP observations:
--   psql -h sibyl -U claude_ro mpc_sbn -f ades_export.sql
--
--   -- Single designation (set :desig or use -v):
--   psql -h sibyl -U claude_ro mpc_sbn -v desig="'CE5W292'" -f ades_export.sql
--
-- For production export, pipe to lib/ades_export.py or use COPY.
-- ===========================================================================


-- ===========================================================================
-- USE CASE 1: All current NEOCP observations
-- ===========================================================================
-- Objects currently on the confirmation page.  These are the ones needing
-- follow-up; the archive contains objects already dealt with.

SELECT
    o.desig,
    p.mode,
    p.stn,
    p.obs_time   AS "obsTime",
    p.ra_deg     AS ra,
    p.dec_deg    AS dec,
    p.ast_cat    AS "astCat",
    p.disc,
    p.notes,
    p.mag,
    p.band,
    o.rmsra      AS "rmsRA",
    o.rmsdec     AS "rmsDec",
    o.rmscorr    AS "rmsCorr",
    o.rmstime    AS "rmsTime",
    o.trkid      AS "trkSub",
    o.created_at AS db_created
FROM neocp_obs o,
     LATERAL (SELECT (parse_obs80(o.obs80)).*) p
ORDER BY o.desig, o.created_at;


-- ===========================================================================
-- USE CASE 2: Single designation
-- ===========================================================================
-- Uncomment and set the designation, or use psql -v desig="'CE5W292'"
--
-- SELECT
--     o.desig,
--     p.mode,
--     p.stn,
--     p.obs_time   AS "obsTime",
--     p.ra_deg     AS ra,
--     p.dec_deg    AS dec,
--     p.ast_cat    AS "astCat",
--     p.disc,
--     p.notes,
--     p.mag,
--     p.band,
--     o.rmsra      AS "rmsRA",
--     o.rmsdec     AS "rmsDec",
--     o.rmscorr    AS "rmsCorr",
--     o.rmstime    AS "rmsTime",
--     o.trkid      AS "trkSub",
--     o.created_at AS db_created
-- FROM neocp_obs o,
--      LATERAL (SELECT (parse_obs80(o.obs80)).*) p
-- WHERE o.desig = :desig
-- ORDER BY o.created_at;
