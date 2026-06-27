-- ==============================================================================
-- DAILY ORBIT NEWS — rebuild orbit_event from all snapshots
-- ==============================================================================
-- Project: CSS_MPC_toolkit
-- Created: 2026-06-27
-- Design:  docs/2026-06-25_daily_orbit_news_design.md
--
-- Wipes orbit_event and regenerates it by diffing every consecutive
-- snapshot_date pair via css_orbit_watch.compute_events(). Use after changing
-- the diff logic (to reclassify history) or after a backfill load that inserts
-- historical snapshots out of order. Safe to re-run.
--
-- USAGE: psql -h /tmp -d mpc_sbn -f sql/orbit_watch/rebuild_events.sql
-- ==============================================================================

DO $$
DECLARE
    r record;
    prev date := NULL;
    total integer := 0;
BEGIN
    DELETE FROM css_orbit_watch.orbit_event;
    FOR r IN
        SELECT DISTINCT snapshot_date AS d
        FROM css_orbit_watch.orbit_snapshot
        ORDER BY snapshot_date
    LOOP
        IF prev IS NOT NULL THEN
            total := total + css_orbit_watch.compute_events(r.d, prev);
        END IF;
        prev := r.d;
    END LOOP;
    RAISE NOTICE 'rebuild_events: % event(s) regenerated across all snapshot pairs', total;
END
$$;
