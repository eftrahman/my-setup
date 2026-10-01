#!/usr/bin/env bash

# Start/cancel an exact one-minute suspend timer based on lock state.

set -u

unit="hyprlock-auto-suspend"
self="$HOME/.config/hypr/scripts/LockSuspend.sh"

cancel_timer() {
    systemctl --user stop "$unit.timer" "$unit.service" >/dev/null 2>&1 || true
    systemctl --user reset-failed "$unit.timer" "$unit.service" >/dev/null 2>&1 || true
}

case "${1:-}" in
    arm)
        cancel_timer
        systemd-run --user --quiet --collect \
            --unit="$unit" \
            --on-active=60s \
            --timer-property=AccuracySec=1s \
            "$self" fire
        ;;
    cancel)
        cancel_timer
        ;;
    fire)
        # Never suspend if the user has already unlocked.
        pidof hyprlock >/dev/null || exit 0
        systemctl suspend
        ;;
    *)
        exit 2
        ;;
esac
