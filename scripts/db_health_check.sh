#!/usr/bin/env bash
# ==============================================================================
# MPC/SBN Database Health Check
# ==============================================================================
# Diagnostic toolkit for the CSS replica of the MPC/SBN PostgreSQL database.
# Checks replication status, table health, index usage, configuration,
# and flags potential problems.
#
# Usage:
#   ./scripts/db_health_check.sh                  # Default: $PGHOST or localhost
#   ./scripts/db_health_check.sh --host myhost     # Override host
#   ./scripts/db_health_check.sh --output report   # Save to file
#   ./scripts/db_health_check.sh --help            # Show usage
#
# Requires: psql, read-only access to the target database.
# ==============================================================================

set -euo pipefail

# --- Configuration -----------------------------------------------------------

PGHOST="${PGHOST:-localhost}"
PGDATABASE="${PGDATABASE:-mpc_sbn}"
PGUSER="${PGUSER:-claude_ro}"
OUTPUT=""

# --- Parse arguments ----------------------------------------------------------

while [[ $# -gt 0 ]]; do
    case "$1" in
        --host)    PGHOST="$2"; shift 2 ;;
        --output)  OUTPUT="$2"; shift 2 ;;
        --help)
            echo "Usage: $0 [--host HOST] [--output FILE] [--help]"
            echo ""
            echo "Options:"
            echo "  --host HOST     Database host (default: \$PGHOST or localhost)"
            echo "  --output FILE   Write report to file (default: stdout)"
            echo "  --help          Show this help"
            exit 0 ;;
        *)  echo "Unknown option: $1" >&2; exit 1 ;;
    esac
done

# --- Helpers ------------------------------------------------------------------

PSQL="psql -h $PGHOST -U $PGUSER -d $PGDATABASE -X --pset footer=off"
WARN_FILE=$(mktemp)
cleanup_warns() { rm -f "$WARN_FILE"; }
trap cleanup_warns EXIT

warn() {
    echo "$1" >> "$WARN_FILE"
}

section() {
    echo ""
    echo "=============================================================================="
    echo "  $1"
    echo "=============================================================================="
    echo ""
}

run_query() {
    $PSQL -c "$1" 2>/dev/null || echo "  (query failed or insufficient privileges)"
}

# Redirect all output to file if --output specified
if [ -n "$OUTPUT" ]; then
    exec > "$OUTPUT" 2>&1
fi

echo "MPC/SBN Database Health Check"
echo "Report generated: $(date '+%Y-%m-%d %H:%M:%S %Z')"
echo "Host: $PGHOST | Database: $PGDATABASE | User: $PGUSER"

# ==============================================================================
section "1. DATABASE OVERVIEW"
# ==============================================================================

run_query "
SELECT
    current_database() AS database,
    (SELECT setting FROM pg_settings WHERE name = 'server_version') AS pg_version,
    pg_size_pretty(pg_database_size(current_database())) AS total_size,
    (SELECT COUNT(*) FROM information_schema.tables
     WHERE table_schema = 'public' AND table_type = 'BASE TABLE') AS public_tables,
    now() AS server_time
"

# ==============================================================================
section "2. REPLICATION STATUS"
# ==============================================================================

echo "Subscriptions:"
echo ""
run_query "
SELECT
    subname AS subscription,
    pid,
    received_lsn,
    latest_end_lsn,
    latest_end_time,
    last_msg_receipt_time,
    CASE
        WHEN received_lsn = latest_end_lsn THEN 'OK — in sync'
        ELSE 'WARNING — LSN mismatch'
    END AS lsn_status,
    ROUND(EXTRACT(EPOCH FROM (now() - latest_end_time))::numeric, 0) AS seconds_behind
FROM pg_stat_subscription
WHERE subname IS NOT NULL
ORDER BY subname
"

# Check for replication lag
LAG_SECONDS=$($PSQL -t -A -c "
SELECT COALESCE(MAX(EXTRACT(EPOCH FROM (now() - latest_end_time)))::integer, -1)
FROM pg_stat_subscription
WHERE subname IS NOT NULL
" 2>/dev/null || echo "-1")

if [ "$LAG_SECONDS" -gt 300 ]; then
    warn "REPLICATION LAG: ${LAG_SECONDS}s behind (>5 min threshold)"
elif [ "$LAG_SECONDS" -eq -1 ]; then
    warn "REPLICATION: Could not determine lag (no active subscriptions?)"
fi

echo ""
echo "Replication slots:"
echo ""
run_query "
SELECT slot_name, slot_type, active,
       pg_size_pretty(pg_wal_lsn_diff(pg_current_wal_lsn(), restart_lsn)) AS wal_lag
FROM pg_replication_slots
"

# ==============================================================================
section "3. TABLE HEALTH"
# ==============================================================================

echo "Table sizes, dead tuples, and vacuum status (public schema):"
echo ""
run_query "
SELECT
    relname AS table_name,
    pg_size_pretty(pg_total_relation_size(relid)) AS total_size,
    pg_size_pretty(pg_relation_size(relid)) AS data_size,
    pg_size_pretty(pg_total_relation_size(relid) - pg_relation_size(relid)) AS index_size,
    to_char(n_live_tup, 'FM999,999,999') AS live_rows,
    to_char(n_dead_tup, 'FM999,999,999') AS dead_rows,
    CASE WHEN n_live_tup > 0
         THEN ROUND(100.0 * n_dead_tup / n_live_tup, 1) || '%'
         ELSE '0%'
    END AS dead_pct,
    COALESCE(TO_CHAR(last_autovacuum, 'YYYY-MM-DD'), '-') AS last_autovac,
    COALESCE(TO_CHAR(last_autoanalyze, 'YYYY-MM-DD'), '-') AS last_autoanlz
FROM pg_stat_user_tables
WHERE schemaname = 'public'
ORDER BY pg_total_relation_size(relid) DESC
"

# Check for dead tuple bloat
$PSQL -t -A -c "
SELECT relname,
       to_char(n_dead_tup, 'FM999,999,999'),
       ROUND(100.0 * n_dead_tup / GREATEST(n_live_tup, 1), 1)
FROM pg_stat_user_tables
WHERE schemaname = 'public' AND n_dead_tup > 1000000
ORDER BY n_dead_tup DESC
" 2>/dev/null | while IFS='|' read -r tbl dead pct; do
    warn "DEAD TUPLES: $tbl has $dead dead rows (${pct}% of live)"
done

# Check for stale autovacuum
$PSQL -t -A -c "
SELECT relname,
       EXTRACT(EPOCH FROM (now() - GREATEST(
           COALESCE(last_autovacuum, TIMESTAMP '2020-01-01'),
           COALESCE(last_vacuum, TIMESTAMP '2020-01-01')
       )))::integer / 86400
FROM pg_stat_user_tables
WHERE schemaname = 'public'
  AND n_live_tup > 100000
  AND GREATEST(
      COALESCE(last_autovacuum, TIMESTAMP '2020-01-01'),
      COALESCE(last_vacuum, TIMESTAMP '2020-01-01')
  ) < now() - INTERVAL '90 days'
ORDER BY 2 DESC
" 2>/dev/null | while IFS='|' read -r tbl days; do
    warn "STALE VACUUM: $tbl not vacuumed in ${days} days"
done

# Check for stale analyze
$PSQL -t -A -c "
SELECT relname,
       EXTRACT(EPOCH FROM (now() - GREATEST(
           COALESCE(last_autoanalyze, TIMESTAMP '2020-01-01'),
           COALESCE(last_analyze, TIMESTAMP '2020-01-01')
       )))::integer / 86400
FROM pg_stat_user_tables
WHERE schemaname = 'public'
  AND n_live_tup > 100000
  AND GREATEST(
      COALESCE(last_autoanalyze, TIMESTAMP '2020-01-01'),
      COALESCE(last_analyze, TIMESTAMP '2020-01-01')
  ) < now() - INTERVAL '90 days'
ORDER BY 2 DESC
" 2>/dev/null | while IFS='|' read -r tbl days; do
    warn "STALE ANALYZE: $tbl not analyzed in ${days} days"
done

# ==============================================================================
section "4. INDEX ANALYSIS"
# ==============================================================================

echo "Index usage on obs_sbn (sorted by size):"
echo ""
run_query "
SELECT
    indexrelname AS index_name,
    pg_size_pretty(pg_relation_size(indexrelid)) AS size,
    idx_scan AS scans,
    CASE
        WHEN idx_scan = 0 THEN '** NEVER USED **'
        WHEN idx_scan < 100 THEN 'very low'
        WHEN idx_scan < 10000 THEN 'low'
        WHEN idx_scan < 1000000 THEN 'moderate'
        ELSE 'high'
    END AS usage
FROM pg_stat_user_indexes
WHERE schemaname = 'public' AND relname = 'obs_sbn'
ORDER BY pg_relation_size(indexrelid) DESC
"

# Flag unused indexes
$PSQL -t -A -c "
SELECT indexrelname, pg_size_pretty(pg_relation_size(indexrelid))
FROM pg_stat_user_indexes
WHERE schemaname = 'public' AND idx_scan = 0
  AND pg_relation_size(indexrelid) > 1048576
ORDER BY pg_relation_size(indexrelid) DESC
" 2>/dev/null | while IFS='|' read -r idx size; do
    warn "UNUSED INDEX: $idx ($size) — zero scans since last stats reset"
done

echo ""
echo "Duplicate index check (same table, same column, same type):"
echo ""
run_query "
SELECT
    t.relname AS table_name,
    a.indexrelname AS index_a,
    b.indexrelname AS index_b,
    pg_size_pretty(pg_relation_size(a.indexrelid)) AS size_a,
    pg_size_pretty(pg_relation_size(b.indexrelid)) AS size_b
FROM pg_stat_user_indexes a
JOIN pg_stat_user_indexes b
    ON a.relid = b.relid
    AND a.indexrelid < b.indexrelid
JOIN pg_class t ON t.oid = a.relid
JOIN pg_index ia ON ia.indexrelid = a.indexrelid
JOIN pg_index ib ON ib.indexrelid = b.indexrelid
WHERE a.schemaname = 'public'
  AND ia.indkey = ib.indkey
  AND ia.indisunique = ib.indisunique
ORDER BY pg_relation_size(a.indexrelid) DESC
"

echo ""
echo "Index-to-data size ratio by table:"
echo ""
run_query "
SELECT
    relname AS table_name,
    pg_size_pretty(pg_relation_size(relid)) AS data_size,
    pg_size_pretty(pg_total_relation_size(relid) - pg_relation_size(relid)) AS index_size,
    CASE WHEN pg_relation_size(relid) > 0
         THEN ROUND((pg_total_relation_size(relid) - pg_relation_size(relid))::numeric
                     / pg_relation_size(relid), 1)
    END AS index_to_data_ratio
FROM pg_stat_user_tables
WHERE schemaname = 'public'
  AND pg_relation_size(relid) > 1048576
ORDER BY index_to_data_ratio DESC NULLS LAST
"

# ==============================================================================
section "5. CONFIGURATION"
# ==============================================================================

echo "Key PostgreSQL settings:"
echo ""
run_query "
SELECT name, setting,
    CASE unit
        WHEN '8kB' THEN pg_size_pretty(setting::bigint * 8192)
        WHEN 'kB'  THEN pg_size_pretty(setting::bigint * 1024)
        WHEN 'MB'  THEN pg_size_pretty(setting::bigint * 1048576)
        ELSE COALESCE(unit, '')
    END AS effective_value,
    short_desc
FROM pg_settings
WHERE name IN (
    'shared_buffers', 'effective_cache_size', 'work_mem', 'maintenance_work_mem',
    'autovacuum', 'autovacuum_vacuum_scale_factor', 'autovacuum_analyze_scale_factor',
    'autovacuum_max_workers', 'autovacuum_naptime',
    'max_connections', 'max_logical_replication_workers',
    'wal_level', 'max_wal_size'
)
ORDER BY name
"

# Check for undersized settings
SHARED_BUFFERS_MB=$($PSQL -t -A -c "
SELECT setting::bigint * 8192 / 1048576 FROM pg_settings WHERE name = 'shared_buffers'
" 2>/dev/null || echo "0")
DB_SIZE_MB=$($PSQL -t -A -c "
SELECT pg_database_size(current_database()) / 1048576
" 2>/dev/null || echo "0")

if [ "$SHARED_BUFFERS_MB" -gt 0 ] && [ "$DB_SIZE_MB" -gt 0 ]; then
    RATIO=$((DB_SIZE_MB / SHARED_BUFFERS_MB))
    if [ "$RATIO" -gt 100 ]; then
        warn "SHARED_BUFFERS: ${SHARED_BUFFERS_MB} MB for a ${DB_SIZE_MB} MB database (${RATIO}:1 ratio — recommended <25:1)"
    fi
fi

MAINT_MEM=$($PSQL -t -A -c "
SELECT setting::bigint FROM pg_settings WHERE name = 'maintenance_work_mem'
" 2>/dev/null || echo "0")
if [ "$MAINT_MEM" -gt 0 ] && [ "$MAINT_MEM" -lt 1048576 ]; then
    warn "MAINTENANCE_WORK_MEM: $(($MAINT_MEM / 1024)) MB — low for vacuuming a $(($DB_SIZE_MB / 1024)) GB database (recommend 1-2 GB)"
fi

# ==============================================================================
section "6. ACTIVE CONNECTIONS"
# ==============================================================================

run_query "
SELECT
    usename AS user,
    application_name AS app,
    client_addr,
    state,
    CASE
        WHEN state = 'active' THEN ROUND(EXTRACT(EPOCH FROM (now() - query_start))::numeric, 0) || 's'
        WHEN state = 'idle' THEN ROUND(EXTRACT(EPOCH FROM (now() - state_change))::numeric, 0) || 's'
        ELSE '-'
    END AS duration,
    LEFT(query, 60) AS query_preview
FROM pg_stat_activity
WHERE datname = current_database()
  AND pid != pg_backend_pid()
ORDER BY state, query_start
"

# ==============================================================================
section "7. SCHEMA FINGERPRINT"
# ==============================================================================

echo "Column counts per table (use to detect schema changes):"
echo ""
run_query "
SELECT table_name,
       COUNT(*) AS columns,
       STRING_AGG(column_name, ',' ORDER BY ordinal_position) AS column_list_hash
FROM information_schema.columns
WHERE table_schema = 'public'
GROUP BY table_name
ORDER BY table_name
"

# ==============================================================================
section "8. RECENT DATA CURRENCY"
# ==============================================================================

echo "Most recent timestamps per key table (indicates data freshness):"
echo ""

# Use indexed columns for efficient lookups
run_query "
SELECT 'obs_sbn (created_at)' AS source,
       MAX(created_at)::text AS latest,
       ROUND(EXTRACT(EPOCH FROM (now() - MAX(created_at))) / 3600, 1) || ' hrs ago' AS age
FROM obs_sbn
WHERE created_at > now() - INTERVAL '7 days'

UNION ALL
SELECT 'mpc_orbits (updated_at)',
       MAX(updated_at)::text,
       ROUND(EXTRACT(EPOCH FROM (now() - MAX(updated_at))) / 3600, 1) || ' hrs ago'
FROM mpc_orbits

UNION ALL
SELECT 'numbered_identifications (updated_at)',
       MAX(updated_at)::text,
       ROUND(EXTRACT(EPOCH FROM (now() - MAX(updated_at))) / 3600, 1) || ' hrs ago'
FROM numbered_identifications

UNION ALL
SELECT 'neocp_obs (updated_at)',
       MAX(updated_at)::text,
       ROUND(EXTRACT(EPOCH FROM (now() - MAX(updated_at))) / 3600, 1) || ' hrs ago'
FROM neocp_obs

UNION ALL
SELECT 'neocp_events (updated_at)',
       MAX(updated_at)::text,
       ROUND(EXTRACT(EPOCH FROM (now() - MAX(updated_at))) / 3600, 1) || ' hrs ago'
FROM neocp_events

ORDER BY source
"

# ==============================================================================
section "9. WARNINGS SUMMARY"
# ==============================================================================

WARN_COUNT=$(wc -l < "$WARN_FILE" | tr -d ' ')
if [ "$WARN_COUNT" -eq 0 ]; then
    echo "  No warnings — all checks passed."
else
    echo "  ${WARN_COUNT} warning(s) found:"
    echo ""
    nl -ba -s '] ' "$WARN_FILE" | sed 's/^  *\([0-9]\)/  [\1/'
fi

echo ""
echo "--- End of report ---"
