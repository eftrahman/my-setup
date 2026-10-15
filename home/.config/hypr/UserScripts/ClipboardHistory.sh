#!/usr/bin/env bash

# Launch the visual clipboard library. Kept as a wrapper so existing keybinds
# and external callers continue to work.
exec python3 "$HOME/.config/hypr/scripts/ClipboardLibrary.py"
