#!/bin/bash
# heartbeat.sh — dead-man's-switch pings to healthchecks.io.
#
# Sourced (not executed) by refresh_matview_gizmo.sh and
# pg_backup_gizmo.sh. Never fails the caller: a missing env file, an
# unreachable hc-ping.com, or a bad role just logs a line and returns 0.
#
# The ping URLs live OUTSIDE the repo in $HOME/Claude/mpc_sbn/heartbeat.env
# (mode 600) — the UUID in each URL is effectively that check's password.
# Expected contents (one per line, no quotes):
#     HB_REFRESH=https://hc-ping.com/<uuid>     # gizmo-refresh, 06:00 MST
#     HB_BACKUP=https://hc-ping.com/<uuid>      # pg-backup, 07:30 MST
#     HB_SITE=https://hc-ping.com/<uuid>        # site-up (public URL 200)
# Each check is configured on healthchecks.io with period 1 day, grace
# 2 h. A day with no ping, or an explicit /fail, raises an email alert.
#
# Usage after sourcing:
#     hb_ping REFRESH start                 # job began (optional; lets
#                                           #   healthchecks show duration)
#     hb_ping REFRESH                       # success
#     hb_ping REFRESH fail "stage 4 rc=1"   # failure — alerts immediately
# The optional third argument is POSTed as the ping body and shows up in
# the check's event log (10 KB cap; we send far less).
#
# Requires a log() function in the caller; falls back to echo.

HB_ENV_FILE="${HB_ENV_FILE:-$HOME/Claude/mpc_sbn/heartbeat.env}"
HB_CURL="${HB_CURL:-/usr/bin/curl}"

_hb_log() {
    if declare -F log >/dev/null 2>&1; then log "$@"; else echo "$*"; fi
}

hb_ping() {
    local role="$1" kind="${2:-}" msg="${3:-}"
    local var="HB_${role}" url suffix=""
    if [[ ! -r "$HB_ENV_FILE" ]]; then
        _hb_log "heartbeat: $HB_ENV_FILE missing — skipping $role $kind"
        return 0
    fi
    url=$(grep -E "^${var}=" "$HB_ENV_FILE" | tail -1 | cut -d= -f2- | tr -d '[:space:]')
    if [[ -z "$url" ]]; then
        _hb_log "heartbeat: no $var in $HB_ENV_FILE — skipping"
        return 0
    fi
    case "$kind" in
        "")      suffix="" ;;
        start)   suffix="/start" ;;
        fail)    suffix="/fail" ;;
        *)       _hb_log "heartbeat: unknown kind '$kind' — sending plain ping"; suffix="" ;;
    esac
    # if/else keeps a curl failure from tripping a caller's `set -e`.
    local rc=0
    local -a args=(-fsS -m 10 --retry 3 --retry-delay 2 -o /dev/null)
    [[ -n "$msg" ]] && args+=(--data-raw "$msg")
    if "$HB_CURL" "${args[@]}" "$url$suffix"; then rc=0; else rc=$?; fi
    if [[ $rc -eq 0 ]]; then
        _hb_log "heartbeat: $role${suffix:-/ok} sent"
    else
        _hb_log "heartbeat: WARN $role${suffix:-/ok} failed (curl rc=$rc)"
    fi
    return 0
}
