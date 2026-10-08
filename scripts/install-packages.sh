#!/usr/bin/env bash
set -Eeuo pipefail
SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
# shellcheck source=scripts/lib.sh
source "$SCRIPT_DIR/lib.sh"
ROOT=$(repo_root)

zsh_packages=(ca-certificates curl fontconfig git lsd zsh)
tmux_packages=(ca-certificates git tmux wl-clipboard)
hyprland_bootstrap_packages=(ca-certificates curl fontconfig git jq kitty rsync wl-clipboard xz-utils)
mapfile -t hyprland_packages < <(sed -e 's/[[:space:]]*#.*$//' -e '/^[[:space:]]*$/d' "$ROOT/config/packages.txt")

selected_packages=()
declare -A package_seen=()
add_packages() {
  local package
  for package in "$@"; do
    [[ -n ${package_seen[$package]:-} ]] && continue
    package_seen[$package]=1
    selected_packages+=("$package")
  done
}

component_selected zsh && add_packages "${zsh_packages[@]}"
component_selected tmux && add_packages "${tmux_packages[@]}"
if component_selected hyprland; then
  if command -v Hyprland >/dev/null; then
    add_packages "${hyprland_packages[@]}"
  else
    add_packages "${hyprland_bootstrap_packages[@]}"
  fi
fi

((${#selected_packages[@]})) || die "No packages mapped to the selected components."
run sudo apt-get update

available_packages=()
deferred_packages=()
for package in "${selected_packages[@]}"; do
  if apt-cache show "$package" >/dev/null 2>&1; then
    available_packages+=("$package")
  else
    deferred_packages+=("$package")
  fi
done

info "Installing ${#available_packages[@]} available packages for: ${SETUP_COMPONENTS}."
if ((${#available_packages[@]})); then
  run sudo apt-get install -y "${available_packages[@]}"
fi
if ((${#deferred_packages[@]})); then
  warn "Not available from the enabled APT repositories; a component installer may provide them: ${deferred_packages[*]}"
fi
