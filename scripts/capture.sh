#!/usr/bin/env bash
set -Eeuo pipefail
SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
# shellcheck source=scripts/lib.sh
source "$SCRIPT_DIR/lib.sh"
ROOT=$(repo_root)

APPLY=0
case ${1:-} in
  --apply) APPLY=1 ;;
  ''|--dry-run) ;;
  -h|--help)
    printf 'Usage: %s [--dry-run|--apply]\n' "$0"
    exit 0
    ;;
  *) die "Unknown option: $1" ;;
esac

command -v rsync >/dev/null || die "rsync is required. Run the packages stage first."
git -C "$ROOT" rev-parse --is-inside-work-tree >/dev/null 2>&1 || die "$ROOT is not a Git repository."
if ! git -C "$ROOT" diff --quiet || ! git -C "$ROOT" diff --cached --quiet; then
  die "Commit or stash repository changes before capturing from HOME."
fi

rsync_flags=(-a --delete --itemize-changes)
(( APPLY == 0 )) && rsync_flags+=(--dry-run)
excludes=(
  --exclude=.initial_startup_done
  '--exclude=*.bak' '--exclude=*.bak-*' '--exclude=*.before-*'
  '--exclude=*.orig' '--exclude=*.rej' '--exclude=*~' '--exclude=*.swp'
  --exclude=wallpaper_effects/.wallpaper_current
  --exclude=wallpaper_effects/.wallpaper_modified
  --exclude=.current_wallpaper
  --exclude=config
  --exclude=style.css
)

config_dirs=(btop cava fastfetch hypr kitty Kvantum qt5ct qt6ct rofi swappy swaync wallust waybar wlogout xsettingsd)
for config_dir in "${config_dirs[@]}"; do
  [[ -d $HOME/.config/$config_dir ]] || { warn "Skipping missing ~/.config/$config_dir"; continue; }
  mkdir -p "$ROOT/home/.config/$config_dir"
  rsync "${rsync_flags[@]}" "${excludes[@]}" "$HOME/.config/$config_dir/" "$ROOT/home/.config/$config_dir/"
done

for dotfile in .zshrc .zprofile .zshenv .p10k.zsh .tmux.conf.local; do
  [[ -f $HOME/$dotfile ]] || { warn "Skipping missing ~/$dotfile"; continue; }
  if (( APPLY == 1 )); then
    cp -a -- "$HOME/$dotfile" "$ROOT/home/$dotfile"
  else
    diff -q "$HOME/$dotfile" "$ROOT/home/$dotfile" >/dev/null || info "Would update $dotfile"
  fi
done

if [[ -d $HOME/Pictures/wallpapers ]]; then
  mkdir -p "$ROOT/assets/wallpapers"
  rsync "${rsync_flags[@]}" "$HOME/Pictures/wallpapers/" "$ROOT/assets/wallpapers/"
fi

if (( APPLY == 1 )); then
  sed -i "s|$HOME|@HOME@|g" "$ROOT/home/.config/qt5ct/qt5ct.conf" "$ROOT/home/.config/qt6ct/qt6ct.conf"
  sed -i 's|^\. "$HOME/.cargo/env"$|[[ -r "$HOME/.cargo/env" ]] \&\& . "$HOME/.cargo/env"|' "$ROOT/home/.zshenv"
  if rg -q --hidden --pcre2 '(?i)(api[_-]?key|access[_-]?token|client[_-]?secret|password)\s*[:=]\s*\S{8,}' "$ROOT/home"; then
    die "Possible credential detected. Review locally; nothing was printed to avoid exposing it."
  fi
  ok "Captured live configuration. Review with: git -C $ROOT status --short && git -C $ROOT diff"
else
  info "Dry run only. Use --apply after reviewing the itemized changes."
fi
