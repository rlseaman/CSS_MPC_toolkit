#!/bin/bash
# start-dashboard-rnd.sh — launch the R&D-instance Dash dashboard on Gizmo.
#
# Mirror of ~/Claude/mpc_sbn/start-dashboard.sh, but bound to port 8051
# and with --rnd, which enables R&D-only UI surfaces (notably the
# NEO Consensus tab). Cloudflare's named tunnel routes
# `dev.hotwireduniverse.org` to localhost:8051; access is gated by a
# Cloudflare Access policy.
#
# Cache files live under app/ and are SHARED with the prod instance.
# Both processes read the same parquets — the daily refresh writes
# them once.
#
# Invoked by ~/Library/LaunchAgents/com.rlseaman.dashboard-rnd.plist
# (KeepAlive=true), so manual launch is rare. For ad-hoc runs:
#   ./scripts/start-dashboard-rnd.sh

PROJECT_DIR=/Users/robertseaman/CSS_MPC_toolkit
LOGDIR=/Users/robertseaman/Claude/mpc_sbn/logs
mkdir -p "$LOGDIR"
LOG="$LOGDIR/dashboard-rnd_$(date +%Y%m%d_%H%M%S).log"

cd "$PROJECT_DIR" || { echo "cannot cd $PROJECT_DIR" >&2; exit 1; }

export PGHOST="${PGHOST:-/tmp}"

echo "=== $(date) :: start-dashboard-rnd.sh ===" >"$LOG"
echo "PGHOST=$PGHOST  port=8051  rnd=true  waitress=true" >>"$LOG"
echo "PID (parent shell): $$" >>"$LOG"

# --waitress runs the WSGI app under a multithreaded production
# server. Drop the flag for ad-hoc dev runs that want hot-reload or
# verbose Flask tracebacks.
exec ./venv/bin/python app/discovery_stats.py --rnd --port 8051 \
    --waitress >>"$LOG" 2>&1
