#!/usr/bin/env bash
# ==============================================================================
# Upload CSV to GitHub Releases
# ==============================================================================
# Uploads (or replaces) a CSV file as a GitHub Release asset on the "latest"
# release. Creates the release if it doesn't exist.
#
# Usage:
#   ./scripts/upload_release.sh <csv_file>
#
# Requires: gh CLI (https://cli.github.com/) authenticated with appropriate
# permissions.
# ==============================================================================

set -euo pipefail

CSV_FILE="${1:?Usage: upload_release.sh <csv_file>}"
REPO="rlseaman/CSS_SBN_derived"
TAG="latest"
DATE=$(date '+%Y-%m-%d')

# --- Functions ----------------------------------------------------------------

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"
}

die() {
    log "ERROR: $*" >&2
    exit 1
}

# --- Preflight ----------------------------------------------------------------

[ -f "$CSV_FILE" ] || die "File not found: $CSV_FILE"
command -v gh >/dev/null 2>&1 || die "gh CLI not found. Install from https://cli.github.com/"

# --- Create or update release -------------------------------------------------

# Check if the release exists
if gh release view "$TAG" --repo "$REPO" >/dev/null 2>&1; then
    log "Updating existing '$TAG' release..."
    gh release upload "$TAG" "$CSV_FILE" \
        --repo "$REPO" \
        --clobber
    # Update the release title with the current date
    gh release edit "$TAG" \
        --repo "$REPO" \
        --title "Latest data products ($DATE)"
else
    log "Creating '$TAG' release..."
    gh release create "$TAG" "$CSV_FILE" \
        --repo "$REPO" \
        --title "Latest data products ($DATE)" \
        --notes "Automatically generated NEA discovery tracklet statistics.

Updated: $DATE

See [schema documentation](https://github.com/$REPO/blob/main/schema/discovery_tracklets.md) for column descriptions."
fi

log "Upload complete: $CSV_FILE -> $REPO release '$TAG'"
