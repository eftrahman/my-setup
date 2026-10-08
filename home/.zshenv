typeset -U path
path=("$HOME/.local/bin" "$HOME/bin" $path)
export PATH

[[ -r "$HOME/.cargo/env" ]] && . "$HOME/.cargo/env"
