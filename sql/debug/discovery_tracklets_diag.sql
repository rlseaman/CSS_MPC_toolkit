-- ==============================================================================
-- DIAGNOSTIC QUERIES FOR NEA DISCOVERY TRACKLET MATCHING
-- ==============================================================================
-- Project: CSS_SBN_derived
-- Authors: Rob Seaman (Catalina Sky Survey) / Claude (Anthropic)
-- Created: 2026-01-08
-- Updated: 2026-02-08
--
-- Run these queries after sql/discovery_tracklets.sql to identify NEAs from
-- NEA.txt that failed to match discovery observations in obs_sbn.
--
-- PREREQUISITES:
--   - The temporary table nea_txt_import must exist (created by the main query)
--   - Run this in the same psql session as discovery_tracklets.sql
--
-- POSSIBLE REASONS FOR NO MATCH:
--   1. No discovery observation (disc = '*') in obs_sbn
--   2. Designation mismatch between NEA.txt and obs_sbn
--   3. Object observations stored under different designation (linked/identified)
-- ==============================================================================

-- ==============================================================================
-- QUERY 1: List all NEA.txt entries that were NOT found in the output
-- ==============================================================================

SELECT
    '--- UNMATCHED NEAs FROM NEA.txt ---' as debug_info,
    '' as packed_desig,
    '' as unpacked_desig,
    '' as is_numbered,
    '' as asteroid_number,
    '' as match_attempt_permid,
    '' as match_attempt_provid;

WITH nea_parsed AS (
    SELECT
        TRIM(SUBSTRING(raw_line FROM 1 FOR 7)) as packed_desig,
        TRIM(SUBSTRING(raw_line FROM 167 FOR 28)) as unpacked_desig,
        TRIM(SUBSTRING(raw_line FROM 167 FOR 28)) ~ '^\([0-9]+\)' as is_numbered,
        CASE
            WHEN TRIM(SUBSTRING(raw_line FROM 167 FOR 28)) ~ '^\([0-9]+\)'
            THEN REGEXP_REPLACE(TRIM(SUBSTRING(raw_line FROM 167 FOR 28)), '^\(([0-9]+)\).*$', '\1')
            ELSE NULL
        END as asteroid_number,
        CASE
            WHEN TRIM(SUBSTRING(raw_line FROM 167 FOR 28)) ~ '^\([0-9]+\)'
            THEN NULL
            ELSE TRIM(SUBSTRING(raw_line FROM 167 FOR 28))
        END as provisional_desig
    FROM nea_txt_import
    WHERE LENGTH(raw_line) >= 167
      AND raw_line !~ '^\s*$'
      AND raw_line !~ '^-'
),
nea_list AS (
    SELECT
        np.packed_desig,
        np.unpacked_desig,
        np.is_numbered,
        np.asteroid_number,
        np.provisional_desig,
        numid.unpacked_primary_provisional_designation as num_provid
    FROM nea_parsed np
    LEFT JOIN numbered_identifications numid
        ON np.is_numbered AND numid.permid = np.asteroid_number
),
matched_neas AS (
    SELECT DISTINCT neo.unpacked_desig
    FROM nea_list neo
    INNER JOIN obs_sbn obs ON (
        (neo.is_numbered AND obs.permid = neo.asteroid_number)
        OR (NOT neo.is_numbered AND obs.provid = neo.provisional_desig)
        OR (neo.num_provid IS NOT NULL AND obs.provid = neo.num_provid)
    )
    WHERE obs.disc = '*'
)
SELECT
    'UNMATCHED' as debug_info,
    nl.packed_desig,
    nl.unpacked_desig,
    nl.is_numbered::text,
    COALESCE(nl.asteroid_number, '') as asteroid_number,
    -- Show what we tried to match on
    CASE WHEN nl.is_numbered THEN nl.asteroid_number ELSE '' END as match_attempt_permid,
    COALESCE(nl.provisional_desig, nl.num_provid, '') as match_attempt_provid
FROM nea_list nl
LEFT JOIN matched_neas mn ON nl.unpacked_desig = mn.unpacked_desig
WHERE mn.unpacked_desig IS NULL
ORDER BY nl.is_numbered DESC, nl.unpacked_desig;

-- ==============================================================================
-- QUERY 2: Check if unmatched numbered NEAs have ANY observations in obs_sbn
-- ==============================================================================

SELECT
    '--- SAMPLE: Checking if unmatched numbered NEAs have ANY obs in obs_sbn ---' as debug_info,
    '' as packed_desig,
    '' as unpacked_desig,
    '' as permid_exists,
    '' as provid_via_numid_exists,
    '' as has_disc_star;

WITH nea_parsed AS (
    SELECT
        TRIM(SUBSTRING(raw_line FROM 1 FOR 7)) as packed_desig,
        TRIM(SUBSTRING(raw_line FROM 167 FOR 28)) as unpacked_desig,
        TRIM(SUBSTRING(raw_line FROM 167 FOR 28)) ~ '^\([0-9]+\)' as is_numbered,
        CASE
            WHEN TRIM(SUBSTRING(raw_line FROM 167 FOR 28)) ~ '^\([0-9]+\)'
            THEN REGEXP_REPLACE(TRIM(SUBSTRING(raw_line FROM 167 FOR 28)), '^\(([0-9]+)\).*$', '\1')
            ELSE NULL
        END as asteroid_number
    FROM nea_txt_import
    WHERE LENGTH(raw_line) >= 167
      AND raw_line !~ '^\s*$'
),
nea_list AS (
    SELECT
        np.packed_desig,
        np.unpacked_desig,
        np.is_numbered,
        np.asteroid_number,
        numid.unpacked_primary_provisional_designation as num_provid
    FROM nea_parsed np
    LEFT JOIN numbered_identifications numid
        ON np.is_numbered AND numid.permid = np.asteroid_number
),
matched_neas AS (
    SELECT DISTINCT neo.unpacked_desig
    FROM nea_list neo
    INNER JOIN obs_sbn obs ON (
        (neo.is_numbered AND obs.permid = neo.asteroid_number)
        OR (neo.num_provid IS NOT NULL AND obs.provid = neo.num_provid)
    )
    WHERE obs.disc = '*'
),
unmatched_numbered AS (
    SELECT nl.*
    FROM nea_list nl
    LEFT JOIN matched_neas mn ON nl.unpacked_desig = mn.unpacked_desig
    WHERE mn.unpacked_desig IS NULL
      AND nl.is_numbered = true
    LIMIT 20  -- Sample first 20
)
SELECT
    'CHECK' as debug_info,
    un.packed_desig,
    un.unpacked_desig,
    EXISTS(SELECT 1 FROM obs_sbn WHERE permid = un.asteroid_number LIMIT 1)::text as permid_exists,
    EXISTS(SELECT 1 FROM obs_sbn WHERE provid = un.num_provid LIMIT 1)::text as provid_via_numid_exists,
    EXISTS(SELECT 1 FROM obs_sbn WHERE permid = un.asteroid_number AND disc = '*' LIMIT 1)::text as has_disc_star
FROM unmatched_numbered un
ORDER BY un.asteroid_number::integer;

-- ==============================================================================
-- QUERY 3: Summary statistics for discovery observation trksub coverage
-- ==============================================================================

SELECT
    COUNT(*) as total_disc_obs,
    COUNT(*) FILTER (WHERE trksub IS NULL) as null_trksub,
    COUNT(*) FILTER (WHERE trksub IS NOT NULL) as has_trksub,
    ROUND(100.0 * COUNT(*) FILTER (WHERE trksub IS NULL) / COUNT(*), 1) as pct_null
FROM obs_sbn
WHERE disc = '*';
