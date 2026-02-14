#!/bin/bash
# Daily cache refresh for NEO Discovery Statistics Explorer
# Intended to be called by cron — writes a sentinel file so the
# running app can display a "refresh in progress" banner.
#
# Usage:
#   scripts/daily_refresh.sh              # normal cron invocation
#   scripts/daily_refresh.sh --reload     # also restart gunicorn after refresh

set -euo pipefail

APP_DIR="$(cd "$(dirname "$0")/../app" && pwd)"
PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
SENTINEL="$APP_DIR/.refreshing"
LOG="/var/log/neo-dash/refresh.log"
RELOAD=false

if [[ "${1:-}" == "--reload" ]]; then
    RELOAD=true
fi

log_msg() {
    echo "$(date -u '+%Y-%m-%d %H:%M:%S UTC') — $1" >> "$LOG"
}

log_msg "Starting refresh"

# Signal the running app that a refresh is in progress
touch "$SENTINEL"

cleanup() {
    rm -f "$SENTINEL"
}
trap cleanup EXIT

# Activate venv and run refresh
cd "$PROJECT_DIR"
source venv/bin/activate
python app/discovery_stats.py --refresh-only >> "$LOG" 2>&1

log_msg "Refresh complete"

# Optionally reload gunicorn to pick up new caches immediately
if $RELOAD; then
    sudo systemctl reload neo-dash 2>/dev/null && \
        log_msg "Gunicorn reloaded" || \
        log_msg "Gunicorn reload failed (non-fatal)"
fi
