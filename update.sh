#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_PATH=$(readlink -f -- "${BASH_SOURCE[0]}")
ROOT=$(cd -- "$(dirname -- "$SCRIPT_PATH")" && pwd -P)

printf '%s\n' '[INFO] Pulling the latest my-setup changes...'
git -C "$ROOT" pull --ff-only

exec "$ROOT/bootstrap.sh" "$@"
