#!/bin/sh
# Daily Orbit News — recurring capture + diff (interim standalone job).
# Runs on Gizmo as robertseaman via launchd at 07:00 MST daily.
# Eventual home: a stage in refresh_matview_gizmo.sh once the backend is on
# main and the dashboard tab is built. SQL lives beside this script.
DIR=/Users/robertseaman/orbit_watch_cron
PSQL=/opt/homebrew/bin/psql
LOG="$DIR/orbitwatch_$(date +%Y%m%d_%H%M%S).log"
find "$DIR" -maxdepth 1 -name 'orbitwatch_*.log' -mtime +30 -delete 2>/dev/null
{
  echo "=== orbit-watch daily run: $(date) ==="
  echo "--- capture (today's snapshot) ---"
  $PSQL -h /tmp -d mpc_sbn -v ON_ERROR_STOP=1 -f "$DIR/capture_snapshot.sql"
  echo "--- diff (idempotent: clear today's events first) ---"
  $PSQL -h /tmp -d mpc_sbn -c "DELETE FROM css_orbit_watch.orbit_event WHERE event_date = (SELECT MAX(snapshot_date) FROM css_orbit_watch.orbit_snapshot);"
  $PSQL -h /tmp -d mpc_sbn -v ON_ERROR_STOP=1 -f "$DIR/daily_diff.sql"
  echo "--- snapshots present ---"
  $PSQL -h /tmp -d mpc_sbn -c "SELECT snapshot_date, count(*) FROM css_orbit_watch.orbit_snapshot GROUP BY 1 ORDER BY 1;"
  echo "--- events by type (latest event_date) ---"
  $PSQL -h /tmp -d mpc_sbn -c "SELECT event_type, count(*) FROM css_orbit_watch.orbit_event WHERE event_date=(SELECT MAX(event_date) FROM css_orbit_watch.orbit_event) GROUP BY 1 ORDER BY 1;"
  echo "=== done: $(date) ==="
} >> "$LOG" 2>&1
exit 0
