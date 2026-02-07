-- ==============================================================================
-- NEA DISCOVERY TRACKLET STATISTICS
-- ==============================================================================
-- Project: CSS_SBN_derived
-- Authors: Rob Seaman (Catalina Sky Survey) / Claude (Anthropic)
-- Created: 2026-01-08
-- Updated: 2026-02-08
--
-- Computes discovery tracklet statistics for all Near-Earth Asteroids listed
-- in the MPC's NEA.txt catalog, queried against the MPC/SBN PostgreSQL database.
--
-- NEA.txt source: https://minorplanetcenter.net/iau/MPCORB/NEA.txt
-- NEA.txt uses MPCORB format with NO header lines (data starts at line 1)
--
-- HANDLES BOTH:
--   - Numbered asteroids: (433) Eros, (99942) Apophis, etc.
--   - Unnumbered asteroids: 2024 AA1, 2023 DZ2, etc.
--
-- USAGE:
--   This file is designed to be called from scripts/run_pipeline.sh which:
--   1. Downloads NEA.txt to a temp directory
--   2. Injects the \copy command with the correct path
--   3. Executes this query and exports to CSV
--
-- MANUAL USAGE:
--   1. Download: curl -o /tmp/NEA.txt https://minorplanetcenter.net/iau/MPCORB/NEA.txt
--   2. Run: psql -h host -d mpc_sbn -f sql/discovery_tracklets.sql --csv -o output.csv
--      (Ensure the \copy path below matches your download location)
--
-- OUTPUT COLUMNS:
--   primary_designation                    Number (for numbered) or provisional designation
--   packed_primary_provisional_designation Packed format (e.g., "00433" or "K24A01A")
--   avg_mjd_discovery_tracklet             Mean MJD of discovery tracklet
--   avg_ra_deg                             Mean RA in decimal degrees
--   avg_dec_deg                            Mean Dec in decimal degrees
--   median_v_magnitude                     Median V-band magnitude (corrected)
--   discovery_site_code                    MPC observatory code
--
-- DESIGNATION FORMATS:
--   Numbered asteroids in NEA.txt:
--     - Packed (cols 1-7): "00433" (numbers < 100000), "A0345" (100345), "~0000" (620000+)
--     - Unpacked (cols 167-194): "(433) Eros" or "(99942) Apophis"
--     - obs_sbn.permid: "433" or "99942" (number as string, no parentheses)
--
--   Unnumbered asteroids in NEA.txt:
--     - Packed (cols 1-7): "K24A01A" (2024 AA1), "J95X00A" (1995 XA)
--     - Unpacked (cols 167-194): "2024 AA1" or "1995 XA"
--     - obs_sbn.provid: "2024 AA1" or "1995 XA"
--
-- KNOWN LIMITATIONS:
--   - ~7% of discovery observations have NULL trksub; for these, statistics
--     are computed from the single disc='*' observation rather than the full
--     tracklet
--   - NEAs without any disc='*' observation in obs_sbn cannot be matched
--     (as of 2026-02-07: 2009 US19 and 2024 TZ7; reported to MPC)
-- ==============================================================================

-- Performance indexes (create once, speeds up repeated queries)
CREATE INDEX IF NOT EXISTS idx_obs_sbn_disc ON obs_sbn(disc) WHERE disc = '*';
CREATE INDEX IF NOT EXISTS idx_obs_sbn_provid ON obs_sbn(provid);
CREATE INDEX IF NOT EXISTS idx_obs_sbn_permid ON obs_sbn(permid);
CREATE INDEX IF NOT EXISTS idx_obs_sbn_trksub ON obs_sbn(trksub);

-- Temporary table for NEA.txt data
DROP TABLE IF EXISTS nea_txt_import;
CREATE TEMPORARY TABLE nea_txt_import (raw_line TEXT);

-- Load NEA.txt (this line is typically replaced by scripts/run_pipeline.sh)
-- NEA.txt has NO header lines - all lines are data in MPCORB format
\copy nea_txt_import(raw_line) FROM '/tmp/NEA.txt'

-- ==============================================================================
-- MAIN QUERY
-- ==============================================================================

WITH nea_parsed AS (
    -- Parse MPCORB fixed-width format from NEA.txt
    -- Key columns (1-indexed):
    --   1-7:     Packed designation (number or provisional)
    --   167-194: Readable unpacked designation
    --
    -- PACKED NUMBER FORMAT (columns 1-5, columns 6-7 are spaces):
    --   Numbers < 100000:    Right-justified, zero-padded (e.g., "00433" for 433)
    --   Numbers 100000-619999: Letter prefix A-Z then a-z (e.g., "A0345" = 100345)
    --   Numbers >= 620000:   Tilde prefix with base-62 (e.g., "~0000" = 620000)
    --
    -- PACKED PROVISIONAL FORMAT (all 7 columns):
    --   Century letter + 2-digit year + half-month + cycle + second letter
    --   E.g., "K24A01A" = 2024 AA1, "J95X00A" = 1995 XA
    --
    -- READABLE DESIGNATION (columns 167-194):
    --   Numbered: "(433) Eros" or "(99942) Apophis"
    --   Unnumbered: "2024 AA1" or "1995 XA"
    SELECT
        TRIM(SUBSTRING(raw_line FROM 1 FOR 7)) as packed_desig,
        TRIM(SUBSTRING(raw_line FROM 167 FOR 28)) as unpacked_desig,
        -- Detect if this is a numbered asteroid by checking if readable starts with "("
        TRIM(SUBSTRING(raw_line FROM 167 FOR 28)) ~ '^\([0-9]+\)' as is_numbered,
        -- Extract the number from "(NNN)" format if numbered
        CASE
            WHEN TRIM(SUBSTRING(raw_line FROM 167 FOR 28)) ~ '^\([0-9]+\)'
            THEN REGEXP_REPLACE(
                TRIM(SUBSTRING(raw_line FROM 167 FOR 28)),
                '^\(([0-9]+)\).*$',
                '\1'
            )
            ELSE NULL
        END as asteroid_number,
        -- Extract provisional designation (everything for unnumbered,
        -- or the part after the name for numbered if they have one)
        CASE
            WHEN TRIM(SUBSTRING(raw_line FROM 167 FOR 28)) ~ '^\([0-9]+\)'
            THEN NULL  -- Numbered asteroids: we use the number, not provisional
            ELSE TRIM(SUBSTRING(raw_line FROM 167 FOR 28))
        END as provisional_desig
    FROM nea_txt_import
    WHERE LENGTH(raw_line) >= 167      -- Valid data lines
      AND raw_line !~ '^\s*$'          -- Skip blank lines
      AND raw_line !~ '^-'             -- Skip any separator lines
),

nea_list AS (
    -- Create a unified list with proper identifiers for matching obs_sbn
    -- For numbered asteroids, get their principal provisional designation
    -- from numbered_identifications (the authoritative number-to-designation
    -- cross-reference, more reliable than the partially-populated mpc_orbits)
    SELECT
        np.packed_desig,
        np.unpacked_desig,
        np.is_numbered,
        np.asteroid_number,
        np.provisional_desig,
        -- For numbered asteroids: look up their provisional designation
        -- so we can also search obs_sbn.provid for discovery observations
        numid.unpacked_primary_provisional_designation as num_provid
    FROM nea_parsed np
    LEFT JOIN numbered_identifications numid
        ON np.is_numbered AND numid.permid = np.asteroid_number
),

discovery_info AS (
    -- Find discovery observation for each NEA
    -- Must handle both numbered and unnumbered asteroids
    SELECT DISTINCT ON (neo.unpacked_desig)
        neo.unpacked_desig,
        neo.packed_desig,
        neo.is_numbered,
        neo.asteroid_number,
        neo.provisional_desig,
        neo.num_provid,
        obs.stn as discovery_stn,
        obs.trksub as discovery_trksub
    FROM nea_list neo
    INNER JOIN obs_sbn obs ON (
        -- For numbered asteroids: match on permid (the number as string)
        (neo.is_numbered AND obs.permid = neo.asteroid_number)
        -- For unnumbered asteroids: match on provid (provisional designation)
        OR (NOT neo.is_numbered AND obs.provid = neo.provisional_desig)
        -- For numbered asteroids: also try matching via provisional designation
        -- from numbered_identifications (discovery obs may be stored under provid)
        OR (neo.num_provid IS NOT NULL AND obs.provid = neo.num_provid)
    )
    WHERE obs.disc = '*'
    ORDER BY neo.unpacked_desig, obs.obstime
),

discovery_tracklet_stats AS (
    -- Calculate statistics from all observations in the discovery tracklet
    SELECT
        di.unpacked_desig,
        di.packed_desig,

        -- Average MJD of discovery tracklet
        AVG(
            EXTRACT(EPOCH FROM obs.obstime) / 86400.0 + 40587.0
        ) as avg_mjd,

        -- Average position
        AVG(obs.ra) as avg_ra_deg,
        AVG(obs.dec) as avg_dec_deg,

        -- Median V magnitude with band corrections
        -- Corrections from: https://minorplanetcenter.net/iau/info/BandConversion.txt
        PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY
            obs.mag + CASE obs.band
                WHEN 'V' THEN 0.0    -- V-band (reference)
                WHEN 'v' THEN 0.0
                WHEN 'B' THEN -0.8   -- Blue
                WHEN 'U' THEN -1.3   -- Ultraviolet
                WHEN 'R' THEN 0.4    -- Red
                WHEN 'I' THEN 0.8    -- Infrared
                WHEN 'g' THEN -0.35  -- SDSS green
                WHEN 'r' THEN 0.14   -- SDSS red
                WHEN 'i' THEN 0.32   -- SDSS infrared
                WHEN 'z' THEN 0.26   -- SDSS z
                WHEN 'y' THEN 0.32   -- SDSS y
                WHEN 'u' THEN 2.5    -- SDSS ultraviolet
                WHEN 'w' THEN -0.13  -- ATLAS white
                WHEN 'c' THEN -0.05  -- ATLAS cyan
                WHEN 'o' THEN 0.33   -- ATLAS orange
                WHEN 'G' THEN 0.28   -- Gaia
                WHEN 'J' THEN 1.2    -- 2MASS J
                WHEN 'H' THEN 1.4    -- 2MASS H
                WHEN 'K' THEN 1.7    -- 2MASS K
                WHEN 'C' THEN 0.4    -- Clear/unfiltered
                WHEN 'W' THEN 0.4    -- Wide
                WHEN 'L' THEN 0.2
                WHEN 'Y' THEN 0.7
                WHEN '' THEN -0.8    -- Blank = B-band default
                ELSE 0.0             -- Unknown = assume V
            END
        ) FILTER (WHERE obs.mag IS NOT NULL) as median_v_mag

    FROM discovery_info di
    INNER JOIN obs_sbn obs ON (
        -- Match tracklet observations using the same logic as discovery
        -- For numbered asteroids: match on permid (the number as string)
        (di.is_numbered AND obs.permid = di.asteroid_number)
        -- For unnumbered asteroids: match on provid (provisional designation)
        OR (NOT di.is_numbered AND obs.provid = di.provisional_desig)
        -- For numbered asteroids: also try matching via provisional designation
        OR (di.num_provid IS NOT NULL AND obs.provid = di.num_provid)
    )
    WHERE (
        -- If trksub is available, match the full discovery tracklet
        (di.discovery_trksub IS NOT NULL AND obs.trksub = di.discovery_trksub)
        -- If trksub is NULL, fall back to just the discovery observation itself
        OR (di.discovery_trksub IS NULL AND obs.disc = '*')
    )
    GROUP BY di.unpacked_desig, di.packed_desig
)

-- Final output
SELECT
    -- For numbered objects, output just the number; for unnumbered, output the provisional designation
    CASE
        WHEN di.is_numbered THEN di.asteroid_number
        ELSE dts.unpacked_desig
    END as primary_designation,
    dts.packed_desig as packed_primary_provisional_designation,
    ROUND(dts.avg_mjd::numeric, 6) as avg_mjd_discovery_tracklet,
    ROUND(dts.avg_ra_deg::numeric, 5) as avg_ra_deg,
    ROUND(dts.avg_dec_deg::numeric, 5) as avg_dec_deg,
    ROUND(dts.median_v_mag::numeric, 2) as median_v_magnitude,
    di.discovery_stn as discovery_site_code
FROM discovery_info di
INNER JOIN discovery_tracklet_stats dts
    ON di.unpacked_desig = dts.unpacked_desig
ORDER BY
    -- Sort numbered objects numerically first, then unnumbered alphabetically
    di.is_numbered DESC,
    CASE WHEN di.is_numbered THEN LPAD(di.asteroid_number, 10, '0') ELSE dts.unpacked_desig END;
