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
  available_packages=()
  deferred_packages=()
  for package in "${packages[@]}"; do
    if apt-cache show "$package" >/dev/null 2>&1; then
      available_packages+=("$package")
    else
      deferred_packages+=("$package")
    fi
  done

  info "Installing ${#available_packages[@]} available packages used directly by the tracked configuration."
  if ((${#available_packages[@]})); then
    run sudo apt-get install -y "${available_packages[@]}"
  fi
  if ((${#deferred_packages[@]})); then
    warn "Not available from the enabled APT repositories; deferring to the upstream installer: ${deferred_packages[*]}"
  fi
else
  info "Installing base packages. The upstream Hyprland stage owns desktop packages and its PPA."
  run sudo apt-get install -y "${base_packages[@]}"
fi
