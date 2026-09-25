#!/usr/bin/env bash
set -Eeuo pipefail
SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
# shellcheck source=scripts/lib.sh
source "$SCRIPT_DIR/lib.sh"

failures=0
check_command() {
  if command -v "$1" >/dev/null; then
    ok "$1: $(command -v "$1")"
  else
    warn "Missing command: $1"
    failures=$((failures + 1))
  fi
}

commands=(Hyprland hyprctl hypridle hyprlock kitty rofi waybar swaync wl-copy cliphist grim slurp swww tmux zsh)
for command_name in "${commands[@]}"; do check_command "$command_name"; done

if zsh -n "$HOME/.zshrc" "$HOME/.p10k.zsh"; then ok "Zsh syntax"; else failures=$((failures + 1)); fi
if jq empty "$HOME/.config/swaync/config.json"; then ok "SwayNC JSON"; else failures=$((failures + 1)); fi

if command -v tmux >/dev/null && [[ -r $HOME/.tmux.conf ]]; then
  socket_name=eftear-dotfiles-check-$$
  if tmux -L "$socket_name" -f "$HOME/.tmux.conf" new-session -d 2>/tmp/eftear-tmux-check.err; then
    tmux -L "$socket_name" kill-server
    ok "tmux configuration parses"
  else
    warn "tmux configuration check failed: $(tr '\n' ' ' </tmp/eftear-tmux-check.err)"
    failures=$((failures + 1))
  fi
  rm -f /tmp/eftear-tmux-check.err
fi

if [[ ${XDG_CURRENT_DESKTOP:-} == Hyprland ]] && command -v hyprctl >/dev/null; then
  config_errors=$(hyprctl configerrors 2>/dev/null || true)
  if [[ -z $config_errors ]]; then ok "Hyprland reports no configuration errors"; else warn "$config_errors"; failures=$((failures + 1)); fi
else
  warn "Not inside a Hyprland session; skipped live hyprctl validation."
fi

if (( failures > 0 )); then
  die "$failures verification check(s) failed."
fi
ok "All available verification checks passed."

