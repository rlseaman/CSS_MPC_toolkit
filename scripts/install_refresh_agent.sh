#!/bin/bash
# Install the nightly-refresh LaunchAgent on the MBP.
#
#   - Copies scripts/org.seaman.css-refresh.plist into ~/Library/LaunchAgents/
#   - launchctl bootstrap'es it into the current GUI session
#   - Prints the (manual) pmset command you still need to run as root
#     to wake the MBP from sleep before the scheduled 05:30 firing.
#
# Re-run safely — unloads any existing agent with the same label first.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PLIST_SRC="$SCRIPT_DIR/org.seaman.css-refresh.plist"
PLIST_DST="$HOME/Library/LaunchAgents/org.seaman.css-refresh.plist"
LABEL=org.seaman.css-refresh
UID_NUM=$(id -u)

[[ -f "$PLIST_SRC" ]] || { echo "missing $PLIST_SRC" >&2; exit 1; }

# Validate plist syntax before installing.
plutil -lint "$PLIST_SRC"

# Unload any existing agent with the same label (safe if not loaded).
if launchctl print "gui/$UID_NUM/$LABEL" >/dev/null 2>&1; then
    echo "Unloading existing agent..."
    launchctl bootout "gui/$UID_NUM" "$PLIST_DST" || true
fi

# Install.
mkdir -p "$(dirname "$PLIST_DST")"
cp "$PLIST_SRC" "$PLIST_DST"
launchctl bootstrap "gui/$UID_NUM" "$PLIST_DST"

echo
echo "Installed. Verify:"
echo "  launchctl print gui/$UID_NUM/$LABEL"
echo
echo "To trigger manually (test run):"
echo "  launchctl start $LABEL"
echo
echo "To disable temporarily:"
echo "  launchctl disable gui/$UID_NUM/$LABEL"
echo "To enable again:"
echo "  launchctl enable gui/$UID_NUM/$LABEL"
echo
echo "-------------------------------------------------------------"
echo "Wake-on-schedule (run as root, one time):"
echo "  sudo pmset repeat wake MTWRFSU 05:25:00"
echo
echo "This wakes the MBP 5 min before the 05:30 launchd firing."
echo "Requires the MBP to be on AC power; if on battery the wake is"
echo "skipped and launchd defers the job to the next wake."
echo "-------------------------------------------------------------"
