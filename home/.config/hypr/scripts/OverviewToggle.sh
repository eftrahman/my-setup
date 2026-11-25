#!/usr/bin/env bash
# Super+A: toggle the workspace overview.
# Uses the built-in WorkspaceOverview.py; a Quickshell overview is used instead
# only if Quickshell is installed and its overview config exists.
set -uo pipefail

overview="$HOME/.config/hypr/scripts/WorkspaceOverview.py"

if command -v qs >/dev/null 2>&1 && [[ -d $HOME/.config/quickshell/overview ]]; then
  pgrep -x quickshell >/dev/null 2>&1 || { qs -c overview >/dev/null 2>&1 & sleep 0.6; }
  qs ipc -c overview call overview toggle >/dev/null 2>&1 && exit 0
fi

if pkill -f '^python3 .*WorkspaceOverview\.py' 2>/dev/null; then
  exit 0
fi
exec python3 "$overview"
