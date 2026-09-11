#!/bin/bash
# usage_summary.sh — daily roll-up of inbound REQ lines (dashboard usage).
#
# Sister of apireq_summary.sh: reads the dashboard launchd logs under
# $HOME/Claude/mpc_sbn/logs for today + yesterday (the nightly restart
# rotates the log at ~06:15, so "yesterday's" file carries the trailing
# 24 h) and writes a flat text summary. Runs as stage 6 of
# refresh_matview_gizmo.sh; safe to run by hand.
#
# REQ line format (app/discovery_stats.py → _reqlog_line):
#   REQ ts=<UTC> vid=<8hex> cc=<CC> dev=<bot|mobile|desktop|none>
#       <METHOD> <path> <status> ms=<n> tab=<tab-id|-> trig=<props|init|->
#       out=<output-id|->
# vid is a salted hash that rotates with each restart — "unique visitors"
# below means unique per log file, roughly per day.
#
# Output: $LOG_DIR/usage_summary_YYYYMMDD.txt
# Exit: 0 (also when no logs / no REQ lines), 1 on write failure.

set -o pipefail

LOG_DIR="${LOG_DIR:-$HOME/Claude/mpc_sbn/logs}"
TODAY=$(date '+%Y%m%d')
YESTERDAY=$(date -v-1d '+%Y%m%d' 2>/dev/null \
            || date -d 'yesterday' '+%Y%m%d' 2>/dev/null)
OUT="$LOG_DIR/usage_summary_${TODAY}.txt"

shopt -s nullglob
# prod logs only (dashboard_<stamp>.log); the dev instance writes
# dashboard-rnd_<stamp>.log and is behind Cloudflare Access.
files=( "$LOG_DIR"/dashboard_${TODAY}_*.log
        "$LOG_DIR"/dashboard_${YESTERDAY}_*.log )
shopt -u nullglob

if [[ ${#files[@]} -eq 0 ]]; then
    echo "usage_summary: no dashboard logs in $LOG_DIR" >&2
    exit 0
fi

req() { cat "${files[@]}" 2>/dev/null | grep '^REQ '; }
field() { sed -E "s/.* $1=([^ ]*).*/\1/"; }   # extract key=value field
humans() { grep -v ' dev=bot ' | grep -v ' dev=none '; }

TMP_OUT="${OUT}.tmp.$$"
{
    printf 'USAGE summary — generated %s UTC\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
    printf 'LOG_DIR=%s\n\n' "$LOG_DIR"

    printf 'Source logs in this window:\n'
    for f in "${files[@]}"; do
        printf '  %-60s  %6d REQ\n' "$(basename "$f")" "$(grep -c '^REQ ' "$f")"
    done
    printf '\n'

    total=$(req | wc -l | tr -d ' ')
    human=$(req | humans | wc -l | tr -d ' ')
    loads=$(req | humans | grep -c ' GET / 200 ')
    visitors=$(req | humans | field vid | sort -u | wc -l | tr -d ' ')
    callbacks=$(req | humans | grep -c ' POST /_dash-update-component ')
    printf 'Requests (all):            %6d\n' "$total"
    printf 'Requests (humans):         %6d\n' "$human"
    printf 'Page loads (GET / 200):    %6d\n' "$loads"
    printf 'Unique visitors (humans):  %6d   (salted token; ~per day)\n' "$visitors"
    printf 'Dash callbacks (humans):   %6d\n\n' "$callbacks"

    printf '===== device class (all requests) =====\n'
    req | field dev | sort | uniq -c | sort -rn
    printf '\n===== country (human page loads) =====\n'
    req | humans | grep ' GET / 200 ' | field cc | sort | uniq -c | sort -rn | head -15
    printf '\n===== visitors x page loads (humans, top 15) =====\n'
    req | humans | grep ' GET / 200 ' | field vid | sort | uniq -c | sort -rn | head -15
    printf '\n===== tab switches (humans; trig=tabs.value) =====\n'
    req | humans | grep ' trig=tabs.value ' | field tab | sort | uniq -c | sort -rn
    printf '\n===== callbacks by active tab (humans) =====\n'
    req | humans | grep ' POST /_dash-update-component ' | field tab | sort | uniq -c | sort -rn
    printf '\n===== top triggers (humans, top 25) =====\n'
    req | humans | grep ' POST /_dash-update-component ' | field trig | sort | uniq -c | sort -rn | head -25
    printf '\n===== non-2xx responses =====\n'
    req | awk '{for(i=1;i<=NF;i++) if($i ~ /^\/|^\/_/){print $(i-1), $i, $(i+1); break}}' \
        | awk '$3 !~ /^2/' | sort | uniq -c | sort -rn | head -15
    printf '\n===== slowest callbacks (ms, top 10) =====\n'
    req | grep ' POST /_dash-update-component ' \
        | sed -E 's/.* ms=([0-9]+) tab=([^ ]*) trig=([^ ]*).*/\1 \2 \3/' \
        | sort -rn | head -10
    printf '\n===== bots: paths (top 10) =====\n'
    req | grep ' dev=bot ' | awk '{print $6, $7}' | sort | uniq -c | sort -rn | head -10
} > "$TMP_OUT" || { rm -f "$TMP_OUT"; echo "usage_summary: write failed" >&2; exit 1; }
mv "$TMP_OUT" "$OUT"
echo "usage_summary: wrote $OUT ($(wc -l <"$OUT" | tr -d ' ') lines)"
exit 0
