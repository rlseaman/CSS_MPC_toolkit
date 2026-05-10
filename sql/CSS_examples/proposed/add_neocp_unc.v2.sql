/*
 *   add_neocp_unc (v2) — enrich NEOCP submission obs80 lines with
 *   rmsra / rmsdec from neocp_obs.
 *
 *   Usage: sudo -u postgres psql -f add_neocp_unc.v2.sql -A -t -q -h sibyl mpc_sbn \
 *            < /home/fixer/nf/objects/neocp/<desig>/<desig>.obs.txt \
 *            > <desig>.out.txt
 *
 *   Differences from v1 (sql/CSS_examples/add_neocp_unc.sql):
 *
 *     - The three nested IN-subqueries (substring matches on cols 1–12,
 *       15–56, 78–80) are collapsed into a single hash JOIN. Same plan
 *       in practice, but readable and each predicate appears once.
 *
 *     - The rmsra/rmsdec rewrite logic is replaced by
 *       css_utilities.format_obs80_with_uncertainty() — same encoding,
 *       single source of truth, shared with getneos_80col_obs_sbn.
 *
 *   Requires:
 *     - css_utilities.format_obs80_with_uncertainty()
 *       (see sql/css_utilities_extensions.sql)
 */

CREATE TEMPORARY TABLE nf_obs (obs80 text);
\copy nf_obs FROM pstdin;

-- Match each input obs against neocp_obs by the three obs80 substring
-- triple (designation+trksub, date+RA+Dec, station). Output preserves
-- input order via a sort on (date, col-15-case, station) for stability.
SELECT
    css_utilities.format_obs80_with_uncertainty(n.obs80, n.rmsra, n.rmsdec)
  FROM neocp_obs n
  JOIN nf_obs i
    ON substr(n.obs80,  1, 12) = substr(i.obs80,  1, 12)
   AND substr(n.obs80, 15, 42) = substr(i.obs80, 15, 42)
   AND substr(n.obs80, 78,  3) = substr(i.obs80, 78,  3)
 ORDER BY substr(n.obs80, 16, 17),
          substr(n.obs80, 15,  1),
          substr(n.obs80, 78,  3);
