#!/bin/bash
# Wait for the data1 volume to be mounted before starting PostgreSQL.
# Used by the custom launchd plist to avoid crash-looping on boot.

DATA_DIR="/Volumes/data1/postgresql@18"
MAX_WAIT=120
WAITED=0

while [ ! -f "$DATA_DIR/PG_VERSION" ]; do
    sleep 2
    WAITED=$((WAITED + 2))
    if [ "$WAITED" -ge "$MAX_WAIT" ]; then
        echo "Timed out waiting for $DATA_DIR after ${MAX_WAIT}s" >&2
        exit 1
    fi
done

exec /opt/homebrew/opt/postgresql@18/bin/postgres -D /opt/homebrew/var/postgresql@18
