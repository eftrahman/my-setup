#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_PATH=$(readlink -f -- "${BASH_SOURCE[0]}")
ROOT=$(cd -- "$(dirname -- "$SCRIPT_PATH")" && pwd -P)

printf '%s\n' '[INFO] Pulling the latest my-setup changes...'
git -C "$ROOT" pull --ff-only

args=("$@")
has_components=0
has_yes=0
for arg in "${args[@]}"; do
  case $arg in
    --components|--components=*) has_components=1 ;;
    --yes) has_yes=1 ;;
  esac
done

(( has_components == 1 )) || args+=(--components all)
(( has_yes == 1 )) || args+=(--yes)

exec "$ROOT/bootstrap.sh" "${args[@]}"
