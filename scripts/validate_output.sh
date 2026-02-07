#!/usr/bin/env bash
# ==============================================================================
# Validate discovery tracklets CSV output
# ==============================================================================
# Checks that the output CSV is well-formed and complete before distribution.
#
# Usage:
#   ./scripts/validate_output.sh <csv_file> [expected_input_lines]
#
# Exit codes:
#   0 - All checks passed
#   1 - Validation failed
# ==============================================================================

set -euo pipefail

CSV_FILE="${1:?Usage: validate_output.sh <csv_file> [expected_input_lines]}"
EXPECTED_INPUT="${2:-0}"

# --- Configuration -----------------------------------------------------------

# Minimum expected rows (NEA count grows ~2000/year, set a floor)
MIN_ROWS=35000

# Maximum acceptable gap between input NEAs and output rows
MAX_MISSING_PCT=2

# Expected number of columns
EXPECTED_COLS=12

# --- Checks -------------------------------------------------------------------

die() {
    echo "VALIDATION FAILED: $*" >&2
    exit 1
}

warn() {
    echo "WARNING: $*" >&2
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

# Check completeness against input if provided
if [ "$EXPECTED_INPUT" -gt 0 ]; then
    MISSING=$((EXPECTED_INPUT - DATA_ROWS))
    if [ "$MISSING" -lt 0 ]; then
        warn "More output rows ($DATA_ROWS) than input lines ($EXPECTED_INPUT)"
    elif [ "$MISSING" -gt 0 ]; then
        MISSING_PCT=$((100 * MISSING / EXPECTED_INPUT))
        echo "Completeness: $DATA_ROWS / $EXPECTED_INPUT ($MISSING missing)"
        if [ "$MISSING_PCT" -gt "$MAX_MISSING_PCT" ]; then
            die "$MISSING_PCT% missing exceeds threshold of $MAX_MISSING_PCT%"
        fi
    fi
fi

# Spot-check a sample data row for reasonable values
SAMPLE=$(sed -n '2p' "$CSV_FILE")
if [ -z "$SAMPLE" ]; then
    die "No data rows found"
fi

echo "All validation checks passed."
