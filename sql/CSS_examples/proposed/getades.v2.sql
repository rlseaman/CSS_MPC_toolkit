/*
 *   GETADES (v2) — recreate ADES from obs_sbn for a given permID or packed provID.
 *
 *   Usage: sudo -u postgres psql -A -t -q -v id="'448972'" -f getades.v2.sql -h sibyl mpc_sbn > out.xml
 *
 *   Differences from v1 (sql/CSS_examples/getades.sql):
 *
 *     - The 40-line concat() chain is replaced by
 *       css_utilities.obs_to_ades_optical(obs_sbn) — single source of truth
 *       for the <optical> element, with proper XML escaping (the v1
 *       concat() emits raw values into free-text fields like `notes` and
 *       `remarks`, which would produce invalid XML if those ever contain
 *       special characters).
 *
 *     - The two redundant SELECTs (one for permid, one for provid via
 *       current_identifications) are unified into a single CTE-based
 *       query. obs_sbn is scanned once.
 *
 *   Requires:
 *     - css_utilities schema with obs_to_ades_optical() defined
 *       (see sql/css_utilities_extensions.sql)
 *
 *   R. Seaman / claude — Apr 30, 2026
 */

\echo <?xml version="1.0" encoding="UTF-8"?>
\echo <ades version="2022">

WITH targets AS (
    -- Numbered-object path: obs_sbn rows directly tagged with this permid.
    SELECT id
      FROM obs_sbn
     WHERE permid IN (:id)

    UNION

    -- Provisional-designation path: rows whose provid is a secondary
    -- designation of the requested primary in current_identifications.
    SELECT o.id
      FROM obs_sbn o
      JOIN current_identifications ci
        ON ci.unpacked_secondary_provisional_designation = o.provid
     WHERE o.permid IS NULL
       AND ci.packed_primary_provisional_designation IN (:id)
)
SELECT css_utilities.obs_to_ades_optical(o)
  FROM obs_sbn o
  JOIN targets t USING (id)
 WHERE o.deprecated IS NULL
   AND o.status IN ('P','p')
 ORDER BY o.obstime;

\echo </ades>
