#!/bin/bash
# pg18-start.sh — launchd wrapper for PostgreSQL 18 on Gizmo.
#
# Run by ~/Library/LaunchAgents/local.postgresql18.plist (RunAtLoad +
# KeepAlive/PathState on the data directory). Live copy lives at
# ~/Claude/mpc_sbn/pg18-start.sh; keep the repo copy identical.
#
# 1. Wait for the external NVMe (/Volumes/data1) to mount before
#    starting, so boot doesn't crash-loop on a missing data directory.
# 2. Clear a *stale* postmaster.pid — one whose PID is no longer a
#    postgres process. Postgres itself removes a pidfile whose PID is
#    dead, but not one whose PID has been reused by an unrelated
#    process after a reboot (2026-09-10: PID 704 had become a Safari
#    helper, and PG refused to start for that reason). A pidfile whose
#    PID *is* a live postgres is left alone and we exit 1 — launchd's
#    KeepAlive retries every 10 s, which is the right behaviour when a
#    hung postmaster still holds the directory.
# 3. Run postgres as a child (not exec) and translate launchd's SIGTERM
#    into SIGINT = *fast* shutdown. A bare SIGTERM is a *smart* shutdown
#    that waits for every client to disconnect; the dashboards hold
#    pooled connections, so a reboot or `launchctl kickstart -k` would
#    hang until launchd SIGKILLs postgres — leaving an unclean shutdown
#    and a stale pidfile behind. See docs/disaster_recovery.md §D.

DATA_DIR="/Volumes/data1/postgresql@18"
PG_BIN="/opt/homebrew/opt/postgresql@18/bin"
PIDFILE="$DATA_DIR/postmaster.pid"
MAX_WAIT=120
WAITED=0

log() { echo "$(date '+%Y-%m-%d %H:%M:%S') pg18-start: $*"; }

while [ ! -f "$DATA_DIR/PG_VERSION" ]; do
    sleep 2
    WAITED=$((WAITED + 2))
    if [ "$WAITED" -ge "$MAX_WAIT" ]; then
        log "timed out waiting for $DATA_DIR after ${MAX_WAIT}s" >&2
        exit 1
    fi
done

if [ -f "$PIDFILE" ]; then
    OLD_PID=$(head -1 "$PIDFILE" 2>/dev/null)
    if [[ "$OLD_PID" =~ ^[0-9]+$ ]] \
       && ps -p "$OLD_PID" -o command= 2>/dev/null | grep -q "postgres"; then
        log "postmaster PID $OLD_PID still alive — not starting a second one" >&2
        exit 1
    fi
    log "removing stale $PIDFILE (PID '${OLD_PID:-?}' is not a postgres process)"
    mv -f "$PIDFILE" "$DATA_DIR/postmaster.pid.stale.$(date +%Y%m%d_%H%M%S)"
fi

"$PG_BIN/postgres" -D /opt/homebrew/var/postgresql@18 &
PG_PID=$!

# launchd sends SIGTERM on shutdown / bootout / kickstart -k.
# SIGINT to the postmaster = fast shutdown (roll back sessions, checkpoint,
# exit cleanly). SIGQUIT would be immediate mode — avoid.
on_term() {
    log "SIGTERM received — fast shutdown of postmaster $PG_PID"
    kill -INT "$PG_PID" 2>/dev/null
}
trap on_term TERM INT HUP

# `wait` returns early when the trap fires; loop until postgres has exited.
rc=0
while kill -0 "$PG_PID" 2>/dev/null; do
    wait "$PG_PID"
    rc=$?
done
log "postmaster exited rc=$rc"
exit "$rc"
