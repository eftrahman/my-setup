# Troubleshooting and preserved fixes

## Installation was interrupted or the desktop session closed

Reconnect AC power, log back into Plasma, and rerun `./bootstrap.sh`. The package stage skips tools that are not published by the enabled Ubuntu repositories and leaves them to the maintained upstream installer. The Hyprland stage checks the complete desktop runtime, so a partial installation is resumed instead of being mistaken for a finished one.

The current upstream installer supplies the renamed `awww` wallpaper daemon. The bootstrap creates its official `swww`/`swww-daemon` compatibility command links because the preserved configuration still uses those names.

If APT itself was interrupted, repair it first:

```bash
sudo dpkg --configure -a
sudo apt-get --fix-broken install
```

## Hyprland starts with errors or missing shared libraries

Do not mix locally compiled Hyprland ecosystem libraries with PPA packages. On Ubuntu 24.04/26.04, rerun the maintained upstream stage so Hyprland, Aquamarine, Hyprutils, Hyprgraphics, Hyprlang, portals, and related packages come from a compatible source:

```bash
./bootstrap.sh --only hyprland,verify
```

The official Hyprland documentation warns that its ecosystem components are tightly coupled; manual mixes commonly cause missing or mismatched `.so` files.

## Screen sharing or file pickers fail

Check the portal and session environment:

```bash
systemctl --user status xdg-desktop-portal-hyprland.service
systemctl --user status xdg-desktop-portal.service
echo "$XDG_CURRENT_DESKTOP $XDG_SESSION_TYPE"
```

Log out fully after package or portal changes. Do not run both an old manually installed portal and the PPA portal.

## tmux copy does not reach the desktop clipboard

The preserved configuration requires `wl-copy` from `wl-clipboard`, and the tmux server must have been started inside a Wayland session:

```bash
echo "$XDG_SESSION_TYPE"
command -v wl-copy
tmux show-options -g -s set-clipboard
```

Expected values are `wayland`, a valid `wl-copy` path, and `set-clipboard on`. Restart the tmux server after changing its environment: exit all sessions, then start tmux again.

## Super+V has no clipboard history

Confirm the two watchers are running and that copied items exist:

```bash
pgrep -af 'wl-paste.*cliphist store'
cliphist list | head
```

They are started from `~/.config/hypr/configs/Startup_Apps.conf`. The menu script also checks `cliphist`, `rofi`, and `wl-copy` and sends a notification if one is absent.

## Prompt or bar icons render as boxes

Run the font stage and restart Kitty/Waybar:

```bash
./bootstrap.sh --only fonts
fc-match 'JetBrainsMono Nerd Font'
fc-match 'MesloLGS NF'
```

Kitty and the desktop UI use JetBrainsMono Nerd Font; Powerlevel10k can use MesloLGS NF.

## Wrong monitor layout on a new computer

The repository starts with automatic monitor rules. Inspect connector names with `hyprctl monitors`, then use `nwg-displays` or create a machine profile under ignored `local/`. Avoid committing a laptop panel name or desktop connector layout as the universal default.

## Undo a deployment

Every replaced path is moved beneath `~/.local/state/eftear-dotfiles/backups/<timestamp>/`. Stop the affected applications (or log out), inspect that directory, and copy back only the paths you want. Backups are never automatically deleted.
