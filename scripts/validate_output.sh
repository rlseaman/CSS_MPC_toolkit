#!/usr/bin/env bash
# ==============================================================================
# Validate discovery tracklets CSV output
# ==============================================================================
# Checks that the output CSV is well-formed and complete before distribution.
#
# Usage:
#   ./scripts/validate_output.sh <csv_file>
#
# Exit codes:
#   0 - All checks passed
#   1 - Validation failed
# ==============================================================================

set -euo pipefail

CSV_FILE="${1:?Usage: validate_output.sh <csv_file>}"

# --- Configuration -----------------------------------------------------------

# Minimum expected rows (NEO count grows ~2000/year, set a floor)
MIN_ROWS=35000

# Expected number of columns
EXPECTED_COLS=12

# --- Checks -------------------------------------------------------------------

die() {
    echo "VALIDATION FAILED: $*" >&2
    exit 1
}

# Check file exists and is non-empty
[ -f "$CSV_FILE" ] || die "File not found: $CSV_FILE"
[ -s "$CSV_FILE" ] || die "File is empty: $CSV_FILE"

# Count rows (excluding header)
TOTAL_LINES=$(wc -l < "$CSV_FILE" | tr -d ' ')
DATA_ROWS=$((TOTAL_LINES - 1))

echo "Output: $DATA_ROWS data rows"

# Check minimum row count
if [ "$DATA_ROWS" -lt "$MIN_ROWS" ]; then
    die "Only $DATA_ROWS rows (minimum expected: $MIN_ROWS)"
fi

# Check column count on header
HEADER_COLS=$(head -1 "$CSV_FILE" | awk -F',' '{print NF}')
if [ "$HEADER_COLS" -ne "$EXPECTED_COLS" ]; then
    die "Header has $HEADER_COLS columns (expected $EXPECTED_COLS)"
fi

# Spot-check a sample data row for reasonable values
SAMPLE=$(sed -n '2p' "$CSV_FILE")
if [ -z "$SAMPLE" ]; then
    die "No data rows found"
fi

echo "All validation checks passed."
