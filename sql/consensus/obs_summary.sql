-- ===========================================================================
-- css_neo_consensus.obs_summary — per-NEO obs aggregates from obs_sbn.
--
-- Replaces the per-target LATERAL aggregate that the dashboard's NEO
-- Consensus tab used to run on every click. That LATERAL was ~5 ms ×
-- 41K targets ≈ 3+ minutes for the all-six-agree set, which capped
-- the table at 5K rows. Pre-computing once per day and joining is
-- O(1) per row at query time.
--
-- Built from public.obs_sbn (not obs_sbn_neo) for full coverage:
-- the consensus view legitimately contains some Mars-Crossers and
-- non-strict-NEOs flagged by NEOfixer/CNEOS that obs_sbn_neo's NEO
-- filter excludes. The cost is paid once per day during refresh.
-- See gizmo_mpc_sbn_replica.md ("obs_sbn is faster than obs_sbn_neo
-- for LATERAL OR-on-key aggregates") for why we keep this on
-- obs_sbn rather than obs_sbn_neo.
--
-- Refresh command (steady state):
--   REFRESH MATERIALIZED VIEW CONCURRENTLY css_neo_consensus.obs_summary;
-- The unique index on primary_desig is what makes CONCURRENTLY work.
-- ===========================================================================

DROP MATERIALIZED VIEW IF EXISTS css_neo_consensus.obs_summary;

CREATE MATERIALIZED VIEW css_neo_consensus.obs_summary AS
SELECT
    ct.primary_desig,
    min(o.obstime)::date                              AS first_obs,
    max(o.obstime)::date                              AS last_obs,
    EXTRACT(EPOCH FROM (max(o.obstime)
                      - min(o.obstime))) / 86400.0    AS arc_days,
    count(*)                                          AS nobs
  FROM (SELECT primary_desig, permid
          FROM css_neo_consensus.v_membership_wide) ct
  JOIN public.obs_sbn o
    ON (ct.permid IS NOT NULL AND o.permid = ct.permid)
    OR o.provid = ct.primary_desig
 GROUP BY ct.primary_desig;

CREATE UNIQUE INDEX IF NOT EXISTS obs_summary_primary_desig_idx
    ON css_neo_consensus.obs_summary (primary_desig);

COMMENT ON MATERIALIZED VIEW css_neo_consensus.obs_summary IS
    'Per-NEO obs aggregates (first_obs, last_obs, arc_days, nobs) from obs_sbn, keyed on primary_desig from v_membership_wide. Daily refresh; LEFT JOIN target for the NEO Consensus dashboard tab.';

GRANT SELECT ON css_neo_consensus.obs_summary TO claude_ro;
