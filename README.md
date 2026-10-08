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

The bootstrap opens a checklist with three independent components:

| Component | Installs and manages |
| --- | --- |
| `zsh` | Zsh, Oh My Zsh, Powerlevel10k, autosuggestions, syntax highlighting, NVM, Meslo Nerd Fonts, and Zsh configuration |
| `tmux` | tmux, Oh My Tmux, Wayland clipboard support, and tmux configuration |
| `hyprland` | Hyprland, desktop applications, JetBrainsMono Nerd Font, Waybar, Rofi, lock screen, themes, and wallpapers |

Use the arrow keys to move, `Space` to toggle, `Tab` to reach **OK**, and `Enter` to continue. All three are selected by default. For scripts or a direct component installation, bypass the menu with:

```bash
./bootstrap.sh --components zsh
./bootstrap.sh --components tmux
./bootstrap.sh --components hyprland
./bootstrap.sh --components zsh,tmux
./bootstrap.sh --components all
```

Internally, the stages are:

1. preflight and hardware summary;
2. base packages;
3. the maintained LinuxBeginnings Ubuntu-Hyprland installer, if Hyprland is absent;
4. selected pinned Zsh/tmux toolchains;
5. fonts required by the selected components;
6. backup and deployment of only the selected configuration;
7. component-specific syntax and runtime checks.

The upstream Hyprland installer remains interactive on purpose. GPU drivers, ROG support, display manager changes, and laptop choices must match the new hardware. The supplied preset enables the generic themes, Bluetooth, Thunar, and KooL baseline; this repository is deployed afterward.

Run only selected stages when repairing or updating a machine:

```bash
./bootstrap.sh --components zsh --only shell,fonts,deploy,verify
./bootstrap.sh --components tmux --only shell,deploy,verify
./bootstrap.sh --components hyprland --only deploy,verify
./bootstrap.sh --no-chsh
```

## Updating an existing machine

The first successful bootstrap installs `my-setup-update` in `~/.local/bin`. With no options, it performs a fast-forward-only pull from GitHub and automatically updates, deploys, and verifies all three components:

```bash
my-setup-update
```

Use a component option only when you intentionally want a partial update:

```bash
my-setup-update --components zsh
my-setup-update --components tmux
my-setup-update --components hyprland
```

Run `./bootstrap.sh` directly when you want the interactive component checklist.

If the command is not available until the next login, use `~/.local/bin/my-setup-update` or run `./update.sh` from the repository. The pull stops safely if the repository contains conflicting local changes.

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
