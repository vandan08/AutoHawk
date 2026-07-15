#!/bin/sh
# Runs the AutoHawk pipeline on a fixed interval (default: every 24 hours).
# Override with AUTOHAWK_INTERVAL_HOURS. Set it to 0 to run once and exit.

set -u
INTERVAL="${AUTOHAWK_INTERVAL_HOURS:-24}"
PROFILE="/data/profile.yaml"

if [ ! -f "$PROFILE" ]; then
    echo "No $PROFILE found — copying template. Edit it, then restart the container."
    cp /app/profile.example.yaml "$PROFILE"
    exit 1
fi

while true; do
    echo "=== AutoHawk run: $(date -u +%FT%TZ) ==="
    autohawk fetch -p "$PROFILE"   || echo "fetch failed (continuing)"
    autohawk score -p "$PROFILE"   || echo "score failed (continuing)"
    autohawk report                || echo "report failed (continuing)"
    autohawk status                || true

    if [ "$INTERVAL" = "0" ]; then
        echo "AUTOHAWK_INTERVAL_HOURS=0 — single run complete, exiting."
        exit 0
    fi
    echo "Sleeping ${INTERVAL}h until the next run..."
    sleep "$((INTERVAL * 3600))"
done
