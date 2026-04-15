#!/bin/bash
# Deploy NEO Discovery Dashboard caches to Mac Mini
#
# Runs on the MBP (which has database access):
#   1. Rebuilds all Parquet caches via --refresh-only
#   2. Rsyncs cache files to the Mac Mini
#   3. Restarts the Dash app on the Mac Mini
#
# Usage:
#   scripts/deploy_to_mini.sh              # full pipeline: refresh + sync + restart
#   scripts/deploy_to_mini.sh --sync-only  # skip DB refresh, just sync existing caches
#
# Cron example (daily at 06:00 local):
#   0 6 * * * cd /Users/seaman/Desktop/Claude/code/CSS_MPC_toolkit && scripts/deploy_to_mini.sh >> logs/deploy.log 2>&1

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

# Verify venv exists
[[ -f "$PROJECT_DIR/venv/bin/activate" ]] \
    || die "No venv at $PROJECT_DIR/venv"

# ── Step 1: Rebuild caches on MBP ────────────────────────────────
if ! $SYNC_ONLY; then
    log "Step 1: Refreshing caches on MBP"
    cd "$PROJECT_DIR"
    source venv/bin/activate
    PGHOST=sibyl python app/discovery_stats.py --refresh-only \
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

# ── Step 3: Restart app on Mac Mini ──────────────────────────────
log "Step 3: Restarting Dash app on Mac Mini"

ssh "$MINI_HOST" bash -s <<'REMOTE'
set -euo pipefail

APP_DIR="$HOME/CSS_MPC_toolkit"
PIDFILE="$APP_DIR/app/.dash.pid"

# Kill existing app process
if [[ -f "$PIDFILE" ]]; then
    OLD_PID=$(cat "$PIDFILE")
    kill "$OLD_PID" 2>/dev/null && sleep 2
    kill -0 "$OLD_PID" 2>/dev/null && kill -9 "$OLD_PID" 2>/dev/null
    rm -f "$PIDFILE"
fi

# Also kill any stray discovery_stats processes
pkill -f "discovery_stats.py" 2>/dev/null || true
sleep 1

# Start the app in serve-only mode (never queries DB, uses synced caches)
cd "$APP_DIR"
source venv/bin/activate
nohup python app/discovery_stats.py --serve-only > app/dash.log 2>&1 &
echo $! > "$PIDFILE"
echo "App started with PID $!"
REMOTE

log "Step 3: App restarted"

# ── Summary ───────────────────────────────────────────────────────
log "Deploy complete"
echo ""
echo "Dashboard should be live at http://192.168.0.157:8050/"
echo "Tunnel (if running):      https://hotwireduniverse.org/"
