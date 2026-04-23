#!/bin/bash
# Run dashboard --refresh-only with per-line elapsed/delta timestamps.
# Env:
#   PGHOST   — where to query (sibyl, /tmp, etc.)
#   LABEL    — identifier used in output filename
#   OUTDIR   — where to write the log (default ./logs)

LABEL="${LABEL:-host}"
OUTDIR="${OUTDIR:-./logs}"
PROJECT_DIR="${PROJECT_DIR:-$(pwd)}"

mkdir -p "$OUTDIR"
OUT="$OUTDIR/refresh_timed_${LABEL}_$(date +%Y%m%d_%H%M%S).log"

cd "$PROJECT_DIR" || exit 1

{
  echo "=== run_refresh_timed ==="
  echo "LABEL=$LABEL  PGHOST=$PGHOST  PROJECT_DIR=$PROJECT_DIR"
  echo "started $(date '+%Y-%m-%d %H:%M:%S.%N')"
  echo ""
} > "$OUT"

./venv/bin/python -u app/discovery_stats.py --refresh-only 2>&1 | \
  ./venv/bin/python -c "
import sys, time
start = time.time()
prev = start
for line in sys.stdin:
    now = time.time()
    el    = now - start
    delta = now - prev
    prev  = now
    sys.stdout.write(f'[{el:7.1f}s  +{delta:5.1f}s] {line}')
    sys.stdout.flush()
" >> "$OUT"

echo "=== finished $(date '+%Y-%m-%d %H:%M:%S.%N') ===" >> "$OUT"
echo "$OUT"
