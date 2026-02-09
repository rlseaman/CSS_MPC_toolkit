-- ===========================================================================
-- ADES Export Query: Live NEOCP Observations
-- ===========================================================================
--
-- Produces ADES-ready columns from neocp_obs (the live NEOCP table).
-- A single query handles both use cases:
--   - All observations:   pass desig as '' (empty string)
--   - One designation:    pass desig as the NEOCP temp designation
--
-- Requires: css_utilities schema functions (css_utilities_functions.sql)
--
-- Usage:
--   -- All current NEOCP observations:
--   psql -h sibyl -U claude_ro mpc_sbn -v desig="''" -f sql/ades_export.sql
--
--   -- Single designation:
--   psql -h sibyl -U claude_ro mpc_sbn -v desig="'CE5W292'" -f sql/ades_export.sql
--
-- Add --csv for CSV output, or pipe through lib/ades_export.py for XML/PSV.
-- ===========================================================================

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
WHERE :desig = '' OR o.desig = :desig
ORDER BY o.desig, o.created_at;
