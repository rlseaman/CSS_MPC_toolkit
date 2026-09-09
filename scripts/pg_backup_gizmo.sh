#!/bin/bash
# pg_backup_gizmo.sh — nightly pg_dump of the locally-authored schemas.
#
# Scheduled via ~/Library/LaunchAgents/org.seaman.pg-backup.plist at
# 07:30 MST daily (after the 06:00 refresh and the 07:00 orbit-watch
# capture, so the dump carries both). Can also be run manually.
#
# Scope: every schema named css_* (css_neo_consensus, css_orbit_watch,
# css_ades_overlay, css_utilities, plus any added later) and the
# cluster globals (roles). The replicated MPC tables in public are NOT
# dumped — they are recoverable by re-subscribing to SBN, and at
# ~300 GB they are not worth a nightly copy. The css_* schemas are the
# irreplaceable part: see docs/2026-07-16_project_review.md §R1.
#
# Output (all on the boot volume, i.e. NOT on the external NVMe that
# hosts PGDATA):
#   ~/Claude/mpc_sbn/backups/dumps/mpc_sbn_css_YYYYMMDD_HHMMSS.dump
#       pg_dump custom format, zstd-compressed (~265 MB, Sep 2026)
#   ~/Claude/mpc_sbn/backups/dumps/globals_YYYYMMDD_HHMMSS.sql
#       pg_dumpall --globals-only (roles; <1 KB)
#   ~/Claude/mpc_sbn/backups/dumps/mpc_sbn_css_YYYYMMDD_HHMMSS.dump.sha256
#   ~/Claude/mpc_sbn/backups/dumps/latest.dump   -> symlink to newest
#   ~/Claude/mpc_sbn/backups/last_backup_status.json
#   ~/Claude/mpc_sbn/backups/logs/backup_YYYYMMDD_HHMMSS.log
#
# Retention: every dump from the last KEEP_DAILY_DAYS days, plus the
# first dump of each calendar month for KEEP_MONTHLY_DAYS days. Ages
# are taken from the filename stamp, not mtime.
#
# Verification: pg_restore -l must parse the archive and list one
# TABLE DATA entry per ordinary table in the dumped schemas.
#
# Restore procedure: docs/disaster_recovery.md §F.
# Heartbeat: pings the pg-backup check on healthchecks.io at start,
# success, and failure (scripts/heartbeat.sh; URLs in ~/Claude/mpc_sbn/
# heartbeat.env, not in git).
#
# Exit codes:
#   0 — success (including lock-held: another run is in progress)
#   1 — failure (see log file named in status)
#   2 — pre-flight failure (missing binary, DB unreachable, low disk)

set -o pipefail

PG_BIN=/opt/homebrew/bin
PG_DUMP="$PG_BIN/pg_dump"
PG_DUMPALL="$PG_BIN/pg_dumpall"
PG_RESTORE="$PG_BIN/pg_restore"
PSQL="$PG_BIN/psql"

export PGHOST="${PGHOST:-/tmp}"          # Unix socket, peer auth
export PGUSER="${PGUSER:-robertseaman}"  # superuser; can read every schema
DB=mpc_sbn

KEEP_DAILY_DAYS=${KEEP_DAILY_DAYS:-14}
KEEP_MONTHLY_DAYS=${KEEP_MONTHLY_DAYS:-366}
MIN_FREE_GB=${MIN_FREE_GB:-5}
COMPRESS="${COMPRESS:-zstd:6}"

STATE_DIR="$HOME/Claude/mpc_sbn/backups"
DUMP_DIR="$STATE_DIR/dumps"
LOG_ROOT="$STATE_DIR/logs"
STATUS_FILE="$STATE_DIR/last_backup_status.json"
LOCK_DIR="/tmp/gizmo_pg_backup.lock"

mkdir -p "$DUMP_DIR" "$LOG_ROOT"
STAMP="$(date +%Y%m%d_%H%M%S)"
LOG_FILE="$LOG_ROOT/backup_$STAMP.log"

exec >>"$LOG_FILE" 2>&1

now_iso() { date -u '+%Y-%m-%dT%H:%M:%SZ'; }
log() { echo "$(now_iso) | $*"; }

# Dead-man's-switch pings (healthchecks.io); see scripts/heartbeat.sh.
. "$(cd "$(dirname "$0")" && pwd)/heartbeat.sh"

write_status() {
    # $1=OK|FAIL  $2=elapsed_s  $3=extra_json_body (optional)
    local status="$1" elapsed="$2" extra="${3:-}"
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

fail() {
    # $1=exit code  $2=reason
    log "FATAL: $2"
    hb_ping BACKUP fail "$2"
    write_status FAIL $(( $(date +%s) - T0 )) "\"reason\": \"$2\""
    rmdir "$LOCK_DIR" 2>/dev/null
    exit "$1"
}

T0=$(date +%s)
log "=== pg backup start — script_pid=$$ log=$LOG_FILE ==="

# -- Lock --
if ! mkdir "$LOCK_DIR" 2>/dev/null; then
    log "lock held ($LOCK_DIR) — another run in progress; exiting 0"
    exit 0
fi
trap 'rmdir "$LOCK_DIR" 2>/dev/null' EXIT
hb_ping BACKUP start

# -- Pre-flight --
for f in "$PG_DUMP" "$PG_DUMPALL" "$PG_RESTORE" "$PSQL"; do
    [[ -x "$f" ]] || fail 2 "missing $f"
done
if ! "$PSQL" -d "$DB" -Atc "SELECT 1" >/dev/null 2>&1; then
    fail 2 "cannot connect to $DB as $PGUSER via $PGHOST"
fi
free_gb=$(df -g "$DUMP_DIR" | awk 'NR==2 {print $4}')
if [[ -z "$free_gb" || "$free_gb" -lt "$MIN_FREE_GB" ]]; then
    fail 2 "only ${free_gb:-?} GB free under $DUMP_DIR (need $MIN_FREE_GB)"
fi
log "pre-flight ok — ${free_gb} GB free on $(df "$DUMP_DIR" | awk 'NR==2 {print $1}')"

# -- Discover schemas --
SCHEMAS=$("$PSQL" -d "$DB" -Atc \
    "SELECT nspname FROM pg_namespace WHERE nspname LIKE 'css\_%' ORDER BY 1")
[[ -n "$SCHEMAS" ]] || fail 1 "no css_* schemas found in $DB"
SCHEMA_ARGS=()
for s in $SCHEMAS; do SCHEMA_ARGS+=(-n "$s"); done
SCHEMA_LIST=$(echo $SCHEMAS | tr ' ' ',')
N_TABLES=$("$PSQL" -d "$DB" -Atc \
    "SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
      WHERE c.relkind='r' AND n.nspname LIKE 'css\_%'")
log "schemas: $SCHEMA_LIST ($N_TABLES ordinary tables)"

# -- Dump --
DUMP="$DUMP_DIR/mpc_sbn_css_$STAMP.dump"
GLOBALS="$DUMP_DIR/globals_$STAMP.sql"
t1=$(date +%s)
if ! "$PG_DUMP" -d "$DB" -Fc --compress="$COMPRESS" "${SCHEMA_ARGS[@]}" -f "$DUMP"; then
    rm -f "$DUMP"
    fail 1 "pg_dump failed"
fi
DUMP_S=$(( $(date +%s) - t1 ))
BYTES=$(stat -f %z "$DUMP")
log "dump: $DUMP ($BYTES bytes, ${DUMP_S}s)"

if ! "$PG_DUMPALL" --globals-only > "$GLOBALS"; then
    log "WARN: pg_dumpall --globals-only failed (roles not captured)"
    rm -f "$GLOBALS"
fi

# -- Verify --
if ! TOC=$("$PG_RESTORE" -l "$DUMP" 2>&1); then
    fail 1 "pg_restore -l could not read the archive"
fi
N_DATA=$(printf '%s\n' "$TOC" | grep -c ' TABLE DATA ')
if [[ "$N_DATA" -ne "$N_TABLES" ]]; then
    fail 1 "archive lists $N_DATA TABLE DATA entries, catalog has $N_TABLES tables"
fi
if [[ "$BYTES" -lt 1000000 ]]; then
    fail 1 "archive suspiciously small ($BYTES bytes)"
fi
SHA=$(shasum -a 256 "$DUMP" | awk '{print $1}')
echo "$SHA  $(basename "$DUMP")" > "$DUMP.sha256"
ln -sfn "$(basename "$DUMP")" "$DUMP_DIR/latest.dump"
log "verify ok — $N_DATA TABLE DATA entries, sha256=$SHA"

# -- Retention --
today=$(date -j -f %Y%m%d "${STAMP:0:8}" +%s)
seen_ym=""
n_kept=0; n_removed=0
for f in $(ls "$DUMP_DIR"/mpc_sbn_css_*.dump 2>/dev/null | sort); do
    b=$(basename "$f"); st=${b#mpc_sbn_css_}; st=${st%.dump}
    ymd=${st:0:8}; ym=${st:0:6}
    f_epoch=$(date -j -f %Y%m%d "$ymd" +%s 2>/dev/null) || continue
    age=$(( (today - f_epoch) / 86400 ))
    first_of_month=0
    if [[ "$ym" != "$seen_ym" ]]; then first_of_month=1; seen_ym=$ym; fi
    if [[ $age -le $KEEP_DAILY_DAYS ]] || \
       { [[ $first_of_month -eq 1 ]] && [[ $age -le $KEEP_MONTHLY_DAYS ]]; }; then
        n_kept=$((n_kept + 1))
    else
        log "retention: removing $b (age ${age} d)"
        rm -f "$f" "$f.sha256" "$DUMP_DIR/globals_$st.sql"
        n_removed=$((n_removed + 1))
    fi
done
RETAINED_BYTES=$(du -sk "$DUMP_DIR" | awk '{print $1 * 1024}')
log "retention: kept $n_kept, removed $n_removed, dir=$RETAINED_BYTES bytes"

# -- Prune old logs (90 d) --
find "$LOG_ROOT" -name 'backup_*.log' -mtime +90 -delete 2>/dev/null

ELAPSED=$(( $(date +%s) - T0 ))
write_status OK "$ELAPSED" \
    "\"dump\": \"$DUMP\", \"bytes\": $BYTES, \"sha256\": \"$SHA\", \"dump_s\": $DUMP_S, \"schemas\": \"$SCHEMA_LIST\", \"n_tables\": $N_TABLES, \"retained_dumps\": $n_kept, \"retained_bytes\": $RETAINED_BYTES, \"free_gb\": $free_gb"
log "SUCCESS total ${ELAPSED}s"
hb_ping BACKUP "" "SUCCESS $(basename "$DUMP") $BYTES bytes in ${DUMP_S}s; retained $n_kept"
exit 0
