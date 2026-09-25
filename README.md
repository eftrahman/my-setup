# Portable Kubuntu + Hyprland workstation

This repository is a migration-safe snapshot of Eftear's working Kubuntu setup:

- Hyprland/KooL desktop configuration, including custom clipboard history, screenshots, Show Desktop, lock screen, Waybar, Rofi, Kitty, SwayNC, Wlogout, Wallust, and wallpapers.
- Oh My Zsh with Powerlevel10k, autosuggestions, syntax highlighting, NVM integration, and the current prompt.
- Oh My Tmux with the local theme, pane bindings, window naming, and Wayland system-clipboard integration.
- A staged installer that delegates Hyprland package ownership to the maintained Ubuntu installer while keeping personal configuration in this repository.

The snapshot was audited on Ubuntu 24.04.5, Hyprland 0.56.2, tmux 3.4, and Zsh 5.9. Ubuntu/Kubuntu 24.04 and 26.04 are accepted; other releases stop at preflight instead of guessing.

## New-machine installation

Start from a normal Kubuntu installation and log in as your regular sudo-capable user. Do not run the bootstrap itself with `sudo`.

```bash
sudo apt-get update
sudo apt-get install -y git
git clone YOUR_PRIVATE_REPOSITORY_URL "$HOME/dotfiles"
cd "$HOME/dotfiles"
./bootstrap.sh --dry-run
./bootstrap.sh
```

The stages are:

1. preflight and hardware summary;
2. base packages;
3. the maintained LinuxBeginnings Ubuntu-Hyprland installer, if Hyprland is absent;
4. pinned Oh My Zsh, plugins, Powerlevel10k, Oh My Tmux, and NVM;
5. verified JetBrainsMono Nerd Font plus Powerlevel10k's Meslo fonts;
6. backup and deployment of the tracked configuration;
7. syntax and runtime checks.

The upstream Hyprland installer remains interactive on purpose. GPU drivers, ROG support, display manager changes, and laptop choices must match the new hardware. The supplied preset enables the generic themes, Bluetooth, Thunar, and KooL baseline; this repository is deployed afterward.

Run only selected stages when repairing or updating a machine:

```bash
./bootstrap.sh --only shell,fonts,deploy,verify
./bootstrap.sh --only verify
./bootstrap.sh --no-chsh
```

## Safety and recovery

Deployment does not silently overwrite existing dotfiles. Conflicts are moved to:

```text
~/.local/state/eftear-dotfiles/backups/YYYYMMDD-HHMMSS/
```

The script uses copies rather than linking the desktop tree into Git. Hyprland, Wallust, Rofi, and Waybar write runtime state into their configuration directories; keeping that state out of the repository prevents a normal desktop session from dirtying Git.

To restore a backup, inspect the timestamped directory, then copy only the desired file or directory back. Do this while logged out of Hyprland for desktop-wide restores.

## Keeping future changes

The capture command is dry-run by default and refuses to proceed when the repository already has uncommitted changes:

```bash
cd "$HOME/dotfiles"
./scripts/capture.sh
./scripts/capture.sh --apply
git status --short
git diff
git add -A
git commit -m "Update workstation configuration"
git push
```

It excludes generated colors, wallpaper state, editor backups, and machine-local overrides. It normalizes the two Qt paths back to `@HOME@` and aborts if a likely credential assignment is detected.

## Machine-specific settings

`monitors.conf` intentionally uses portable `preferred/highrr/highres` defaults. On a new computer, configure displays with `nwg-displays` or `hyprctl monitors`; keep truly machine-specific files under `local/`, which Git ignores. Only promote a monitor profile into the tracked configuration when it should apply to every machine.

NVIDIA and ASUS ROG setup is not forced. Choose those options only when the destination hardware requires them. The tracked environment file leaves NVIDIA variables commented.

## GitHub publishing

The local repository contains no detected credentials, histories, browser data, SSH keys, or database files. A private remote is still recommended because desktop layouts and application choices are personal metadata.

```bash
cd "$HOME/dotfiles"
git remote add origin YOUR_PRIVATE_REPOSITORY_URL
git push -u origin main
```

See [docs/AUDIT.md](docs/AUDIT.md) for the inventory and design decisions and [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) for the fixes preserved by this setup.

