#!/usr/bin/env bash
set -Eeuo pipefail
SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
# shellcheck source=scripts/lib.sh
source "$SCRIPT_DIR/scripts/lib.sh"

DRY_RUN=0
ASSUME_YES=0
NO_CHSH=0
ONLY=''
COMPONENTS=''

usage() {
  cat <<'USAGE'
Usage: ./bootstrap.sh [options]

Options:
  --dry-run          Print every mutating command without running it.
  --yes              Accept this wrapper's confirmations (upstream UI remains interactive).
  --no-chsh          Do not change the login shell to Zsh.
  --components LIST  Configure only: zsh,tmux,hyprland (or all).
  --only LIST        Run comma-separated stages: preflight,packages,hyprland,shell,fonts,deploy,verify.
  -h, --help         Show this help.

Recommended first run:
  ./bootstrap.sh --dry-run
  ./bootstrap.sh
USAGE
}

while (($#)); do
  case $1 in
    --dry-run) DRY_RUN=1 ;;
    --yes) ASSUME_YES=1 ;;
    --no-chsh) NO_CHSH=1 ;;
    --components) shift; (($#)) || die "--components requires a comma-separated value"; COMPONENTS=$1 ;;
    --components=*) COMPONENTS=${1#*=} ;;
    --only) shift; (($#)) || die "--only requires a comma-separated value"; ONLY=$1 ;;
    --only=*) ONLY=${1#*=} ;;
    -h|--help) usage; exit 0 ;;
    *) die "Unknown option: $1" ;;
  esac
  shift
done

choose_components() {
  local choices reply
  if [[ $ASSUME_YES == 1 ]]; then
    COMPONENTS=all
    return
  fi

  if command -v whiptail >/dev/null 2>&1; then
    if ! choices=$(whiptail --title "Eftear Setup Components" --checklist \
      "Select what to install or update. Space toggles; Tab moves to OK." 16 76 5 \
      zsh "Zsh, Oh My Zsh, Powerlevel10k, plugins, NVM and fonts" ON \
      tmux "tmux, Oh My Tmux and tmux configuration" ON \
      hyprland "Hyprland desktop, applications, themes and wallpapers" ON \
      3>&1 1>&2 2>&3); then
      die "Component selection cancelled."
    fi
    COMPONENTS=${choices//\"/}
    COMPONENTS=${COMPONENTS// /,}
  else
    printf '%s\n' 'Select components: zsh, tmux, hyprland, or all.'
    read -r -p 'Components [all]: ' reply
    COMPONENTS=${reply:-all}
    COMPONENTS=${COMPONENTS// /,}
  fi
}

normalize_components() {
  local requested component normalized=''
  local -a component_list=()
  requested=${COMPONENTS,,}
  requested=${requested// /,}
  [[ $requested == all ]] && requested='zsh,tmux,hyprland'
  IFS=',' read -r -a component_list <<<"$requested"
  for component in "${component_list[@]}"; do
    [[ -n $component ]] || continue
    case $component in
      zsh|tmux|hyprland) ;;
      *) die "Unknown component: $component (choose zsh, tmux, hyprland, or all)." ;;
    esac
  done
  for component in zsh tmux hyprland; do
    if [[ ",$requested," == *",$component,"* ]]; then
      normalized+="${normalized:+,}$component"
    fi
  done
  [[ -n $normalized ]] || die "Select at least one component."
  COMPONENTS=$normalized
}

[[ -n $COMPONENTS ]] || choose_components
normalize_components
SETUP_COMPONENTS=$COMPONENTS
export DRY_RUN ASSUME_YES NO_CHSH SETUP_COMPONENTS

all_stages=(preflight packages hyprland shell fonts deploy verify)
if [[ -n $ONLY ]]; then
  IFS=',' read -r -a stages <<<"$ONLY"
else
  stages=("${all_stages[@]}")
fi

for stage in "${stages[@]}"; do
  case ",preflight,packages,hyprland,shell,fonts,deploy,verify," in
    *",$stage,"*) ;;
    *) die "Unknown stage: $stage" ;;
  esac
done

cat <<'BANNER'
Eftear workstation bootstrap
============================
Component-aware installation and updates for Zsh, tmux, and Hyprland.
BANNER

info "Selected components: $SETUP_COMPONENTS"
info "Selected stages: ${stages[*]}"

if [[ $DRY_RUN != 1 ]] && ! confirm "Continue with $SETUP_COMPONENTS?"; then
  die "Cancelled."
fi

run mkdir -p "$HOME/.local/bin"
run ln -sfn "$SCRIPT_DIR/update.sh" "$HOME/.local/bin/my-setup-update"

for stage in "${stages[@]}"; do
  printf '\n%s==> %s%s\n' "$C_BLUE" "$stage" "$C_RESET"
  case $stage in
    preflight) stage_script=preflight.sh ;;
    packages) stage_script=install-packages.sh ;;
    hyprland) stage_script=install-hyprland.sh ;;
    shell) stage_script=install-shell.sh ;;
    fonts) stage_script=install-fonts.sh ;;
    deploy) stage_script=deploy.sh ;;
    verify) stage_script=verify.sh ;;
  esac
  "$SCRIPT_DIR/scripts/$stage_script"
done

ok "Bootstrap completed for: $SETUP_COMPONENTS"
if component_selected zsh; then
  info "Open a new terminal (or log out and back in) to use Zsh changes."
fi
if component_selected hyprland; then
  info "For a fresh desktop install, log out and choose Hyprland in SDDM."
fi
