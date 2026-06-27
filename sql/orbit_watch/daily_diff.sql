-- ==============================================================================
-- DAILY ORBIT NEWS — diff the two latest snapshots into orbit_event
-- ==============================================================================
-- Project: CSS_MPC_toolkit
-- Created: 2026-06-25  (refactored 2026-06-27 to call css_orbit_watch.compute_events)
-- Design:  docs/2026-06-25_daily_orbit_news_design.md
--
-- Thin wrapper: the diff logic now lives in css_orbit_watch.compute_events(cur,
-- prev) (defined in schema.sql) so the same code path serves the nightly run,
-- a full rebuild (rebuild_events.sql), and any historical backfill (e.g. from
-- DOU-derived snapshots). compute_events is idempotent for the cur date, so
-- re-running this is safe.
--
-- "cur"/"prev" are the two most recent snapshot_dates present, so a skipped
-- night still diffs correctly against whatever the prior snapshot was.
--
-- USAGE: psql -h /tmp -d mpc_sbn -f sql/orbit_watch/daily_diff.sql
-- ==============================================================================

SELECT css_orbit_watch.compute_events(
    (SELECT max(snapshot_date) FROM css_orbit_watch.orbit_snapshot),
    (SELECT max(snapshot_date) FROM css_orbit_watch.orbit_snapshot
       WHERE snapshot_date < (SELECT max(snapshot_date) FROM css_orbit_watch.orbit_snapshot))
) AS events_inserted;
