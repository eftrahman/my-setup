#!/usr/bin/env bash
set -Eeuo pipefail
SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
# shellcheck source=scripts/lib.sh
source "$SCRIPT_DIR/lib.sh"
ROOT=$(repo_root)
# shellcheck source=config/versions.env
source "$ROOT/config/versions.env"

install_repo() {
  local name=$1 url=$2 revision=$3 destination=$4
  if [[ -d $destination/.git ]]; then
    local current_remote
    current_remote=$(git -C "$destination" remote get-url origin 2>/dev/null || true)
    [[ $current_remote == "$url" || $current_remote == "${url%.git}" ]] || die "$name exists with an unexpected origin: $current_remote"
    if [[ -n $(git -C "$destination" status --porcelain) ]]; then
      warn "$name has local changes; leaving it untouched at $destination."
      return
    fi
    run git -C "$destination" fetch --quiet origin "$revision"
  elif [[ -e $destination ]]; then
    die "$destination exists but is not a Git checkout. Move it aside and rerun."
  else
    run git clone --filter=blob:none "$url" "$destination"
  fi
  run git -C "$destination" checkout --quiet "$revision"
  ok "$name is pinned to $revision"
}

if component_selected zsh; then
  install_repo "Oh My Zsh" "$OH_MY_ZSH_URL" "$OH_MY_ZSH_REV" "$HOME/.oh-my-zsh"
  install_repo "Powerlevel10k" "$POWERLEVEL10K_URL" "$POWERLEVEL10K_REV" "$HOME/.oh-my-zsh/custom/themes/powerlevel10k"
  install_repo "zsh-autosuggestions" "$ZSH_AUTOSUGGESTIONS_URL" "$ZSH_AUTOSUGGESTIONS_REV" "$HOME/.oh-my-zsh/custom/plugins/zsh-autosuggestions"
  install_repo "zsh-syntax-highlighting" "$ZSH_SYNTAX_HIGHLIGHTING_URL" "$ZSH_SYNTAX_HIGHLIGHTING_REV" "$HOME/.oh-my-zsh/custom/plugins/zsh-syntax-highlighting"
  install_repo "nvm" "$NVM_URL" "$NVM_REV" "$HOME/.nvm"

  if [[ ${NO_CHSH:-0} != 1 ]]; then
    zsh_path=$(command -v zsh)
    current_shell=$(getent passwd "$(id -un)" | cut -d: -f7)
    if [[ $current_shell != "$zsh_path" ]]; then
      info "Changing the login shell to $zsh_path (this can request your password)."
      run chsh -s "$zsh_path"
    fi
  fi
fi

if component_selected tmux; then
  install_repo "Oh My Tmux" "$OH_MY_TMUX_URL" "$OH_MY_TMUX_REV" "$HOME/.tmux"

  if [[ -e $HOME/.tmux.conf && ! -L $HOME/.tmux.conf ]]; then
    warn "$HOME/.tmux.conf is a regular file; deploy will back it up before linking Oh My Tmux."
  elif [[ ${DRY_RUN:-0} == 1 ]]; then
    print_command ln -sfn .tmux/.tmux.conf "$HOME/.tmux.conf"
  else
    ln -sfn .tmux/.tmux.conf "$HOME/.tmux.conf"
  fi
fi

if ! component_selected zsh && ! component_selected tmux; then
  info "Shell-tool stage skipped; neither zsh nor tmux was selected."
fi
