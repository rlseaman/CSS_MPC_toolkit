#!/bin/bash
# refresh_cron.sh — robustness wrapper around deploy_to_mini.sh.
#
# Scheduled via ~/Library/LaunchAgents/org.seaman.css-refresh.plist at
# 05:30 MST daily. Can also be run manually.
#
# Adds to the plain deploy:
#   - Single-instance lock (atomic mkdir — no competing daily runs)
#   - Retry on transient failure (3 attempts, 2-min backoff)
#   - Post-refresh row-count sanity check (scripts/sanity_check.py)
#   - JSON status file (~/Claude/mpc_sbn/last_refresh_status.json)
#   - Log rotation (keep 30 days)
#
# Exit codes:
#   0 — success (including lock-held: another run is in progress)
#   1 — failure after all retries
#   2 — pre-flight failure (no venv, no scripts, etc.)

# Do NOT set -e: we need to handle failures explicitly. -u caught too many
# bash 3.2 array quirks to be worth it in this script as well.
set -o pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
APP_DIR="$PROJECT_DIR/app"
DEPLOY_SCRIPT="$PROJECT_DIR/scripts/deploy_to_mini.sh"
SANITY_SCRIPT="$PROJECT_DIR/scripts/sanity_check.py"
VENV_PY="$PROJECT_DIR/venv/bin/python"

STATE_DIR="$HOME/Claude/mpc_sbn"
LOG_ROOT="$STATE_DIR/logs"
STATUS_FILE="$STATE_DIR/last_refresh_status.json"
MANIFEST_FILE="$STATE_DIR/cache_manifest.json"
LOCK_DIR="/tmp/css_mpc_refresh.lock"

mkdir -p "$LOG_ROOT"
LOG_FILE="$LOG_ROOT/refresh_cron_$(date +%Y%m%d_%H%M%S).log"

exec >>"$LOG_FILE" 2>&1

now_iso() { date -u '+%Y-%m-%dT%H:%M:%SZ'; }
log() { echo "$(now_iso) | $*"; }

write_status() {
    # $1=OK|FAIL  $2=attempts  $3=elapsed_s  $4=extra_json_body (optional)
    local status="$1" attempts="$2" elapsed="$3" extra="${4:-}"
    mkdir -p "$(dirname "$STATUS_FILE")"
    {
        echo '{'
        echo "  \"status\": \"$status\","
        echo "  \"ts\": \"$(now_iso)\","
        echo "  \"attempts\": $attempts,"
        echo "  \"elapsed_s\": $elapsed,"
        echo "  \"log\": \"$LOG_FILE\""
        [[ -n "$extra" ]] && echo ",  $extra"
        echo '}'
    } > "$STATUS_FILE"
}

log "=== refresh_cron start — script_pid=$$ log=$LOG_FILE ==="

# -- Pre-flight --
for f in "$DEPLOY_SCRIPT" "$SANITY_SCRIPT" "$VENV_PY"; do
    if [[ ! -x "$f" && ! -f "$f" ]]; then
        log "FATAL: missing $f"
        write_status FAIL 0 0 "\"reason\": \"missing $f\""
        exit 2
    fi
done

# -- Lock (atomic mkdir, with stale-lock cleanup) --
# If the lock dir exists but is older than 2 h, assume a prior run died
# and reclaim it. 2 h is generous: a healthy refresh is <5 min, and
# worst-case (3 attempts × full run + 2 × 2-min sleep) is under 20 min.
if [[ -d "$LOCK_DIR" ]]; then
    LOCK_AGE_SEC=$(( $(date +%s) - $(stat -f %m "$LOCK_DIR" 2>/dev/null || echo 0) ))
    if (( LOCK_AGE_SEC > 7200 )); then
        log "Removing stale lock (age ${LOCK_AGE_SEC}s > 7200s)"
        rmdir "$LOCK_DIR" 2>/dev/null || rm -rf "$LOCK_DIR"
    fi
fi
if ! mkdir "$LOCK_DIR" 2>/dev/null; then
    log "Another refresh_cron is already running (lock $LOCK_DIR). Exiting cleanly."
    exit 0
fi
trap 'rmdir "$LOCK_DIR" 2>/dev/null' EXIT

# -- Log rotation (keep 30 days) --
find "$LOG_ROOT" -maxdepth 1 -name 'refresh_cron_*.log' -mtime +30 -delete 2>/dev/null || true

# -- Retry loop --
MAX_ATTEMPTS=3
RETRY_SLEEP=120
RC=1
ELAPSED=0
START_ALL=$(date +%s)

for (( attempt=1; attempt<=MAX_ATTEMPTS; attempt++ )); do
    log "--- attempt $attempt of $MAX_ATTEMPTS ---"
    START=$(date +%s)
    "$DEPLOY_SCRIPT"
    RC=$?
    END=$(date +%s)
    ELAPSED=$((END - START))
    log "attempt $attempt: rc=$RC elapsed=${ELAPSED}s"

    if [[ $RC -eq 0 ]]; then
        # Sanity check (non-fatal to the deploy, but forces a FAIL status).
        log "running sanity check against manifest $MANIFEST_FILE"
        SANITY_OUT=$("$VENV_PY" "$SANITY_SCRIPT" verify "$APP_DIR" "$MANIFEST_FILE" 2>&1)
        SANITY_RC=$?
        log "sanity: rc=$SANITY_RC out=$SANITY_OUT"
        if [[ $SANITY_RC -ne 0 ]]; then
            RC=$SANITY_RC
            log "sanity check FAILED — will retry deploy"
            # Fall through to retry (not break), in case transient Sibyl issue.
        else
            # Persist current counts as new baseline.
            "$VENV_PY" "$SANITY_SCRIPT" update "$APP_DIR" "$MANIFEST_FILE" >/dev/null
            log "manifest updated"
            break
        fi
    fi

    if [[ $attempt -lt $MAX_ATTEMPTS ]]; then
        log "sleeping ${RETRY_SLEEP}s before retry"
        sleep "$RETRY_SLEEP"
    fi
done

TOTAL_ELAPSED=$(( $(date +%s) - START_ALL ))

# -- Status file --
if [[ $RC -eq 0 ]]; then
    log "SUCCESS after $attempt attempt(s), total ${TOTAL_ELAPSED}s"
    COUNTS=$(cat "$MANIFEST_FILE" 2>/dev/null | tr -d '\n' | sed 's/^{//;s/}$//')
    write_status OK "$attempt" "$TOTAL_ELAPSED" "\"counts\": {$COUNTS}"
    log "=== refresh_cron end — OK ==="
    exit 0
else
    log "FAILURE after $attempt attempt(s), total ${TOTAL_ELAPSED}s, last_rc=$RC"
    write_status FAIL "$attempt" "$TOTAL_ELAPSED" "\"last_rc\": $RC"
    log "=== refresh_cron end — FAIL ==="
    exit 1
fi
