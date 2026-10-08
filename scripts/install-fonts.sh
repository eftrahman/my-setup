#!/usr/bin/env bash
set -Eeuo pipefail
SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
# shellcheck source=scripts/lib.sh
source "$SCRIPT_DIR/lib.sh"
ROOT=$(repo_root)
# shellcheck source=config/versions.env
source "$ROOT/config/versions.env"

font_root=$HOME/.local/share/fonts
jetbrains_dir=$font_root/JetBrainsMonoNerd
meslo_dir=$font_root/MesloLGS-NF

install_jetbrains() {
  if fc-match 'JetBrainsMono Nerd Font' 2>/dev/null | grep -qi 'JetBrainsMono'; then
    ok "JetBrainsMono Nerd Font is already available."
  else
    archive_url="https://github.com/ryanoasis/nerd-fonts/releases/download/${NERD_FONTS_VERSION}/JetBrainsMono.tar.xz"
    sums_url="https://github.com/ryanoasis/nerd-fonts/releases/download/${NERD_FONTS_VERSION}/SHA-256.txt"
    if [[ ${DRY_RUN:-0} == 1 ]]; then
      print_command curl -fL "$archive_url" -o '<temporary>/JetBrainsMono.tar.xz'
      print_command curl -fL "$sums_url" -o '<temporary>/SHA-256.txt'
      print_command tar -xJf '<temporary>/JetBrainsMono.tar.xz' -C "$jetbrains_dir"
    else
      tmp_dir=$(mktemp -d)
      trap 'rm -rf -- "$tmp_dir"' EXIT
      curl -fL "$archive_url" -o "$tmp_dir/JetBrainsMono.tar.xz"
      curl -fL "$sums_url" -o "$tmp_dir/SHA-256.txt"
      expected=$(awk '$2 == "JetBrainsMono.tar.xz" {print $1}' "$tmp_dir/SHA-256.txt")
      [[ -n $expected ]] || die "JetBrainsMono checksum is absent from the official checksum file."
      actual=$(sha256sum "$tmp_dir/JetBrainsMono.tar.xz" | awk '{print $1}')
      [[ $actual == "$expected" ]] || die "JetBrainsMono checksum verification failed."
      mkdir -p "$jetbrains_dir"
      tar -xJf "$tmp_dir/JetBrainsMono.tar.xz" -C "$jetbrains_dir"
    fi
  fi
}

install_meslo() {
  meslo_base='https://raw.githubusercontent.com/romkatv/powerlevel10k-media/master'
  meslo_files=(
    'MesloLGS NF Regular.ttf'
    'MesloLGS NF Bold.ttf'
    'MesloLGS NF Italic.ttf'
    'MesloLGS NF Bold Italic.ttf'
  )
  run mkdir -p "$meslo_dir"
  for font_file in "${meslo_files[@]}"; do
    [[ -f $meslo_dir/$font_file ]] && continue
    encoded=${font_file// /%20}
    run curl -fL "$meslo_base/$encoded" -o "$meslo_dir/$font_file"
  done
}

fonts_selected=0
if component_selected hyprland; then
  install_jetbrains
  fonts_selected=1
fi
if component_selected zsh; then
  install_meslo
  fonts_selected=1
fi

if (( fonts_selected == 1 )); then
  run fc-cache -f "$font_root"
else
  info "Font stage skipped; neither zsh nor Hyprland was selected."
fi
