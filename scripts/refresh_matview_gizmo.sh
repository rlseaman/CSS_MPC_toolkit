#!/bin/bash
# refresh_matview_gizmo.sh — Gizmo-native daily refresh.
#
# Scheduled via ~/Library/LaunchAgents/org.seaman.gizmo-refresh.plist at
# 06:00 MST daily (Arizona). Can also be run manually.
#
# Stages, all against Gizmo's local mpc_sbn replica via Unix socket:
#   1. REFRESH MATERIALIZED VIEW CONCURRENTLY obs_sbn_neo  (~3.6 min)
#   2. python app/discovery_stats.py --refresh-only        (~1 min; all caches)
#
# Writes a status JSON under $HOME/Claude/mpc_sbn/matview/ that the
# dashboard or an operator can consult.
#
# Exit codes:
#   0 — success (including lock-held: another run is in progress)
#   1 — failure (see log file named in status)
#   2 — pre-flight failure (missing script, venv, or psql)

set -o pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
APP_DIR="$PROJECT_DIR/app"
VENV_PY="$PROJECT_DIR/venv/bin/python"
PSQL=/opt/homebrew/bin/psql

STATE_DIR="$HOME/Claude/mpc_sbn/matview"
LOG_ROOT="$STATE_DIR/logs"
STATUS_FILE="$STATE_DIR/last_refresh_status.json"
LOCK_DIR="/tmp/gizmo_matview_refresh.lock"

mkdir -p "$LOG_ROOT"
LOG_FILE="$LOG_ROOT/refresh_$(date +%Y%m%d_%H%M%S).log"

exec >>"$LOG_FILE" 2>&1

now_iso() { date -u '+%Y-%m-%dT%H:%M:%SZ'; }
log() { echo "$(now_iso) | $*"; }

write_status() {
    # $1=OK|FAIL  $2=elapsed_s  $3=extra_json_body (optional)
    local status="$1" elapsed="$2" extra="${3:-}"
    mkdir -p "$(dirname "$STATUS_FILE")"
    {
        echo '{'
        echo "  \"status\": \"$status\","
        echo "  \"ts\": \"$(now_iso)\","
        echo "  \"elapsed_s\": $elapsed,"
        echo "  \"log\": \"$LOG_FILE\""
        [[ -n "$extra" ]] && echo ",  $extra"
        echo '}'
    } > "$STATUS_FILE"
}

log "=== gizmo refresh start — script_pid=$$ log=$LOG_FILE ==="

# -- Pre-flight --
for f in "$VENV_PY" "$PSQL" "$APP_DIR/discovery_stats.py"; do
    if [[ ! -x "$f" && ! -f "$f" ]]; then
        log "FATAL: missing $f"
        write_status FAIL 0 "\"reason\": \"missing $f\""
        exit 2
    fi
done

# -- Lock (atomic mkdir, stale-lock reclaim after 2 h) --
if [[ -d "$LOCK_DIR" ]]; then
    LOCK_AGE_SEC=$(( $(date +%s) - $(stat -f %m "$LOCK_DIR" 2>/dev/null || echo 0) ))
    if (( LOCK_AGE_SEC > 7200 )); then
        log "Removing stale lock (age ${LOCK_AGE_SEC}s > 7200s)"
        rmdir "$LOCK_DIR" 2>/dev/null || rm -rf "$LOCK_DIR"
    fi
fi
if ! mkdir "$LOCK_DIR" 2>/dev/null; then
    log "Another refresh already running (lock $LOCK_DIR). Exiting cleanly."
    exit 0
fi
trap 'rmdir "$LOCK_DIR" 2>/dev/null' EXIT

# -- Log rotation (keep 30 days) --
find "$LOG_ROOT" -maxdepth 1 -name 'refresh_*.log' -mtime +30 -delete 2>/dev/null || true

cd "$PROJECT_DIR" || { log "FATAL: cannot cd $PROJECT_DIR"; exit 2; }
export PGHOST=/tmp

START_ALL=$(date +%s)

# -- Stage 1: matview refresh --
log "--- stage 1: REFRESH MATERIALIZED VIEW CONCURRENTLY obs_sbn_neo ---"
START=$(date +%s)
"$PSQL" -d mpc_sbn -v ON_ERROR_STOP=1 \
    -c "REFRESH MATERIALIZED VIEW CONCURRENTLY obs_sbn_neo;"
RC=$?
STAGE1_ELAPSED=$(( $(date +%s) - START ))
log "stage 1: rc=$RC elapsed=${STAGE1_ELAPSED}s"
if [[ $RC -ne 0 ]]; then
    TOTAL=$(( $(date +%s) - START_ALL ))
    write_status FAIL "$TOTAL" "\"stage\": \"matview_refresh\", \"last_rc\": $RC, \"stage1_s\": $STAGE1_ELAPSED"
    log "=== gizmo refresh end — FAIL at stage 1 ==="
    exit 1
fi

# -- Stage 2: python parquet cache rebuild --
log "--- stage 2: python app/discovery_stats.py --refresh-only ---"
START=$(date +%s)
"$VENV_PY" app/discovery_stats.py --refresh-only
RC=$?
STAGE2_ELAPSED=$(( $(date +%s) - START ))
log "stage 2: rc=$RC elapsed=${STAGE2_ELAPSED}s"
if [[ $RC -ne 0 ]]; then
    TOTAL=$(( $(date +%s) - START_ALL ))
    write_status FAIL "$TOTAL" "\"stage\": \"cache_refresh\", \"last_rc\": $RC, \"stage1_s\": $STAGE1_ELAPSED, \"stage2_s\": $STAGE2_ELAPSED"
    log "=== gizmo refresh end — FAIL at stage 2 ==="
    exit 1
fi

# -- Stage 3: restart Dash so it loads the freshly-written caches --
# Best-effort: if this fails, stages 1+2 still succeeded and the data
# pipeline is current — the dashboard just keeps serving its older
# in-memory copy until a manual restart. Don't fail the overall job
# on stage-3 trouble.
#
# Bridge fix per docs/disaster_recovery.md "Cache freshness gap (A)";
# preferred long-term: put Dash under launchd (B) or in-process cache
# reload (C). See docs/dashboard_hardening_backlog.md.
log "--- stage 3: restart Dash so the new caches actually serve ---"
START=$(date +%s)
START_DASHBOARD="$HOME/Claude/mpc_sbn/start-dashboard.sh"
STAGE3_NOTE=""

if [[ ! -x "$START_DASHBOARD" ]]; then
    log "WARN: $START_DASHBOARD not found or not executable — skipping restart"
    STAGE3_NOTE="\"stage3_warn\": \"start-dashboard.sh not found\""
else
    # Find the live dashboard PIDs. Exclude any --refresh-only invocation
    # that may still be reaping (shouldn't be, but defensive).
    DASH_PIDS=$(pgrep -f 'app/discovery_stats.py' 2>/dev/null | xargs -I {} sh -c \
        "ps -o pid,command -p {} 2>/dev/null | awk '/discovery_stats.py/ && !/--refresh-only/ {print \$1}'" \
        | tr '\n' ' ')
    DASH_PIDS=$(echo "$DASH_PIDS" | xargs)

    if [[ -n "$DASH_PIDS" ]]; then
        log "stopping Dash (PIDs: $DASH_PIDS)"
        kill -TERM $DASH_PIDS 2>/dev/null
        # Wait up to 10 s for graceful exit
        for _ in 1 2 3 4 5 6 7 8 9 10; do
            sleep 1
            STILL=$(ps -o pid= -p $DASH_PIDS 2>/dev/null | xargs)
            [[ -z "$STILL" ]] && break
        done
        STILL=$(ps -o pid= -p $DASH_PIDS 2>/dev/null | xargs)
        if [[ -n "$STILL" ]]; then
            log "Dash didn't exit gracefully; SIGKILL $STILL"
            kill -KILL $STILL 2>/dev/null
        fi
    else
        log "no Dash process running before restart"
    fi

    log "launching $START_DASHBOARD (detached)"
    nohup "$START_DASHBOARD" </dev/null >/dev/null 2>&1 &
    disown 2>/dev/null || true

    # Give it a few seconds to bind and start serving, then verify.
    sleep 5
    NEW_PID=$(pgrep -f 'app/discovery_stats.py' 2>/dev/null | head -1)
    if [[ -n "$NEW_PID" ]]; then
        log "stage 3: new Dash PID=$NEW_PID"
        STAGE3_NOTE="\"new_dash_pid\": $NEW_PID"
    else
        log "WARN: no Dash PID found after restart — investigate manually"
        STAGE3_NOTE="\"stage3_warn\": \"no new dash pid\""
    fi
fi
STAGE3_ELAPSED=$(( $(date +%s) - START ))
log "stage 3: elapsed=${STAGE3_ELAPSED}s"

TOTAL=$(( $(date +%s) - START_ALL ))
log "SUCCESS total ${TOTAL}s (stage1=${STAGE1_ELAPSED}s stage2=${STAGE2_ELAPSED}s stage3=${STAGE3_ELAPSED}s)"

# Record cache file sizes as a sanity-check proxy.
CACHE_SIZES=""
for prefix in neo_cache apparition_cache boxscore_cache; do
    f=$(ls -1t "$APP_DIR"/.${prefix}_*.parquet 2>/dev/null | head -1)
    if [[ -n "$f" ]]; then
        sz=$(stat -f %z "$f")
        CACHE_SIZES+="\"$prefix\": $sz, "
    fi
done
CACHE_SIZES="${CACHE_SIZES%, }"

EXTRA="\"stage1_s\": $STAGE1_ELAPSED, \"stage2_s\": $STAGE2_ELAPSED, \"stage3_s\": $STAGE3_ELAPSED, \"cache_sizes\": {${CACHE_SIZES}}"
[[ -n "$STAGE3_NOTE" ]] && EXTRA+=", $STAGE3_NOTE"
write_status OK "$TOTAL" "$EXTRA"
log "=== gizmo refresh end — OK ==="
exit 0
