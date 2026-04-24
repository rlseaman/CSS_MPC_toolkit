#!/bin/bash
# head_to_head.sh — speed + content reality-check for Gizmo vs Sibyl.
#
# Runs sql/benchmarks/bench_app_queries.sql against three configurations:
#   1. Gizmo, source=obs_sbn_neo  (dashboard's production path)
#   2. Gizmo, source=obs_sbn      (isolates matview effect)
#   3. Sibyl, source=obs_sbn      (baseline; no matview)
#
# Emits a side-by-side speed table and a content-fingerprint diff. A
# mismatched fingerprint at the same row count is a real divergence; a
# small row-count delta (few hundred out of ~41K NEO rows, ~370K
# apparition rows, ~1.5M boxscore rows) is expected replication drift.
#
# Prereqs:
#   - ssh access to robertseaman@192.168.0.157 (Gizmo)
#   - ~/.pgpass entry for claude_ro on sibyl
#   - BOTH subscribers reasonably caught up (this is not a frozen-LSN
#     compare; expect small drift)
#
# Usage:
#   ./scripts/head_to_head.sh [outdir]
# Default outdir: /tmp/head_to_head_<timestamp>

set -o pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
SQL="$PROJECT_DIR/sql/benchmarks/bench_app_queries.sql"
GIZMO_HOST=robertseaman@192.168.0.157
GIZMO_PSQL=/opt/homebrew/bin/psql
SIBYL_PGHOST=sibyl
OUTDIR="${1:-/tmp/head_to_head_$(date +%Y%m%d_%H%M%S)}"

if [[ ! -f "$SQL" ]]; then
    echo "missing $SQL" >&2
    exit 2
fi
mkdir -p "$OUTDIR"

echo "=== head_to_head.sh → $OUTDIR ==="

run_gizmo() {
    local source="$1" out="$2"
    echo "-- Gizmo, source=$source"
    scp -q "$SQL" "$GIZMO_HOST:/tmp/bench_app_queries.sql"
    ssh "$GIZMO_HOST" "bash -lc 'PGHOST=/tmp $GIZMO_PSQL -d mpc_sbn -v source=$source -f /tmp/bench_app_queries.sql'" > "$out" 2>&1
    ssh "$GIZMO_HOST" "rm -f /tmp/bench_app_queries.sql"
}

run_sibyl() {
    local source="$1" out="$2"
    echo "-- Sibyl, source=$source"
    PGHOST=$SIBYL_PGHOST psql -U claude_ro -d mpc_sbn -v source="$source" -f "$SQL" \
        > "$out" 2>&1
}

run_gizmo obs_sbn_neo "$OUTDIR/gizmo_neo.txt"
run_gizmo obs_sbn     "$OUTDIR/gizmo_raw.txt"
run_sibyl obs_sbn     "$OUTDIR/sibyl_raw.txt"

echo
echo "=== Fingerprints (row counts + content hashes) ==="
for f in "$OUTDIR"/{gizmo_neo,gizmo_raw,sibyl_raw}.txt; do
    echo "--- $(basename "$f") ---"
    grep '^FP' "$f" | column -t -s '|'
done

echo
echo "=== Timings (wall clock per query) ==="
for f in "$OUTDIR"/{gizmo_neo,gizmo_raw,sibyl_raw}.txt; do
    echo "--- $(basename "$f") ---"
    # psql \timing outputs "Time: <ms>" after each statement. Surface them
    # alongside the query they measured by printing the preceding \echo
    # header too.
    grep -E '^(###|Time:)' "$f"
done

echo
echo "=== Content diff: row counts + content_hash ==="
# Sort-free compare — same FP order in all three files.
diff "$OUTDIR/gizmo_neo.txt" "$OUTDIR/sibyl_raw.txt" \
    | grep '^[<>].*FP' || echo "(no FP divergence beyond replication drift)"

echo
echo "Full output in: $OUTDIR"
