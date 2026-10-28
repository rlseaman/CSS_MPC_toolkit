#!/bin/bash
# db_up_check.sh — hourly liveness check for the mpc_sbn replica on Gizmo.
#
# Scheduled via ~/Library/LaunchAgents/org.seaman.db-up.plist every hour
# at :20. Added 2026-09-10 after the NVMe-drop outage that went unnoticed
# for 8 h: the public site kept serving 200 from parquet caches and the
# existing heartbeats (06:00 refresh, 07:30 backup, 08:00 Time Machine)
# only exercise the DB once a day. See docs/disaster_recovery.md §D.
#
# Checks, in order (first failure wins):
#   1. pg_isready on the /tmp socket
#   2. a trivial query answers (so a postmaster in recovery/startup fails)
#   3. every logical-replication subscription has an apply worker and
#      received a message from SBN within MAX_RECEIPT_AGE_MIN minutes
#      (last_msg_receipt_time advances on keepalives even when upstream is
#      idle, so an idle publisher does not false-alarm)
#   4. upstream data is actually arriving: the newest obs_sbn.updated_at
#      is no older than MAX_DATA_AGE_MIN minutes. Check 3 cannot see this —
#      during SBN's 2026-10-26 publisher switch the workers stayed up and
#      keepalives kept arriving while no data flowed for ~25 h, and this
#      script reported OK throughout. The longest normal gap over the 90
#      days before that was 3 h 53 min (measured 2026-10-27), hence the
#      6 h default. An upstream (MPC/SBN) pause alerts too, by design.
#      MAX(updated_at) is a backward scan of obs_sbn_updated_at_idx, <1 ms.
#   5. /Volumes/data1 is mounted and writable (the drive is the usual
#      root cause; report it explicitly)
#
# Heartbeat: pings the db-up check on healthchecks.io on success or
# /fail (scripts/heartbeat.sh; HB_DB in ~/Claude/mpc_sbn/heartbeat.env,
# not in git). Configure the check with period 1 h, grace 30 min: a
# silent hour (host dark, launchd unloaded) alerts too. One log line per
# run in ~/Claude/mpc_sbn/logs/db_up_check.log.

set -o pipefail

PG_BIN=/opt/homebrew/opt/postgresql@18/bin
export PGHOST="${PGHOST:-/tmp}"
export PGUSER="${PGUSER:-claude_ro}"
DB=mpc_sbn
MAX_RECEIPT_AGE_MIN="${MAX_RECEIPT_AGE_MIN:-15}"
MAX_DATA_AGE_MIN="${MAX_DATA_AGE_MIN:-360}"
DATA_VOL=/Volumes/data1
LOG_FILE="${LOG_FILE:-$HOME/Claude/mpc_sbn/logs/db_up_check.log}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=heartbeat.sh
[[ -r "$SCRIPT_DIR/heartbeat.sh" ]] && source "$SCRIPT_DIR/heartbeat.sh"
declare -F hb_ping >/dev/null || hb_ping() { :; }

mkdir -p "$(dirname "$LOG_FILE")"
log() { echo "$(date '+%Y-%m-%d %H:%M:%S') $*" | tee -a "$LOG_FILE"; }

fail() {
    local vol="mounted"
    /sbin/mount | grep -q " on $DATA_VOL " || vol="NOT MOUNTED"
    log "FAIL: $* (data1 $vol)"
    hb_ping DB fail "$* (data1 $vol)"
    exit 1
}

# 1. postmaster answering
if ! "$PG_BIN/pg_isready" -h "$PGHOST" -d "$DB" -q 2>/dev/null; then
    fail "pg_isready: no response on $PGHOST"
fi

# 2. a real query
if ! "$PG_BIN/psql" -d "$DB" -Atqc "SELECT 1" -v ON_ERROR_STOP=1 2>/dev/null | grep -qx 1; then
    fail "SELECT 1 failed on $DB (postmaster up but not serving?)"
fi

# 3. replication workers alive and recently fed
rep=$("$PG_BIN/psql" -d "$DB" -Atq -v ON_ERROR_STOP=1 -c "
    SELECT subname
           || ' worker=' || COALESCE(pid::text, 'none')
           || ' receipt_age_min=' || COALESCE(round(EXTRACT(EPOCH FROM (now() - last_msg_receipt_time)) / 60)::text, 'never')
           || CASE WHEN pid IS NULL
                     OR last_msg_receipt_time IS NULL
                     OR now() - last_msg_receipt_time > make_interval(mins => $MAX_RECEIPT_AGE_MIN)
                   THEN ' BAD' ELSE ' ok' END
    FROM pg_stat_subscription ORDER BY subname;" 2>/dev/null) || fail "pg_stat_subscription query failed"
[[ -n "$rep" ]] || fail "no logical-replication subscriptions found"
if grep -q " BAD$" <<<"$rep"; then
    fail "replication: $(tr '\n' ';' <<<"$rep")"
fi

# 4. upstream data actually arriving (connected-but-idle looks fine to 3)
data_age=$("$PG_BIN/psql" -d "$DB" -Atq -v ON_ERROR_STOP=1 -c "
    SELECT round(EXTRACT(EPOCH FROM (now() - MAX(updated_at))) / 60)
    FROM obs_sbn;" 2>/dev/null) || fail "obs_sbn freshness query failed"
[[ "$data_age" =~ ^-?[0-9]+$ ]] || fail "obs_sbn freshness: no updated_at value"
if (( data_age > MAX_DATA_AGE_MIN )); then
    fail "stale data: newest obs_sbn row is ${data_age} min old (> ${MAX_DATA_AGE_MIN}); replication connected but upstream not delivering"
fi

# 5. data volume (informational unless broken)
/sbin/mount | grep -q " on $DATA_VOL " || fail "$DATA_VOL not mounted (PG answered from cache?)"
if ! ( touch "$DATA_VOL/.db_up_wtest" && rm -f "$DATA_VOL/.db_up_wtest" ) 2>/dev/null; then
    # bash under launchd has no TCC grant for the removable volume, so a
    # write test from here is not meaningful — note it, don't fail.
    vol_note="data1 write-test skipped (no volume access from launchd)"
else
    vol_note="data1 writable"
fi

msg="OK: $(tr '\n' ';' <<<"$rep") data_age_min=$data_age $vol_note"
log "$msg"
hb_ping DB "" "$msg"
exit 0
