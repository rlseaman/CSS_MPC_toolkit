#!/usr/bin/env bash
# ==============================================================================
# NEO Discovery Tracklets Pipeline
# ==============================================================================
# Runs the discovery tracklets SQL query against the MPC/SBN PostgreSQL
# database, validates the output, and optionally uploads the CSV to GitHub
# Releases.  The SQL is self-contained — the NEO list is derived directly
# from the mpc_orbits table, with no external file dependencies.
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

# Paths (relative to repository root)
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
SQL_FILE="$REPO_DIR/sql/discovery_tracklets.sql"
VALIDATE_SCRIPT="$REPO_DIR/scripts/validate_output.sh"

# Working files
WORK_DIR=$(mktemp -d)
OUTPUT_CSV="$WORK_DIR/NEO_discovery_tracklets.csv"

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

# --- Step 1: Run SQL ----------------------------------------------------------

log "Running discovery tracklets query..."
PSQL_ARGS=(-h "$PGHOST" -d "$PGDATABASE" --csv -f "$SQL_FILE" -o "$OUTPUT_CSV")
[ -n "$PGUSER" ] && PSQL_ARGS+=(-U "$PGUSER")

psql "${PSQL_ARGS[@]}" || die "SQL query failed"

log "Query complete. Output: $OUTPUT_CSV"

# --- Step 2: Validate output --------------------------------------------------

log "Validating output..."
if [ -x "$VALIDATE_SCRIPT" ]; then
    "$VALIDATE_SCRIPT" "$OUTPUT_CSV" || die "Validation failed"
else
    log "WARNING: validate_output.sh not found or not executable, skipping validation"
fi

# --- Step 3: Copy to final location -------------------------------------------

FINAL_CSV="$REPO_DIR/NEO_discovery_tracklets.csv"
cp "$OUTPUT_CSV" "$FINAL_CSV"
log "Output copied to $FINAL_CSV"

# --- Step 4: Upload to GitHub Releases (optional) -----------------------------

if [ "$DO_UPLOAD" = true ]; then
    log "Uploading to GitHub Releases..."
    "$REPO_DIR/scripts/upload_release.sh" "$FINAL_CSV" || die "Upload failed"
fi

# --- Summary ------------------------------------------------------------------

OUTPUT_LINES=$(wc -l < "$FINAL_CSV" | tr -d ' ')
log "Pipeline complete. $OUTPUT_LINES rows (including header) written."
