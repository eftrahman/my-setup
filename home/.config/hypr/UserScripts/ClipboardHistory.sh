#!/usr/bin/env bash

# Polished clipboard history picker for Hyprland.
# Enter restores the selected item to the clipboard; paste normally with Ctrl+V.

theme="$HOME/.config/rofi/config-clipboard-history.rasi"
footer='<b>Enter</b>  copy selection    <b>Ctrl+Del</b>  remove    <b>Alt+Del</b>  clear all    <b>Esc</b>  close'

for dependency in cliphist rofi wl-copy; do
    if ! command -v "$dependency" >/dev/null 2>&1; then
        notify-send -u critical "Clipboard history" "Missing required command: $dependency"
        exit 1
    fi
done

# Replace another open Rofi menu instead of stacking popups.
if pgrep -x rofi >/dev/null 2>&1; then
    pkill -x rofi
    sleep 0.08
fi

while true; do
    selection=$(
        cliphist list | rofi \
            -dmenu \
            -i \
            -matching fuzzy \
            -no-custom \
            -display-columns 2 \
            -selected-row 0 \
            -p "Clipboard" \
            -kb-custom-1 "Control-Delete" \
            -kb-custom-2 "Alt-Delete" \
            -config "$theme" \
            -mesg "$footer"
    )
    status=$?

    case "$status" in
        0)
            if [[ -n "$selection" ]]; then
                cliphist decode <<<"$selection" | wl-copy
            fi
            exit 0
            ;;
        1)
            exit 0
            ;;
        10)
            if [[ -n "$selection" ]]; then
                cliphist delete <<<"$selection"
            fi
            ;;
        11)
            confirmation=$(
                printf '%s\n' "Keep history" "Clear all history" | rofi \
                    -dmenu \
                    -no-custom \
                    -selected-row 0 \
                    -p "Clear clipboard?" \
                    -config "$theme" \
                    -theme-str 'window { width: 430px; } listview { lines: 2; } message { enabled: false; }'
            )
            if [[ "$confirmation" == "Clear all history" ]]; then
                cliphist wipe
                notify-send -u low "Clipboard history" "History cleared"
                exit 0
            fi
            ;;
        *)
            exit 0
            ;;
    esac
done
