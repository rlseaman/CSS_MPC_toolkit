-- ==============================================================================
-- STANDARD-EPOCH MIGRATION MONITOR
-- ==============================================================================
-- Project: CSS_MPC_toolkit
-- Created: 2026-06-27
-- Analysis: docs/2026-06-27_dou_orbit_logistics.md
--
-- MPC integrates every orbit to a common osculation epoch on an MJD-multiple-
-- of-200 grid, advancing exactly every 200 days. Re-fitting the 1.56M-object
-- catalog to each new standard epoch takes longer than the 200-day cycle, so a
-- backlog is structural — and the stale-epoch objects are the same ones with
-- the "scattershot" data holes (missing a / orbit_type_int / earth_moid).
--
-- This reports how far the catalog (and the NEO subset) has migrated to the
-- current standard epoch, plus the 200-day-stepped backlog histogram. Read-only
-- (claude_ro); ~150 ms against mpc_orbits. To expose to the dashboard, wrap
-- either query in a VIEW in css_orbit_watch (or public).
--
-- USAGE: psql -h /tmp -U claude_ro mpc_sbn -f sql/epoch_migration.sql
-- ==============================================================================

\pset pager off

\echo ===== Current standard epoch + % migrated (catalog vs NEOs) =====
WITH cur AS (
  SELECT round(epoch_mjd)::int AS cur_epoch
  FROM mpc_orbits
  WHERE epoch_mjd IS NOT NULL AND updated_at >= CURRENT_DATE - 7
  GROUP BY 1 ORDER BY count(*) DESC LIMIT 1
),
buckets AS (
  SELECT round(epoch_mjd)::int AS epoch_mjd,
         count(*) AS n,
         count(*) FILTER (WHERE q <= 1.3 AND e < 1) AS n_neo
  FROM mpc_orbits WHERE epoch_mjd IS NOT NULL
  GROUP BY 1
)
SELECT (DATE '1858-11-17' + cur_epoch) AS current_standard_epoch,
       cur_epoch                       AS cur_epoch_mjd,
       (SELECT round(100.0*sum(n)     FILTER (WHERE epoch_mjd=cur_epoch)/sum(n),1)               FROM buckets) AS pct_catalog_current,
       (SELECT round(100.0*sum(n_neo) FILTER (WHERE epoch_mjd=cur_epoch)/NULLIF(sum(n_neo),0),1) FROM buckets) AS pct_neo_current
FROM cur;

\echo ===== Backlog histogram (standard-epoch grid; clusters > 1000) =====
WITH cur AS (
  SELECT round(epoch_mjd)::int AS cur_epoch
  FROM mpc_orbits
  WHERE epoch_mjd IS NOT NULL AND updated_at >= CURRENT_DATE - 7
  GROUP BY 1 ORDER BY count(*) DESC LIMIT 1
),
buckets AS (
  SELECT round(epoch_mjd)::int AS epoch_mjd,
         count(*) AS n,
         count(*) FILTER (WHERE q <= 1.3 AND e < 1) AS n_neo
  FROM mpc_orbits WHERE epoch_mjd IS NOT NULL
  GROUP BY 1
)
SELECT (DATE '1858-11-17' + b.epoch_mjd)             AS epoch_date,
       ((SELECT cur_epoch FROM cur) - b.epoch_mjd)/200 AS epochs_behind,
       b.n                                           AS objects,
       round(100.0*b.n/sum(b.n) OVER (),1)           AS pct_all,
       b.n_neo                                       AS neos,
       round(100.0*b.n_neo/sum(b.n_neo) OVER (),1)   AS pct_neo
FROM buckets b
WHERE b.n > 1000
ORDER BY b.epoch_mjd DESC;
