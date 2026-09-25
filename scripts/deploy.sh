#!/usr/bin/env bash
set -Eeuo pipefail
SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
# shellcheck source=scripts/lib.sh
source "$SCRIPT_DIR/lib.sh"
ROOT=$(repo_root)
SOURCE=$ROOT/home
timestamp=$(date +%Y%m%d-%H%M%S)
backup_root=${XDG_STATE_HOME:-$HOME/.local/state}/eftear-dotfiles/backups/$timestamp

managed_paths=(
  .zshrc .zprofile .zshenv .p10k.zsh .tmux.conf.local
  .config/btop .config/cava .config/fastfetch .config/hypr .config/kitty
  .config/Kvantum .config/qt5ct .config/qt6ct .config/rofi .config/swappy
  .config/swaync .config/wallust .config/waybar .config/wlogout .config/xsettingsd
)

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

for relative in "${managed_paths[@]}"; do
  [[ -e $SOURCE/$relative || -L $SOURCE/$relative ]] || die "Repository source is missing: $SOURCE/$relative"
  backup_path "$relative"
  run mkdir -p "$(dirname -- "$HOME/$relative")"
  run cp -a -- "$SOURCE/$relative" "$HOME/$relative"
done

backup_path .tmux.conf
run ln -s .tmux/.tmux.conf "$HOME/.tmux.conf"

backup_path Pictures/wallpapers
run mkdir -p "$HOME/Pictures"
run cp -a -- "$ROOT/assets/wallpapers" "$HOME/Pictures/wallpapers"

if [[ ${DRY_RUN:-0} == 1 ]]; then
  print_command sed -i "s|@HOME@|$HOME|g" "$HOME/.config/qt5ct/qt5ct.conf" "$HOME/.config/qt6ct/qt6ct.conf"
  print_command ln -sfn configs/TechConsole "$HOME/.config/waybar/config"
  print_command ln -sfn style/TechConsole.css "$HOME/.config/waybar/style.css"
  print_command ln -sfn "$HOME/Pictures/wallpapers/Dynamic-Wallpapers/Dark/Beach-Dark.png" "$HOME/.config/rofi/.current_wallpaper"
  print_command mkdir -p "$HOME/.config/hypr/wallpaper_effects"
  print_command ln -sfn "$HOME/Pictures/wallpapers/Dynamic-Wallpapers/Dark/Beach-Dark.png" "$HOME/.config/hypr/wallpaper_effects/.wallpaper_current"
else
  sed -i "s|@HOME@|$HOME|g" "$HOME/.config/qt5ct/qt5ct.conf" "$HOME/.config/qt6ct/qt6ct.conf"
  ln -sfn configs/TechConsole "$HOME/.config/waybar/config"
  ln -sfn style/TechConsole.css "$HOME/.config/waybar/style.css"
  ln -sfn "$HOME/Pictures/wallpapers/Dynamic-Wallpapers/Dark/Beach-Dark.png" "$HOME/.config/rofi/.current_wallpaper"
  mkdir -p "$HOME/.config/hypr/wallpaper_effects"
  ln -sfn "$HOME/Pictures/wallpapers/Dynamic-Wallpapers/Dark/Beach-Dark.png" "$HOME/.config/hypr/wallpaper_effects/.wallpaper_current"
fi

ok "Configuration deployed. Backup root: $backup_root"
