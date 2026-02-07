#!/usr/bin/env bash
# ==============================================================================
# NEA Discovery Tracklets Pipeline
# ==============================================================================
# Downloads NEA.txt, runs the discovery tracklets SQL query, validates the
# output, and optionally uploads the CSV to GitHub Releases.
#
# Usage:
#   ./scripts/run_pipeline.sh                  # Run with defaults
#   ./scripts/run_pipeline.sh --upload         # Run and upload to GitHub
#   ./scripts/run_pipeline.sh --help           # Show usage
#
# Configuration:
#   Set environment variables or edit the defaults below.
# ==============================================================================

set -euo pipefail

# --- Configuration -----------------------------------------------------------

# Database connection (override with environment variables)
PGHOST="${PGHOST:-localhost}"
PGDATABASE="${PGDATABASE:-mpc_sbn}"
PGUSER="${PGUSER:-}"

# URLs
NEA_TXT_URL="https://minorplanetcenter.net/iau/MPCORB/NEA.txt"

# Paths (relative to repository root)
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
SQL_FILE="$REPO_DIR/sql/discovery_tracklets.sql"
VALIDATE_SCRIPT="$REPO_DIR/scripts/validate_output.sh"

# Working files
WORK_DIR=$(mktemp -d)
NEA_TXT="$WORK_DIR/NEA.txt"
OUTPUT_CSV="$WORK_DIR/NEA_discovery_tracklets.csv"
SQL_TEMP="$WORK_DIR/discovery_tracklets_run.sql"

# Options
DO_UPLOAD=false

# --- Functions ----------------------------------------------------------------

usage() {
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  --upload     Upload CSV to GitHub Releases after successful run"
    echo "  --help       Show this help message"
    echo ""
    echo "Environment variables:"
    echo "  PGHOST       Database host (default: localhost)"
    echo "  PGDATABASE   Database name (default: mpc_sbn)"
    echo "  PGUSER       Database user (default: current user)"
}

cleanup() {
    rm -rf "$WORK_DIR"
}
trap cleanup EXIT

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"
}

die() {
    log "ERROR: $*" >&2
    exit 1
}

# --- Parse arguments ----------------------------------------------------------

while [[ $# -gt 0 ]]; do
    case "$1" in
        --upload) DO_UPLOAD=true; shift ;;
        --help)   usage; exit 0 ;;
        *)        die "Unknown option: $1" ;;
    esac
done

# --- Step 1: Download NEA.txt ------------------------------------------------

log "Downloading NEA.txt..."
curl -sSf -o "$NEA_TXT" "$NEA_TXT_URL" || die "Failed to download NEA.txt"

NEA_LINES=$(wc -l < "$NEA_TXT" | tr -d ' ')
NEA_SIZE=$(wc -c < "$NEA_TXT" | tr -d ' ')
log "Downloaded NEA.txt: $NEA_LINES lines, $NEA_SIZE bytes"

# Basic input validation
if [ "$NEA_LINES" -lt 30000 ]; then
    die "NEA.txt has only $NEA_LINES lines (expected 30000+). Download may be truncated."
fi

# --- Step 2: Prepare and run SQL ----------------------------------------------

log "Preparing SQL query..."

# Copy SQL and replace the \copy path with the actual download location
sed "s|\\\\copy nea_txt_import(raw_line) FROM '/tmp/NEA.txt'|\\\\copy nea_txt_import(raw_line) FROM '$NEA_TXT'|" \
    "$SQL_FILE" > "$SQL_TEMP"

log "Running discovery tracklets query..."
PSQL_ARGS=(-h "$PGHOST" -d "$PGDATABASE" --csv -f "$SQL_TEMP" -o "$OUTPUT_CSV")
[ -n "$PGUSER" ] && PSQL_ARGS+=(-U "$PGUSER")

psql "${PSQL_ARGS[@]}" || die "SQL query failed"

log "Query complete. Output: $OUTPUT_CSV"

# --- Step 3: Validate output --------------------------------------------------

log "Validating output..."
if [ -x "$VALIDATE_SCRIPT" ]; then
    "$VALIDATE_SCRIPT" "$OUTPUT_CSV" "$NEA_LINES" || die "Validation failed"
else
    log "WARNING: validate_output.sh not found or not executable, skipping validation"
fi

# --- Step 4: Copy to final location -------------------------------------------

FINAL_CSV="$REPO_DIR/NEA_discovery_tracklets.csv"
cp "$OUTPUT_CSV" "$FINAL_CSV"
log "Output copied to $FINAL_CSV"

# --- Step 5: Upload to GitHub Releases (optional) -----------------------------

if [ "$DO_UPLOAD" = true ]; then
    log "Uploading to GitHub Releases..."
    "$REPO_DIR/scripts/upload_release.sh" "$FINAL_CSV" || die "Upload failed"
fi

# --- Summary ------------------------------------------------------------------

OUTPUT_LINES=$(wc -l < "$FINAL_CSV" | tr -d ' ')
log "Pipeline complete. $OUTPUT_LINES rows (including header) written."
log "Input: $NEA_LINES NEAs in NEA.txt"
