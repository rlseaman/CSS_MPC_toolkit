-- ===========================================================================
-- public.obs_summary_all — per-object obs aggregates over ALL of obs_sbn.
--
-- Sibling to css_neo_consensus.obs_summary which is NEO-only (driven by
-- v_membership_wide). This one covers the full mpc_orbits catalog
-- (~1.6M objects), keyed on a designation that matches what
-- mpc_orbits uses: numbered objects by permid, unnumbered by provid.
-- The boxscore_cache / Observation history tab join against this
-- key directly — no NEO-consensus dependency.
--
-- Build cost on Gizmo NVMe (16 GB RAM, PG 18):
--   Plain GROUP BY  primary_desig                ~2:25
--   This view (adds disc_by FILTER)              ~2:30 (FILTER is cheap)
-- The aggregation is I/O-bound on a parallel seq scan of 530M rows;
-- no index speeds it up, and adding (permid, obstime) etc. would only
-- help point lookups. See benchmarks 2026-05-16.
--
-- Solar-elongation is NOT included: it requires the most-recent
-- (ra, dec) per object, which forces a sorted aggregation that blows
-- up timing. Compute on the fly from obs_sbn in the per-object plot
-- callback instead.
--
-- Refresh command (steady state):
--   REFRESH MATERIALIZED VIEW CONCURRENTLY public.obs_summary_all;
-- The unique index on primary_desig is what makes CONCURRENTLY work.
-- ===========================================================================

DROP MATERIALIZED VIEW IF EXISTS public.obs_summary_all;

CREATE MATERIALIZED VIEW public.obs_summary_all AS
SELECT
    COALESCE(NULLIF(permid, ''), provid)         AS primary_desig,
    min(obstime)::date                           AS first_obs,
    max(obstime)::date                           AS last_obs,
    EXTRACT(EPOCH FROM (max(obstime)
                      - min(obstime))) / 86400.0 AS arc_days,
    count(*)                                     AS nobs,
    -- Discovery station: deterministic pick of stn on a disc='*' row.
    -- The partial index obs_sbn(disc) WHERE disc='*' (13 MB) makes
    -- this aggregation cheap to layer on top of the seq scan.
    min(stn) FILTER (WHERE disc = '*')           AS disc_by
  FROM public.obs_sbn
 WHERE COALESCE(NULLIF(permid, ''), provid) IS NOT NULL
 GROUP BY COALESCE(NULLIF(permid, ''), provid);

CREATE UNIQUE INDEX IF NOT EXISTS obs_summary_all_primary_desig_idx
    ON public.obs_summary_all (primary_desig);

COMMENT ON MATERIALIZED VIEW public.obs_summary_all IS
    'Per-object obs aggregates (first_obs, last_obs, arc_days, nobs, disc_by) from obs_sbn for the full mpc_orbits catalog. Keyed on COALESCE(permid, provid). Daily refresh; LEFT JOIN target for the Observation history dashboard tab.';

GRANT SELECT ON public.obs_summary_all TO claude_ro;
