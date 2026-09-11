#!/bin/bash
# tm_backup_check.sh — daily dead-man's-switch for Time Machine on Gizmo.
#
# Scheduled via ~/Library/LaunchAgents/org.seaman.tm-check.plist at
# 08:00 MST (after the 07:30 pg_dump, so the newest Time Machine
# snapshot the check sees should already carry today's dump). Can also
# be run manually; prints one summary line and exits 0/1.
#
# Time Machine itself runs hourly (macOS default) to the encrypted APFS
# volume `backup1` (Seagate 2 TB USB HDD, front USB-C port). It backs up
# the boot volume only — /Volumes/data1 (live PGDATA) is deliberately
# NOT included; the irreplaceable css_* schemas reach backup1 via the
# nightly pg_dump on the boot volume. See docs/disaster_recovery.md §G.
#
# Checks, in order (first failure wins):
#   1. /Volumes/backup1 is mounted
#   2. tmutil lists backup1 as a destination
#   3. the newest completed backup is younger than MAX_AGE_H hours
#   4. (warn only) destination free space below WARN_FREE_PCT %
#
# Backup age comes from `tmutil latestbackup -t`; if that is refused
# (Full Disk Access) it falls back to the SnapshotDates array in
# /Library/Preferences/com.apple.TimeMachine.plist.
#
# Heartbeat: pings the tm-backup check on healthchecks.io on success
# or /fail (scripts/heartbeat.sh; HB_TM in ~/Claude/mpc_sbn/heartbeat.env,
# not in git). A silent day (launchd didn't fire, host down) also alerts.

set -o pipefail

DEST_NAME="${DEST_NAME:-backup1}"
DEST_MOUNT="/Volumes/$DEST_NAME"
MAX_AGE_H="${MAX_AGE_H:-26}"
WARN_FREE_PCT="${WARN_FREE_PCT:-10}"
LOG_FILE="${LOG_FILE:-$HOME/Claude/mpc_sbn/backups/tm_check.log}"
TM_PLIST=/Library/Preferences/com.apple.TimeMachine.plist

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=heartbeat.sh
[[ -r "$SCRIPT_DIR/heartbeat.sh" ]] && source "$SCRIPT_DIR/heartbeat.sh"
declare -F hb_ping >/dev/null || hb_ping() { :; }

mkdir -p "$(dirname "$LOG_FILE")"
log() { echo "$(date '+%Y-%m-%d %H:%M:%S') $*" | tee -a "$LOG_FILE"; }

fail() {
    log "FAIL: $*"
    hb_ping TM fail "$*"
    exit 1
}

# 1. mounted
if ! /sbin/mount | grep -q " on $DEST_MOUNT "; then
    fail "$DEST_MOUNT not mounted (drive unplugged, or encrypted volume not unlocked at login)"
fi

# 2. registered as a TM destination
if ! /usr/bin/tmutil destinationinfo 2>/dev/null | grep -q "^Name *: $DEST_NAME\$"; then
    fail "$DEST_NAME is not a Time Machine destination (tmutil destinationinfo)"
fi

# 3. newest backup age
latest_stamp=""
latest_stamp=$(/usr/bin/tmutil latestbackup -t 2>/dev/null | grep -Eo '[0-9]{4}-[0-9]{2}-[0-9]{2}-[0-9]{6}' | tail -1)
if [[ -z "$latest_stamp" ]]; then
    # Fallback: SnapshotDates in the TM prefs (UTC ISO-8601). Take the max.
    latest_iso=$(/usr/bin/plutil -convert json -o - "$TM_PLIST" 2>/dev/null \
        | /usr/bin/tr ',' '\n' | grep -Eo '[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9:]{8}Z' | sort | tail -1)
    if [[ -n "$latest_iso" ]]; then
        latest_epoch=$(TZ=UTC /bin/date -j -f '%Y-%m-%dT%H:%M:%SZ' "$latest_iso" '+%s' 2>/dev/null)
        latest_desc="$latest_iso (from TimeMachine.plist SnapshotDates)"
    fi
else
    latest_epoch=$(/bin/date -j -f '%Y-%m-%d-%H%M%S' "$latest_stamp" '+%s' 2>/dev/null)
    latest_desc="$latest_stamp (tmutil latestbackup)"
fi
[[ -n "${latest_epoch:-}" ]] || fail "no completed Time Machine backup found on $DEST_NAME"

now_epoch=$(/bin/date '+%s')
age_h=$(( (now_epoch - latest_epoch) / 3600 ))
if (( age_h >= MAX_AGE_H )); then
    running=$(/usr/bin/tmutil status 2>/dev/null | grep -Eo 'Running = [01]' | head -1)
    fail "newest backup $latest_desc is ${age_h} h old (limit $MAX_AGE_H h); ${running:-status unknown}"
fi

# 4. free space (warn only)
free_note=""
read -r size_k avail_k < <(/bin/df -k "$DEST_MOUNT" | awk 'NR==2 {print $2, $4}')
if [[ -n "$size_k" && "$size_k" -gt 0 ]]; then
    free_pct=$(( avail_k * 100 / size_k ))
    free_note="free ${free_pct}%"
    (( free_pct < WARN_FREE_PCT )) && log "WARN: $DEST_NAME only ${free_pct}% free (Time Machine will thin old backups)"
fi

msg="OK: newest backup $latest_desc, ${age_h} h old; $free_note"
log "$msg"
hb_ping TM "" "$msg"
exit 0
