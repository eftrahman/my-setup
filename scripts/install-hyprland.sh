#!/usr/bin/env bash
set -Eeuo pipefail
SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
# shellcheck source=scripts/lib.sh
source "$SCRIPT_DIR/lib.sh"
ROOT=$(repo_root)
# shellcheck source=config/versions.env
source "$ROOT/config/versions.env"
load_os_release

ensure_swww_compatibility() {
  if command -v swww >/dev/null; then
    return 0
  fi
  if command -v awww >/dev/null && command -v awww-daemon >/dev/null; then
    info "Providing swww compatibility commands for the renamed awww wallpaper daemon."
    run sudo ln -sfn "$(command -v awww)" /usr/local/bin/swww
    run sudo ln -sfn "$(command -v awww-daemon)" /usr/local/bin/swww-daemon
  fi
}

ensure_swww_compatibility

portal_installed=0
if dpkg-query -W -f='${Status}' xdg-desktop-portal-hyprland 2>/dev/null | grep -q 'install ok installed'; then
  portal_installed=1
fi

required_commands=(Hyprland hyprctl hypridle hyprlock rofi waybar swaync wl-copy cliphist grim slurp swww)
missing_commands=()
for command_name in "${required_commands[@]}"; do
  command -v "$command_name" >/dev/null || missing_commands+=("$command_name")
done

if (( portal_installed == 1 && ${#missing_commands[@]} == 0 )); then
  ok "Hyprland and the required desktop runtime are already installed; upstream install stage is not needed."
  exit 0
fi

if command -v Hyprland >/dev/null; then
  warn "A partial Hyprland installation was detected; the upstream installer will resume."
  if ((${#missing_commands[@]})); then
    warn "Missing runtime commands: ${missing_commands[*]}"
  fi
  (( portal_installed == 1 )) || warn "Missing package: xdg-desktop-portal-hyprland"
fi

cache_base=${XDG_CACHE_HOME:-$HOME/.cache}/eftear-workstation-bootstrap
installer_dir=$cache_base/Ubuntu-Hyprland-${VERSION_ID}
run mkdir -p "$cache_base"

if [[ ! -d $installer_dir/.git ]]; then
  run git clone --branch "$VERSION_ID" --single-branch "$HYPRLAND_INSTALLER_URL" "$installer_dir"
else
  run git -C "$installer_dir" fetch origin "$VERSION_ID"
  run git -C "$installer_dir" checkout "$VERSION_ID"
  run git -C "$installer_dir" pull --ff-only origin "$VERSION_ID"
fi

warn "The maintained upstream installer is interactive because GPU, SDDM, and laptop choices are machine-specific."
warn "Review the choices it shows. Keep NVIDIA/ROG disabled unless the new machine actually needs them."
if [[ ${DRY_RUN:-0} == 1 ]]; then
  print_command bash "$installer_dir/install.sh" --preset "$ROOT/config/upstream-preset.sh"
else
  (cd "$installer_dir" && bash ./install.sh --preset "$ROOT/config/upstream-preset.sh")
  ensure_swww_compatibility
fi
