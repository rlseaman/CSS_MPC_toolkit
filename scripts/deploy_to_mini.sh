#!/bin/bash
# Deploy dashboard caches from MBP/Sibyl to Gizmo.
#
# Runs on the MBP (which has Sibyl access).  Dual-purpose:
#   - Manual: user runs it directly when they want a fresh deploy.
#   - Automated: wrapped by scripts/refresh_cron.sh on a nightly launchd
#     schedule (see ~/Library/LaunchAgents/org.seaman.css-refresh.plist).
#
#   1. Rebuilds all Parquet caches on the MBP against Sibyl via
#      --refresh-only (also refreshes the MBP's own caches).
#   2. Rsyncs cache files to Gizmo.
#   3. On Gizmo: git pull origin main, then restart Dash via the
#      on-host start-dashboard.sh wrapper.  That wrapper launches Dash
#      in LIVE-DB mode against Gizmo's local mpc_sbn (PGHOST=/tmp) —
#      Dash uses the freshly rsynced caches at startup but retains the
#      ability to query live if a user triggers a refresh.  To force
#      cache-only mode on Gizmo, pass SERVE_ONLY=1 to start-dashboard.sh
#      directly; this deploy script no longer does that.
#
# Usage:
#   scripts/deploy_to_mini.sh              # full pipeline: refresh + sync + restart
#   scripts/deploy_to_mini.sh --sync-only  # skip DB refresh, just sync existing caches

set -euo pipefail

# ── Configuration ─────────────────────────────────────────────────
MINI_HOST="robertseaman@192.168.0.157"
MINI_APP_DIR="CSS_MPC_toolkit/app"
MINI_PROJECT_DIR="CSS_MPC_toolkit"

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
APP_DIR="$PROJECT_DIR/app"
LOG_DIR="$PROJECT_DIR/logs"

SYNC_ONLY=false
if [[ "${1:-}" == "--sync-only" ]]; then
    SYNC_ONLY=true
fi

# ── Helpers ───────────────────────────────────────────────────────
timestamp() {
    date -u '+%Y-%m-%d %H:%M:%S UTC'
}

log() {
    echo "$(timestamp) — $1"
}

die() {
    log "FATAL: $1"
    exit 1
}

# ── Preflight checks ─────────────────────────────────────────────
mkdir -p "$LOG_DIR"

# Verify Mac Mini is reachable
ssh -o ConnectTimeout=5 -o BatchMode=yes "$MINI_HOST" true 2>/dev/null \
    || die "Cannot reach Mac Mini at $MINI_HOST"

# Verify venv python exists.  We invoke ./venv/bin/python directly
# rather than `source venv/bin/activate` — the activate script has
# a hardcoded VIRTUAL_ENV path that breaks if the project dir is
# renamed, but the interpreter itself keeps working regardless.
[[ -x "$PROJECT_DIR/venv/bin/python" ]] \
    || die "No venv python at $PROJECT_DIR/venv/bin/python"

# ── Step 1: Rebuild caches on MBP ────────────────────────────────
if ! $SYNC_ONLY; then
    log "Step 1: Refreshing caches on MBP"
    cd "$PROJECT_DIR"
    PGHOST=sibyl "$PROJECT_DIR/venv/bin/python" \
        app/discovery_stats.py --refresh-only \
        || die "Cache refresh failed"
    log "Step 1: Cache refresh complete"
else
    log "Step 1: Skipped (--sync-only)"
fi

# ── Step 2: Sync caches to Mac Mini ──────────────────────────────
log "Step 2: Syncing caches to Mac Mini"

# Parquet caches + metadata
rsync -avz --progress \
    "$APP_DIR"/.neo_cache_*.parquet \
    "$APP_DIR"/.neo_cache_*.meta \
    "$APP_DIR"/.apparition_cache_*.parquet \
    "$APP_DIR"/.apparition_cache_*.meta \
    "$APP_DIR"/.boxscore_cache_*.parquet \
    "$APP_DIR"/.boxscore_cache_*.meta \
    "$MINI_HOST:~/$MINI_APP_DIR/"

# Supplementary catalogs
rsync -avz --progress \
    "$APP_DIR"/.nea_h_cache.csv \
    "$APP_DIR"/.nea_raw.txt \
    "$APP_DIR"/.pha_cache.csv \
    "$APP_DIR"/.pha_raw.txt \
    "$APP_DIR"/.sbdb_moid_cache.csv \
    "$MINI_HOST:~/$MINI_APP_DIR/"

# SBDB classification parquet (if present)
if [[ -f "$APP_DIR/.sbdb_classification.parquet" ]]; then
    rsync -avz --progress \
        "$APP_DIR"/.sbdb_classification.parquet \
        "$MINI_HOST:~/$MINI_APP_DIR/"
fi

log "Step 2: Sync complete"

# ── Step 3: Restart Dash on Gizmo (live-DB mode via start-dashboard.sh) ──
log "Step 3: Restarting Dash app on Gizmo"

ssh "$MINI_HOST" bash -s <<'REMOTE'
set -uo pipefail   # NOT -e: Gizmo runs bash 3.2, strict mode + empty arrays is fragile

# Pull latest app code from GitHub so restarts pick up code changes
# alongside refreshed caches.  Fast-forward only — bail loudly on
# divergence rather than silently running stale code.
cd "$HOME/CSS_MPC_toolkit"
echo "Pulling latest from origin/main..."
git pull --ff-only origin main || exit 1

# Identify the Dash process by port (more robust than a stale PID file
# — Homebrew Python's resolved path doesn't contain 'venv/bin/python',
# so process-name matching is unreliable).
OLD_PID=$(lsof -t -i :8050 2>/dev/null | head -1)
if [[ -n "$OLD_PID" ]]; then
    echo "Stopping old Dash (PID $OLD_PID)..."
    kill "$OLD_PID"
    # Wait for port to free; bail at 10 s
    for _ in {1..50}; do
        lsof -i :8050 >/dev/null 2>&1 || break
        sleep 0.2
    done
fi
# Catch any stragglers that outlived their port binding.
pkill -f "discovery_stats.py" 2>/dev/null || true

# Launch via wrapper — sets PGHOST=/tmp (live-DB), writes its own log.
# The wrapper exec's python so there's no intermediate shell to track.
echo "Starting Dash via ~/Claude/mpc_sbn/start-dashboard.sh..."
nohup /Users/robertseaman/Claude/mpc_sbn/start-dashboard.sh \
    </dev/null >/dev/null 2>&1 &
disown

# Verify new Dash answers 200 within 10 s.
for _ in {1..50}; do
    if curl -sf -o /dev/null --max-time 1 http://127.0.0.1:8050/ 2>/dev/null; then
        NEW_PID=$(lsof -t -i :8050 2>/dev/null | head -1)
        echo "Dash restarted successfully (PID ${NEW_PID:-?})"
        exit 0
    fi
    sleep 0.2
done
echo "ERROR: Dash did not answer on :8050 within 10 s" >&2
exit 1
REMOTE

REMOTE_RC=$?
if [[ $REMOTE_RC -ne 0 ]]; then
    die "Step 3 failed (remote rc=$REMOTE_RC)"
fi
log "Step 3: App restarted"

# ── Summary ───────────────────────────────────────────────────────
log "Deploy complete"
echo ""
echo "Dashboard should be live at http://192.168.0.157:8050/"
echo "Tunnel (if running):      https://hotwireduniverse.org/"
