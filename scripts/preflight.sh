#!/usr/bin/env bash
set -Eeuo pipefail
SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
# shellcheck source=scripts/lib.sh
source "$SCRIPT_DIR/lib.sh"

require_non_root
load_os_release

[[ -n ${HOME:-} && $HOME != / ]] || die "HOME is not a safe user directory."
[[ -w $HOME ]] || die "HOME is not writable: $HOME"
command -v sudo >/dev/null || die "sudo is required."
command -v git >/dev/null || warn "git is missing; the packages stage will install it."
command -v curl >/dev/null || warn "curl is missing; the packages stage will install it."

available_kib=$(df -Pk "$HOME" | awk 'NR == 2 {print $4}')
(( available_kib >= 5242880 )) || die "At least 5 GiB free space is required for the upstream installer."

ok "Ubuntu ${VERSION_ID} (${VERSION_CODENAME:-unknown}), user $(id -un), home $HOME"
info "GPU summary (used only to guide the upstream installer):"
if command -v lspci >/dev/null; then
  lspci | grep -Ei 'vga|3d|display' || true
else
  warn "pciutils/lspci is not installed yet."
fi

