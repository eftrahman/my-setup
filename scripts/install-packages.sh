#!/usr/bin/env bash
set -Eeuo pipefail
SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
# shellcheck source=scripts/lib.sh
source "$SCRIPT_DIR/lib.sh"
ROOT=$(repo_root)

base_packages=(ca-certificates curl fontconfig git jq kitty lsd rsync tmux wl-clipboard xz-utils zsh)
mapfile -t packages < <(sed -e 's/[[:space:]]*#.*$//' -e '/^[[:space:]]*$/d' "$ROOT/config/packages.txt")
run sudo apt-get update
if command -v Hyprland >/dev/null; then
  info "Installing ${#packages[@]} packages used directly by the tracked configuration."
  run sudo apt-get install -y "${packages[@]}"
else
  info "Installing base packages. The upstream Hyprland stage owns desktop packages and its PPA."
  run sudo apt-get install -y "${base_packages[@]}"
fi
