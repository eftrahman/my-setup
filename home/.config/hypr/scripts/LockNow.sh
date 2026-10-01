#!/usr/bin/env bash

# Entry point used by Hypridle whenever logind asks the session to lock.

"$HOME/.config/hypr/scripts/LockConfirm.sh" clear
pidof hyprlock >/dev/null || exec hyprlock
