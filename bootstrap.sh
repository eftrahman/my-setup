#!/usr/bin/env bash
set -Eeuo pipefail
SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
# shellcheck source=scripts/lib.sh
source "$SCRIPT_DIR/scripts/lib.sh"

DRY_RUN=0
ASSUME_YES=0
NO_CHSH=0
ONLY=''

usage() {
  cat <<'USAGE'
Usage: ./bootstrap.sh [options]

Options:
  --dry-run          Print every mutating command without running it.
  --yes              Accept this wrapper's confirmations (upstream UI remains interactive).
  --no-chsh          Do not change the login shell to Zsh.
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
    --only) shift; (($#)) || die "--only requires a comma-separated value"; ONLY=$1 ;;
    --only=*) ONLY=${1#*=} ;;
    -h|--help) usage; exit 0 ;;
    *) die "Unknown option: $1" ;;
  esac
  shift
done
export DRY_RUN ASSUME_YES NO_CHSH

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
1. Validate Ubuntu/Kubuntu and hardware context
2. Install direct package dependencies
3. Run the maintained Ubuntu-Hyprland installer when needed
4. Recreate the pinned Oh My Zsh / Oh My Tmux toolchain
5. Install only the required Nerd Fonts
6. Back up conflicts and deploy the known-good configuration
7. Validate shell, tmux, JSON, commands, and live Hyprland state
BANNER

if [[ $DRY_RUN != 1 ]] && ! confirm "Continue with stages: ${stages[*]}?"; then
  die "Cancelled."
fi

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

ok "Bootstrap completed. Log out and choose Hyprland in SDDM if this was a fresh installation."
