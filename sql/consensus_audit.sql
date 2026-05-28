-- consensus_audit.sql — sizing probe for the NEO Consensus tab
--
-- Author: Claude + Rob, 2026-05-28
-- Purpose: For each of the six sources in css_neo_consensus.source_membership
-- (MPC NEA.txt, mpc_orbits, CNEOS, NEOCC, NEOfixer, Lowell), surface
-- secondary-designation aliases plus the substantive disagreement
-- composition.  Re-runnable as the consensus drifts.
--
-- Usage on Gizmo:
--   psql -h /tmp -U claude_ro mpc_sbn -P pager=off -f sql/consensus_audit.sql
--   (paths into ~/Claude/mpc_sbn or stdout — no writes to the DB)
--
-- The query is read-only and uses indexed lookups against
-- current_identifications and obs_sbn.  Total wall clock on Gizmo: ~3–4 s.

\pset format aligned
\pset border 2

\echo
\echo ============================================================
\echo  Section A — resolution map per source_membership row
\echo ============================================================

DROP TABLE IF EXISTS pg_temp.resolution_map;
CREATE TEMP TABLE resolution_map AS
SELECT sm.source,
       sm.primary_desig                                              AS reported_primary,
       sm.packed_desig                                               AS reported_packed,
       sm.is_comet                                                   AS reported_is_comet,
       sm.permid,
       ci.unpacked_primary_provisional_designation                   AS true_primary,
       ci.packed_primary_provisional_designation                     AS true_primary_packed,
       ci.object_type,
       ci.numbered
FROM css_neo_consensus.source_membership sm
LEFT JOIN current_identifications ci
       ON ci.packed_secondary_provisional_designation = sm.packed_desig;
CREATE INDEX ON resolution_map (source);
CREATE INDEX ON resolution_map (true_primary);
ANALYZE resolution_map;

\echo --- sanity counters ---
SELECT COUNT(*)                                                     AS rows_total,
       COUNT(*) FILTER (WHERE true_primary IS NULL)                 AS no_ci_match,
       COUNT(*) FILTER (WHERE true_primary IS NOT NULL
                          AND true_primary = reported_primary)      AS self_match,
       COUNT(*) FILTER (WHERE true_primary IS NOT NULL
                          AND true_primary <> reported_primary)     AS aliased
FROM resolution_map;

\echo
\echo ============================================================
\echo  Section B — per-source exception table (every alias row)
\echo ============================================================
SELECT rm.source,
       rm.reported_primary,
       rm.reported_packed,
       rm.true_primary,
       rm.true_primary_packed,
       rm.object_type,
       CASE
         WHEN rm.true_primary ~ '^[PCDXAI]/' THEN 'D_comet'
         WHEN EXISTS (SELECT 1 FROM css_neo_consensus.source_membership x
                       WHERE x.primary_desig = rm.true_primary)     THEN 'B_primary_in_consensus'
         ELSE 'AC_primary_absent'
       END                                                          AS case_class
FROM resolution_map rm
WHERE rm.true_primary IS NOT NULL
  AND rm.true_primary <> rm.reported_primary
ORDER BY rm.source, rm.reported_primary;

\echo
\echo --- which sources hold the true primary, which hold the alias (case B/D) ---
WITH alias_rows AS (
  SELECT rm.source AS aliasing_source, rm.reported_primary, rm.true_primary
  FROM resolution_map rm
  WHERE rm.true_primary IS NOT NULL
    AND rm.true_primary <> rm.reported_primary
)
SELECT a.aliasing_source,
       a.reported_primary,
       a.true_primary,
       (SELECT string_agg(DISTINCT x.source, ',' ORDER BY x.source)
          FROM css_neo_consensus.source_membership x
         WHERE x.primary_desig = a.true_primary)        AS sources_holding_primary,
       (SELECT string_agg(DISTINCT x.source, ',' ORDER BY x.source)
          FROM css_neo_consensus.source_membership x
         WHERE x.primary_desig = a.reported_primary)    AS sources_holding_alias
FROM alias_rows a
ORDER BY a.aliasing_source, a.reported_primary;

\echo
\echo --- non-comet, no-current_identifications-match rows (per source) ---
SELECT source, COUNT(*) AS n_unresolved
FROM resolution_map
WHERE true_primary IS NULL
GROUP BY source ORDER BY n_unresolved DESC;

\echo
\echo ============================================================
\echo  Section C — disagreement composition (v_membership_wide,
\echo              after the NOT is_comet filter)
\echo ============================================================
SELECT in_mpc::int        AS mpc,
       in_mpc_orbits::int AS mpcorb,
       in_cneos::int      AS cneos,
       in_neocc::int      AS neocc,
       in_neofixer::int   AS nf,
       in_lowell::int     AS low,
       COUNT(*)           AS n
FROM css_neo_consensus.v_membership_wide
WHERE in_mpc::int + in_mpc_orbits::int + in_cneos::int
    + in_neocc::int + in_neofixer::int + in_lowell::int < 6
GROUP BY in_mpc, in_mpc_orbits, in_cneos, in_neocc, in_neofixer, in_lowell
ORDER BY n DESC
LIMIT 20;

\echo
\echo ============================================================
\echo  Section D — drill into MISSING-FROM-NEOFIXER (5-of-6 sources have it)
\echo ============================================================
WITH mn AS (
  SELECT primary_desig
  FROM css_neo_consensus.v_membership_wide
  WHERE     in_mpc AND     in_mpc_orbits AND     in_cneos
        AND in_neocc AND NOT in_neofixer AND     in_lowell
)
SELECT COUNT(*)                                                    AS n,
       ROUND(MIN(mo.q::numeric), 3)                                AS q_min,
       ROUND(MAX(mo.q::numeric), 3)                                AS q_max,
       ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP
             (ORDER BY mo.q::numeric)::numeric, 3)                 AS q_median,
       COUNT(*) FILTER (WHERE mo.q::numeric > 1.29)                AS n_q_gt_129,
       ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP
             (ORDER BY mo.h::numeric)::numeric, 1)                 AS h_median,
       COUNT(*) FILTER (WHERE mo.h::numeric >= 27)                 AS n_h_ge_27
FROM mn JOIN mpc_orbits mo
  ON mo.unpacked_primary_provisional_designation = mn.primary_desig;

\echo
\echo ============================================================
\echo  Section E — drill into ONLY-NEOFIXER (n=38, Mars-Crosser shell?)
\echo ============================================================
WITH only_nf AS (
  SELECT v.primary_desig, v.nf_q, v.nf_neo_prob, v.nf_u
  FROM css_neo_consensus.v_membership_wide v
  WHERE NOT v.in_mpc AND NOT v.in_mpc_orbits AND NOT v.in_cneos
        AND NOT v.in_neocc AND     v.in_neofixer AND NOT v.in_lowell
)
SELECT COUNT(*)                                              AS n,
       ROUND(AVG(only_nf.nf_q::numeric), 3)                  AS nf_q_avg,
       COUNT(*) FILTER (WHERE only_nf.nf_q::numeric > 1.30)  AS nfq_gt_130,
       COUNT(*) FILTER (WHERE mo.q::numeric > 1.30)          AS mpcq_gt_130
FROM only_nf
LEFT JOIN mpc_orbits mo
  ON mo.unpacked_primary_provisional_designation = only_nf.primary_desig;

\echo
\echo ============================================================
\echo  Section F — collapse simulation (closes 7 of 365 disagreements)
\echo ============================================================
WITH base AS (
  SELECT sm.source, sm.primary_desig, sm.packed_desig
  FROM css_neo_consensus.source_membership sm
  WHERE NOT sm.is_comet
),
collapsed AS (
  SELECT b.source,
         COALESCE(ci.unpacked_primary_provisional_designation, b.primary_desig) AS canonical
  FROM base b
  LEFT JOIN current_identifications ci
         ON ci.packed_secondary_provisional_designation = b.packed_desig
),
after_pivot AS (
  SELECT canonical AS primary_desig, COUNT(DISTINCT source) AS n_sources
  FROM collapsed GROUP BY canonical
)
SELECT 'before (= v_membership_wide)' AS view, COUNT(*) AS n_primaries,
       COUNT(*) FILTER (WHERE
         (in_mpc::int + in_mpc_orbits::int + in_cneos::int
          + in_neocc::int + in_neofixer::int + in_lowell::int) = 6) AS all_six_agree,
       COUNT(*) FILTER (WHERE
         (in_mpc::int + in_mpc_orbits::int + in_cneos::int
          + in_neocc::int + in_neofixer::int + in_lowell::int) < 6) AS disagreements
FROM css_neo_consensus.v_membership_wide
UNION ALL
SELECT 'after collapse', COUNT(*),
       COUNT(*) FILTER (WHERE n_sources = 6),
       COUNT(*) FILTER (WHERE n_sources < 6)
FROM after_pivot;

\echo
\echo ============================================================
\echo  Section G — Rubin (X05) implicated in 2 comet aliases
\echo ============================================================
SELECT permid, packed_primary_provisional_designation AS pri_packed,
       unpacked_primary_provisional_designation       AS pri_unpacked
FROM numbered_identifications
WHERE packed_primary_provisional_designation IN ('PJ94P010','PI18W010');

\echo --- 2025+ obs of those two comets by station ---
SELECT o.permid, o.stn, COUNT(*) AS n_obs,
       to_char(MIN(o.obstime), 'YYYY-MM-DD') AS first_obs,
       to_char(MAX(o.obstime), 'YYYY-MM-DD') AS last_obs
FROM obs_sbn o
WHERE o.permid IN ('2P','141P')
  AND o.obstime > '2025-01-01'
GROUP BY o.permid, o.stn
ORDER BY o.permid, n_obs DESC;

\echo
\echo ============================================================
\echo  Section H — pairwise directed disagreement matrix
\echo  Cell [A, -B] = count of objects A has but B does NOT.
\echo  (Diagonal omitted; cells read row-by-column.)
\echo ============================================================

WITH w AS (
  SELECT in_mpc, in_cneos, in_neocc, in_neofixer, in_lowell
  FROM css_neo_consensus.v_membership_wide
)
SELECT 'mpc' AS source_A,
       0                                                          AS vs_mpc,
       COUNT(*) FILTER (WHERE in_mpc AND NOT in_cneos)::int        AS vs_cneos,
       COUNT(*) FILTER (WHERE in_mpc AND NOT in_neocc)::int        AS vs_neocc,
       COUNT(*) FILTER (WHERE in_mpc AND NOT in_neofixer)::int     AS vs_nf,
       COUNT(*) FILTER (WHERE in_mpc AND NOT in_lowell)::int       AS vs_lowell,
       COUNT(*) FILTER (WHERE in_mpc)::int                         AS total
FROM w
UNION ALL SELECT 'cneos',
       COUNT(*) FILTER (WHERE in_cneos AND NOT in_mpc)::int,
       0,
       COUNT(*) FILTER (WHERE in_cneos AND NOT in_neocc)::int,
       COUNT(*) FILTER (WHERE in_cneos AND NOT in_neofixer)::int,
       COUNT(*) FILTER (WHERE in_cneos AND NOT in_lowell)::int,
       COUNT(*) FILTER (WHERE in_cneos)::int
FROM w
UNION ALL SELECT 'neocc',
       COUNT(*) FILTER (WHERE in_neocc AND NOT in_mpc)::int,
       COUNT(*) FILTER (WHERE in_neocc AND NOT in_cneos)::int,
       0,
       COUNT(*) FILTER (WHERE in_neocc AND NOT in_neofixer)::int,
       COUNT(*) FILTER (WHERE in_neocc AND NOT in_lowell)::int,
       COUNT(*) FILTER (WHERE in_neocc)::int
FROM w
UNION ALL SELECT 'neofixer',
       COUNT(*) FILTER (WHERE in_neofixer AND NOT in_mpc)::int,
       COUNT(*) FILTER (WHERE in_neofixer AND NOT in_cneos)::int,
       COUNT(*) FILTER (WHERE in_neofixer AND NOT in_neocc)::int,
       0,
       COUNT(*) FILTER (WHERE in_neofixer AND NOT in_lowell)::int,
       COUNT(*) FILTER (WHERE in_neofixer)::int
FROM w
UNION ALL SELECT 'lowell',
       COUNT(*) FILTER (WHERE in_lowell AND NOT in_mpc)::int,
       COUNT(*) FILTER (WHERE in_lowell AND NOT in_cneos)::int,
       COUNT(*) FILTER (WHERE in_lowell AND NOT in_neocc)::int,
       COUNT(*) FILTER (WHERE in_lowell AND NOT in_neofixer)::int,
       0,
       COUNT(*) FILTER (WHERE in_lowell)::int
FROM w;

\echo
\echo === MPC-internal: NEA.txt vs mpc_orbits divergence ===
SELECT COUNT(*) FILTER (WHERE in_mpc AND NOT in_mpc_orbits)  AS in_nea_txt_not_orbits,
       COUNT(*) FILTER (WHERE in_mpc_orbits AND NOT in_mpc)  AS in_orbits_not_nea_txt,
       COUNT(*) FILTER (WHERE in_mpc AND in_mpc_orbits)      AS both
FROM css_neo_consensus.v_membership_wide;

\echo
\echo ============================================================
\echo  Section I — observational characteristics per small
\echo              disagreement category (skip baseline for speed)
\echo ============================================================

DROP TABLE IF EXISTS pg_temp.cat_small;
CREATE TEMP TABLE cat_small AS
SELECT primary_desig, 'missing only NF' AS cat
FROM css_neo_consensus.v_membership_wide
WHERE in_mpc AND in_mpc_orbits AND in_cneos
      AND in_neocc AND NOT in_neofixer AND in_lowell
UNION ALL SELECT primary_desig, 'only NF'
FROM css_neo_consensus.v_membership_wide
WHERE NOT in_mpc AND NOT in_mpc_orbits AND NOT in_cneos
      AND NOT in_neocc AND in_neofixer AND NOT in_lowell
UNION ALL SELECT primary_desig, 'mpc_orbits only'
FROM css_neo_consensus.v_membership_wide
WHERE NOT in_mpc AND in_mpc_orbits AND NOT in_cneos
      AND NOT in_neocc AND NOT in_neofixer AND NOT in_lowell
UNION ALL SELECT primary_desig, 'missing CNEOS+NF'
FROM css_neo_consensus.v_membership_wide
WHERE in_mpc AND in_mpc_orbits AND NOT in_cneos
      AND in_neocc AND NOT in_neofixer AND in_lowell
UNION ALL SELECT primary_desig, 'missing only Lowell'
FROM css_neo_consensus.v_membership_wide
WHERE in_mpc AND in_mpc_orbits AND in_cneos
      AND in_neocc AND in_neofixer AND NOT in_lowell
UNION ALL SELECT primary_desig, 'only Lowell'
FROM css_neo_consensus.v_membership_wide
WHERE NOT in_mpc AND NOT in_mpc_orbits AND NOT in_cneos
      AND NOT in_neocc AND NOT in_neofixer AND in_lowell;
CREATE INDEX ON cat_small (primary_desig);
ANALYZE cat_small;

\echo --- arc / nobs / age per category (obs_summary_all) ---
SELECT t.cat,
       COUNT(*)                                                       AS n,
       ROUND(AVG(o.nobs)::numeric, 0)                                 AS nobs_avg,
       PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY o.nobs)::int       AS nobs_p50,
       ROUND(AVG(o.arc_days)::numeric, 0)                             AS arc_avg,
       PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY o.arc_days)::int   AS arc_p50,
       COUNT(*) FILTER (WHERE o.arc_days < 1)                         AS one_night,
       COUNT(*) FILTER (WHERE o.arc_days < 30)                        AS arc_lt_30d,
       to_char(MIN(o.first_obs), 'YYYY-MM-DD')                        AS earliest_disc,
       to_char(MAX(o.last_obs), 'YYYY-MM-DD')                         AS most_recent_obs
FROM cat_small t
JOIN obs_summary_all o ON o.primary_desig = t.primary_desig
GROUP BY t.cat ORDER BY n DESC;

\echo --- top discovery stations per category ---
WITH ds AS (
  SELECT t.cat, o.disc_by, COUNT(*) AS n_in_cat
  FROM cat_small t
  JOIN obs_summary_all o ON o.primary_desig = t.primary_desig
  WHERE o.disc_by IS NOT NULL
  GROUP BY t.cat, o.disc_by
)
SELECT cat, disc_by,
       (SELECT name FROM public.obscodes WHERE obscode = ds.disc_by) AS station_name,
       n_in_cat
FROM (SELECT *, ROW_NUMBER() OVER (PARTITION BY cat ORDER BY n_in_cat DESC) AS rn
        FROM ds) ds
WHERE rn <= 6
ORDER BY cat, n_in_cat DESC;

\echo --- single-site counts per category (obs_sbn n_stns per provid) ---
WITH cat_n_stns AS (
  SELECT t.cat, t.primary_desig,
         (SELECT COUNT(DISTINCT stn) FROM obs_sbn WHERE provid = t.primary_desig) AS n_stns
  FROM cat_small t
)
SELECT cat,
       COUNT(*)                            AS n,
       COUNT(*) FILTER (WHERE n_stns = 1)  AS single_site,
       COUNT(*) FILTER (WHERE n_stns <= 2) AS stns_le_2,
       ROUND(AVG(n_stns)::numeric, 1)      AS n_stns_avg
FROM cat_n_stns
GROUP BY cat ORDER BY n DESC;
