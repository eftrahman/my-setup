#!/usr/bin/env bash

# Yes/No confirmation state for Hyprlock's session-ending controls.

set -u

runtime_dir="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
state_file="$runtime_dir/hyprlock-confirm-action"
lock_file="$runtime_dir/hyprlock-confirm-action.lock"
confirm_window=20

read_state() {
    pending_action=""
    pending_at="0"

    if [[ -r "$state_file" ]]; then
        read -r pending_action pending_at < "$state_file" || true
    fi

    [[ "$pending_at" =~ ^[0-9]+$ ]] || pending_at=0
}

action_label() {
    case "$1" in
        logout) printf 'LOG OUT' ;;
        reboot) printf 'RESTART' ;;
        poweroff) printf 'SHUTDOWN' ;;
        *) printf 'UNKNOWN ACTION' ;;
    esac
}

status_text() {
    local now elapsed
    now="$(date +%s)"
    read_state
    elapsed=$((now - pending_at))

    if (( pending_at > 0 && elapsed >= 0 && elapsed <= confirm_window )); then
        printf 'CONFIRM %s?\n' "$(action_label "$pending_action")"
    else
        printf 'SELECT A SYSTEM ACTION\n'
    fi
}

case "${1:-status}" in
    status)
        status_text
        exit 0
        ;;
    select)
        case "${2:-}" in
            logout|reboot|poweroff) selected_action="$2" ;;
            *) exit 2 ;;
        esac

        exec 9>"$lock_file"
        flock -x 9
        printf '%s %s\n' "$selected_action" "$(date +%s)" > "$state_file"
        chmod 600 "$state_file"
        exit 0
        ;;
    no|cancel|clear)
        rm -f -- "$state_file"
        exit 0
        ;;
    yes|confirm)
        ;;
    *)
        exit 2
        ;;
esac

exec 9>"$lock_file"
flock -x 9

now="$(date +%s)"
read_state
elapsed=$((now - pending_at))

if (( pending_at == 0 || elapsed < 0 || elapsed > confirm_window )); then
    rm -f -- "$state_file"
    exit 0
fi

case "$pending_action" in
    logout|reboot|poweroff) ;;
    *)
        rm -f -- "$state_file"
        exit 2
        ;;
esac

rm -f -- "$state_file"

case "$pending_action" in
    logout) hyprctl dispatch exit 0 ;;
    reboot) systemctl reboot ;;
    poweroff) systemctl poweroff ;;
esac
