#!/usr/bin/env bash
set -Eeuo pipefail

ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)

printf '%s\n' '[INFO] Pulling the latest my-setup changes...'
git -C "$ROOT" pull --ff-only

exec "$ROOT/bootstrap.sh" "$@"
