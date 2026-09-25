#!/usr/bin/env bash
# Toggle a KDE-style "show desktop" state across every normal workspace.
# Windows are parked on a hidden named special workspace and restored in place.

set -euo pipefail

runtime_dir="${XDG_RUNTIME_DIR:-/tmp}"
instance_id="${HYPRLAND_INSTANCE_SIGNATURE:-default}"
state_file="$runtime_dir/hypr-show-desktop-$instance_id.json"
lock_file="$runtime_dir/hypr-show-desktop-$instance_id.lock"

exec 9>"$lock_file"
flock -n 9 || exit 0

workspace_selector() {
  local workspace_name="$1"

  if [[ "$workspace_name" =~ ^[0-9]+$ ]]; then
    printf '%s' "$workspace_name"
  else
    printf 'name:%s' "$workspace_name"
  fi
}

if [[ -s "$state_file" ]]; then
  current_clients="$(hyprctl clients -j)"

  while IFS=$'\t' read -r address workspace_name was_pinned; do
    if ! jq -e --arg address "$address" 'any(.[]; .address == $address)' <<<"$current_clients" >/dev/null; then
      continue
    fi

    target_workspace="$(workspace_selector "$workspace_name")"
    hyprctl dispatch movetoworkspacesilent "$target_workspace,address:$address" >/dev/null

    if [[ "$was_pinned" == "true" ]]; then
      hyprctl dispatch pin "address:$address" >/dev/null
    fi
  done < <(jq -r '.[] | [.address, .workspace, (.pinned | tostring)] | @tsv' "$state_file")

  rm -f "$state_file"
  exit 0
fi

active_workspaces="$(hyprctl monitors -j | jq '[.[].activeWorkspace.name]')"

snapshot="$(
  hyprctl clients -j |
    jq --argjson active_workspaces "$active_workspaces" '[
      .[]
      | select(.mapped == true)
      | select((.workspace.name | startswith("special:")) | not)
      | {
          address: .address,
          workspace: .workspace.name,
          pinned: .pinned
        }
    ]'
)"

if [[ "$(jq 'length' <<<"$snapshot")" -eq 0 ]]; then
  exit 0
fi

temporary_state="$state_file.tmp.$$"
printf '%s\n' "$snapshot" >"$temporary_state"
mv "$temporary_state" "$state_file"

while IFS=$'\t' read -r address was_pinned; do
  if [[ "$was_pinned" == "true" ]]; then
    hyprctl dispatch pin "address:$address" >/dev/null
  fi

  hyprctl dispatch movetoworkspacesilent "special:showdesktop,address:$address" >/dev/null
done < <(jq -r '.[] | [.address, (.pinned | tostring)] | @tsv' "$state_file")
