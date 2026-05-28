#!/bin/bash
# apireq_summary.sh — daily tally of outbound APIREQ counts.
#
# Reads dashboard launchd logs under $HOME/Claude/mpc_sbn/logs and writes
# a flat text summary alongside them.  Designed as stage 6 of
# refresh_matview_gizmo.sh — runs right after the Dash restart, so
# today's date-named log is essentially empty and yesterday's date-named
# log carries the trailing 24 h of traffic.  Also safe to run by hand.
#
# Output: $LOG_DIR/apireq_summary_YYYYMMDD.txt
#
# Week-1 behaviour: emit the summary only.  No alerts.  After ~1–2 weeks
# of baseline observation, enable the threshold block at the end with
# values set to ~3x the observed 95th-percentile per-host daily count.
#
# Exit codes:
#   0 — summary written, or no logs found (silently)
#   1 — internal failure (e.g. cannot write OUT)

set -o pipefail

LOG_DIR="${LOG_DIR:-$HOME/Claude/mpc_sbn/logs}"
TODAY=$(date '+%Y%m%d')
# macOS uses `date -v-1d`; GNU coreutils uses `date -d 'yesterday'`.
YESTERDAY=$(date -v-1d '+%Y%m%d' 2>/dev/null \
            || date -d 'yesterday' '+%Y%m%d' 2>/dev/null)

OUT="$LOG_DIR/apireq_summary_${TODAY}.txt"

shopt -s nullglob
files=( "$LOG_DIR"/dashboard_${TODAY}*.log
        "$LOG_DIR"/dashboard_${YESTERDAY}*.log )
shopt -u nullglob

if [[ ${#files[@]} -eq 0 ]]; then
    echo "apireq_summary: no dashboard logs in $LOG_DIR" >&2
    exit 0
fi

# Build the summary atomically so a half-written file is never visible.
TMP_OUT="${OUT}.tmp.$$"
{
    printf 'APIREQ summary — generated %s UTC\n' \
           "$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
    printf 'LOG_DIR=%s\n\n' "$LOG_DIR"

    printf 'Source logs in this window:\n'
    for f in "${files[@]}"; do
        n=$(grep -c '^APIREQ' "$f" 2>/dev/null)
        printf '  %-60s  %6d APIREQ\n' "$(basename "$f")" "$n"
    done
    printf '\n'

    total=$(cat "${files[@]}" 2>/dev/null | grep -c '^APIREQ')
    neg=$(cat "${files[@]}" 2>/dev/null | grep -c 'API neg-cache')
    printf 'Total APIREQ lines this window: %d\n' "$total"
    printf 'Total neg-cache suppressions:   %d\n\n' "$neg"

    printf '===== per host x outcome =====\n'
    cat "${files[@]}" 2>/dev/null \
        | grep '^APIREQ' \
        | sed -E 's/.*host=([^ ]+) outcome=([^ ]+).*/\1 \2/' \
        | sort | uniq -c | sort -rn
    printf '\n'

    printf '===== per host (totals) =====\n'
    cat "${files[@]}" 2>/dev/null \
        | grep '^APIREQ' \
        | sed -E 's/.*host=([^ ]+).*/\1/' \
        | sort | uniq -c | sort -rn
    printf '\n'

    printf '===== top neg-cache suppression keys =====\n'
    cat "${files[@]}" 2>/dev/null \
        | grep 'API neg-cache' \
        | sed -E 's/.*API neg-cache \[([^]]+)\].*/\1/' \
        | sort | uniq -c | sort -rn | head -10

} > "$TMP_OUT" || { rm -f "$TMP_OUT"; echo "apireq_summary: write failed" >&2; exit 1; }
mv "$TMP_OUT" "$OUT"

echo "apireq_summary: wrote $OUT ($(wc -l <"$OUT" | tr -d ' ') lines)"

# --- Alert block (DISABLED week 1) ----------------------------------------
# Enable after baseline observation.  Set per-host thresholds to ~3x the
# observed 95th-percentile daily count.  Example for JPL:
#
#   awk '$2 == "ssd-api.jpl.nasa.gov" && $1 > 5000 {hit=1}
#        END{exit !hit}' "$OUT" \
#     && mail -s "APIREQ: JPL daily volume above threshold" \
#             contact@hotwireduniverse.org < "$OUT"
# --------------------------------------------------------------------------

exit 0
