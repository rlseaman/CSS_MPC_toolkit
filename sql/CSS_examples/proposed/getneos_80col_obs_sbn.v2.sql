/*
 *   getneos_80col_obs_sbn (v2) — NEOfixer 80-column astrometry export.
 *
 *   Usage: sudo -u postgres psql -A -t -q -h sibyl mpc_sbn \
 *            < getneos_80col_obs_sbn.v2.sql \
 *            > /home/fixer/neofixer/external/catalog/postgres_allneos.ast
 *
 *   Differences from v1 (sql/CSS_examples/getneos_80col_obs_sbn.sql):
 *
 *     - The five separate INSERTs (one per designation-length cohort)
 *       are collapsed into a single SELECT against a unified key list,
 *       with one obs_sbn scan instead of five.
 *
 *     - The rmsra/rmsdec rewrite logic is replaced by
 *       css_utilities.format_obs80_with_uncertainty() — same logic,
 *       single source of truth, shared with add_neocp_unc.
 *
 *     - Adds explicit `deprecated IS NULL` filter (the v1 query relied
 *       on status='P'/'p' alone; deprecated rows could leak through).
 *
 *   Requires:
 *     - css_utilities.format_obs80_with_uncertainty()
 *       (see sql/css_utilities_extensions.sql)
 */

CREATE TEMPORARY TABLE nf_neos    (nid text);
CREATE TEMPORARY TABLE nf_extras  (eid text);

\copy nf_neos   FROM '/home/fixer/neofixer/external/catalog/primary_neo_unpacked.txt';
\copy nf_extras FROM '/home/fixer/neofixer/external/catalog/extras.unpack';

CREATE INDEX nf_neos_nid_idx   ON nf_neos   (nid);
CREATE INDEX nf_extras_eid_idx ON nf_extras (eid);

-- Build a unified key table: each designation tagged with whether it's
-- a permid (numbered) or provid (provisional). A space at column 5
-- (5-char strpos) marks the new-style provid; 7 marks the old-style;
-- 0 (no space) marks a numbered permid. extras.unpack uses 5-char-only.
CREATE TEMPORARY TABLE nf_keys (key text, kind text);

INSERT INTO nf_keys
  SELECT nid, CASE strpos(nid,' ')
                WHEN 0 THEN 'permid'
                ELSE        'provid'
              END
    FROM nf_neos;

INSERT INTO nf_keys
  SELECT eid, CASE strpos(eid,' ')
                WHEN 0 THEN 'permid'
                ELSE        'provid'
              END
    FROM nf_extras;

CREATE INDEX nf_keys_idx ON nf_keys (key, kind);

-- Single obs_sbn scan: pick up everything matching either permid or
-- provid in the key list, filtered to active+published.
SELECT
    css_utilities.format_obs80_with_uncertainty(o.obs80, o.rmsra, o.rmsdec)
  FROM (
    SELECT DISTINCT obs80, rmsra, rmsdec
      FROM obs_sbn o
      JOIN nf_keys k
        ON (k.kind = 'provid' AND o.provid = k.key)
        OR (k.kind = 'permid' AND o.permid = k.key)
     WHERE o.status IN ('P','p')
       AND o.deprecated IS NULL
       AND (o.rmsra  IS NULL OR o.rmsra  < 5.0)
       AND (o.rmsdec IS NULL OR o.rmsdec < 5.0)
       AND substr(o.obs80, 15, 1) NOT IN ('X','x')
  ) o
  ORDER BY substr(obs80, 16, 17), substr(obs80, 15, 1), substr(obs80, 78, 3);
