#!/bin/bash
# Daily Orbit News — recurring capture + diff (interim standalone job).
# Runs on Gizmo as robertseaman via launchd at 07:00 MST daily
# (scripts/org.seaman.orbit-watch.plist).
# Eventual home: a stage in refresh_matview_gizmo.sh once the dashboard tab
# is built.
#
# SQL is read straight from the main checkout (sql/orbit_watch/), so a
# `git pull` in ~/CSS_MPC_toolkit deploys SQL edits — the old static copy in
# ~/orbit_watch_cron/ is retired. Logs stay in ~/orbit_watch_cron/ (state).
#
# Pings the ORBITWATCH heartbeat (scripts/heartbeat.sh): start, then ok, or
# /fail if the capture or diff errors or today's snapshot looks short. Until
# HB_ORBITWATCH is added to heartbeat.env the pings just log "skipping".
REPO=/Users/robertseaman/CSS_MPC_toolkit
SQL="$REPO/sql/orbit_watch"
STATE=/Users/robertseaman/orbit_watch_cron
PSQL=/opt/homebrew/bin/psql
MIN_ROWS=40000      # watch set is ~52 K/day; far fewer means a bad capture
LOG="$STATE/orbitwatch_$(date +%Y%m%d_%H%M%S).log"
find "$STATE" -maxdepth 1 -name 'orbitwatch_*.log' -mtime +30 -delete 2>/dev/null

log() { echo "$(date '+%Y-%m-%d %H:%M:%S') $*"; }
# shellcheck source=heartbeat.sh
. "$REPO/scripts/heartbeat.sh"

q() { $PSQL -h /tmp -d mpc_sbn -X -v ON_ERROR_STOP=1 "$@"; }

{
  echo "=== orbit-watch daily run: $(date) ==="
  hb_ping ORBITWATCH start
  fail=""
  echo "--- capture (today's snapshot) ---"
  q -f "$SQL/capture_snapshot.sql" || fail="capture rc=$?"
  if [[ -z "$fail" ]]; then
    echo "--- diff (idempotent: clear today's events first) ---"
    q -c "DELETE FROM css_orbit_watch.orbit_event WHERE event_date = (SELECT MAX(snapshot_date) FROM css_orbit_watch.orbit_snapshot);" \
      && q -f "$SQL/daily_diff.sql" || fail="diff rc=$?"
  fi
  if [[ -z "$fail" ]]; then
    n=$(q -Atc "SELECT count(*) FROM css_orbit_watch.orbit_snapshot WHERE snapshot_date = CURRENT_DATE;")
    log "today's snapshot rows: ${n:-?}"
    [[ "${n:-0}" -ge $MIN_ROWS ]] || fail="today's snapshot has ${n:-0} rows (< $MIN_ROWS)"
  fi
  echo "--- snapshots present (last 7) ---"
  q -c "SELECT snapshot_date, count(*) FROM css_orbit_watch.orbit_snapshot GROUP BY 1 ORDER BY 1 DESC LIMIT 7;"
  echo "--- events by type (latest event_date) ---"
  q -c "SELECT event_type, count(*) FROM css_orbit_watch.orbit_event WHERE event_date=(SELECT MAX(event_date) FROM css_orbit_watch.orbit_event) GROUP BY 1 ORDER BY 1;"
  if [[ -n "$fail" ]]; then
    log "FAILED: $fail"
    hb_ping ORBITWATCH fail "$fail"
  else
    hb_ping ORBITWATCH
  fi
  echo "=== done: $(date) ==="
} >> "$LOG" 2>&1
exit 0
