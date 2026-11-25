#!/usr/bin/env bash
set -Eeuo pipefail
SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
# shellcheck source=scripts/lib.sh
source "$SCRIPT_DIR/lib.sh"
ROOT=$(repo_root)
SOURCE=$ROOT/home
timestamp=$(date +%Y%m%d-%H%M%S)
backup_root=${XDG_STATE_HOME:-$HOME/.local/state}/eftear-dotfiles/backups/$timestamp

zsh_paths=(.zshrc .zprofile .zshenv .p10k.zsh)
tmux_paths=(.tmux.conf.local)
hyprland_paths=(
  .config/btop .config/cava .config/fastfetch .config/hypr .config/kitty
  .config/Kvantum .config/qt5ct .config/qt6ct .config/rofi .config/swappy
  .config/swaync .config/wallust .config/waybar .config/wlogout .config/xsettingsd
)

managed_paths=()
component_selected zsh && managed_paths+=("${zsh_paths[@]}")
component_selected tmux && managed_paths+=("${tmux_paths[@]}")
component_selected hyprland && managed_paths+=("${hyprland_paths[@]}")

backup_path() {
  local relative target backup
  relative=$1
  target=$HOME/$relative
  backup=$backup_root/$relative
  if [[ -e $target || -L $target ]]; then
    run mkdir -p "$(dirname -- "$backup")"
    run mv -- "$target" "$backup"
    info "Backed up $target -> $backup"
  fi
}

# Per-machine display layout: lives outside the managed paths so updates never
# replace it. Created first because hyprland.conf sources it. An existing custom
# monitors.conf (e.g. from nwg-displays) seeds it once.
if component_selected hyprland; then
  displays_conf=$HOME/.config/hypr-local/displays.conf
  if [[ ! -e $displays_conf ]]; then
    run mkdir -p "$(dirname -- "$displays_conf")"
    if [[ ${DRY_RUN:-0} == 1 ]]; then
      print_command touch "$displays_conf"
    else
      {
        printf '# Display layout for THIS machine (Display Center: Super+Shift+P).\n'
        if [[ -r $HOME/.config/hypr/monitors.conf ]]; then
          grep -E '^[[:space:]]*monitor[[:space:]]*=' "$HOME/.config/hypr/monitors.conf" \
            | grep -vxFf "$SOURCE/.config/hypr/monitors.conf" || true
        fi
      } >"$displays_conf"
      info "Created machine-local display layout: $displays_conf"
    fi
  fi
fi

for relative in "${managed_paths[@]}"; do
  [[ -e $SOURCE/$relative || -L $SOURCE/$relative ]] || die "Repository source is missing: $SOURCE/$relative"
  backup_path "$relative"
  run mkdir -p "$(dirname -- "$HOME/$relative")"
  run cp -a -- "$SOURCE/$relative" "$HOME/$relative"
done

if component_selected tmux; then
  backup_path .tmux.conf
  run ln -s .tmux/.tmux.conf "$HOME/.tmux.conf"
fi

if component_selected hyprland; then
  backup_path Pictures/wallpapers
  run mkdir -p "$HOME/Pictures"
  run cp -a -- "$ROOT/assets/wallpapers" "$HOME/Pictures/wallpapers"

  if [[ ${DRY_RUN:-0} == 1 ]]; then
    print_command sed -i "s|@HOME@|$HOME|g" "$HOME/.config/qt5ct/qt5ct.conf" "$HOME/.config/qt6ct/qt6ct.conf" "$HOME/.config/hypr/xdph.conf"
    print_command ln -sfn configs/TechConsole "$HOME/.config/waybar/config"
    print_command ln -sfn style/TechConsole.css "$HOME/.config/waybar/style.css"
    print_command ln -sfn "$HOME/Pictures/wallpapers/Dynamic-Wallpapers/Dark/Beach-Dark.png" "$HOME/.config/rofi/.current_wallpaper"
    print_command mkdir -p "$HOME/.config/hypr/wallpaper_effects"
    print_command ln -sfn "$HOME/Pictures/wallpapers/Dynamic-Wallpapers/Dark/Beach-Dark.png" "$HOME/.config/hypr/wallpaper_effects/.wallpaper_current"
  else
    sed -i "s|@HOME@|$HOME|g" "$HOME/.config/qt5ct/qt5ct.conf" "$HOME/.config/qt6ct/qt6ct.conf" "$HOME/.config/hypr/xdph.conf"
    ln -sfn configs/TechConsole "$HOME/.config/waybar/config"
    ln -sfn style/TechConsole.css "$HOME/.config/waybar/style.css"
    ln -sfn "$HOME/Pictures/wallpapers/Dynamic-Wallpapers/Dark/Beach-Dark.png" "$HOME/.config/rofi/.current_wallpaper"
    mkdir -p "$HOME/.config/hypr/wallpaper_effects"
    ln -sfn "$HOME/Pictures/wallpapers/Dynamic-Wallpapers/Dark/Beach-Dark.png" "$HOME/.config/hypr/wallpaper_effects/.wallpaper_current"
  fi

  # Keep KDE applications such as Dolphin on a coherent light palette. The
  # qt5ct/qt6ct and Kvantum files above provide matching Catppuccin Latte colors.
  if command -v plasma-apply-colorscheme >/dev/null 2>&1; then
    run plasma-apply-colorscheme KubuntuLight
  else
    warn "plasma-apply-colorscheme is unavailable; skipping the KDE light palette"
  fi

  # The screen-share portal reads xdph.conf only at startup.
  if [[ ${DRY_RUN:-0} != 1 ]] && systemctl --user is-active --quiet xdg-desktop-portal-hyprland 2>/dev/null; then
    systemctl --user restart xdg-desktop-portal-hyprland && info "Restarted the screen-share portal."
  fi

  if [[ ${DRY_RUN:-0} != 1 ]] && pgrep -x waybar >/dev/null 2>&1; then
    pkill -SIGUSR2 -x waybar
    info "Reloaded the running Waybar configuration."
  fi
fi

ok "Configuration deployed for: ${SETUP_COMPONENTS}. Backup root: $backup_root"
