#!/usr/bin/env bash

set -Eeuo pipefail
IFS=$'\n\t'

if [[ -t 1 ]]; then
  C_BLUE=$'\033[34m'
  C_GREEN=$'\033[32m'
  C_YELLOW=$'\033[33m'
  C_RED=$'\033[31m'
  C_RESET=$'\033[0m'
else
  C_BLUE='' C_GREEN='' C_YELLOW='' C_RED='' C_RESET=''
fi

info() { printf '%s[INFO]%s %s\n' "$C_BLUE" "$C_RESET" "$*"; }
ok() { printf '%s[ OK ]%s %s\n' "$C_GREEN" "$C_RESET" "$*"; }
warn() { printf '%s[WARN]%s %s\n' "$C_YELLOW" "$C_RESET" "$*" >&2; }
die() { printf '%s[FAIL]%s %s\n' "$C_RED" "$C_RESET" "$*" >&2; exit 1; }

print_command() {
  printf '  +'
  printf ' %q' "$@"
  printf '\n'
}

run() {
  if [[ ${DRY_RUN:-0} == 1 ]]; then
    print_command "$@"
  else
    "$@"
  fi
}

confirm() {
  local prompt=$1 reply
  if [[ ${ASSUME_YES:-0} == 1 ]]; then
    return 0
  fi
  read -r -p "$prompt [y/N] " reply
  [[ $reply == [yY] || $reply == [yY][eE][sS] ]]
}

repo_root() {
  cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P
}

require_non_root() {
  (( EUID != 0 )) || die "Run this as your normal user, not with sudo. The scripts invoke sudo only where needed."
}

load_os_release() {
  [[ -r /etc/os-release ]] || die "Cannot read /etc/os-release."
  # shellcheck disable=SC1091
  source /etc/os-release
  [[ ${ID:-} == ubuntu ]] || die "This bootstrap supports Ubuntu/Kubuntu only (detected: ${ID:-unknown})."
  case ${VERSION_ID:-} in
    24.04|26.04) ;;
    *) die "Supported Ubuntu releases are 24.04 and 26.04; detected ${VERSION_ID:-unknown}. Use a matching upstream branch before extending support." ;;
  esac
}

