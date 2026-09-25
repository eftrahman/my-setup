# Source workstation audit

Audited 2026-09-25 without copying secrets, histories, caches, browser profiles, databases, SSH material, or machine identity files.

## Platform and live versions

| Component | Audited value |
|---|---|
| OS | Ubuntu/Kubuntu 24.04.5 LTS (Noble) |
| Kernel | 7.0.0-31-generic |
| Session | Wayland / Hyprland |
| Hyprland | 0.56.2, Ubuntu PPA package `0.56.2-1ppa2` |
| Waybar | 0.14.0 |
| Rofi | 1.7.8+wayland1 |
| Kitty | 0.32.2 |
| tmux | 3.4 |
| Zsh | 5.9 |
| KooL dots marker | v2.3.20 |

Hyprland comes from `ppa:cppiber/hyprland` on the source machine. The historical installer checkout was JaKooLit's `24.04` branch at `953fa55`; that project announced archival, so fresh installation is routed to its maintained successor, LinuxBeginnings/Ubuntu-Hyprland, on the branch matching Ubuntu.

## What is preserved

- Full functional configurations for Hyprland, Waybar, Rofi, Kitty, SwayNC, Wlogout, Fastfetch, Wallust, Swappy, Cava, btop, Kvantum, qt5ct/qt6ct, and xsettingsd.
- `Super+V` clipboard history backed by `wl-paste`, `cliphist`, Rofi, and `wl-copy`.
- Region screenshots to clipboard, KDE-style Show Desktop, Super-key launcher behavior, Swww restore, TechConsole/Refined bar designs, and the technical lock-screen theme.
- Oh My Tmux's local configuration, including `set-clipboard on` and `tmux_conf_copy_to_os_clipboard=true`.
- Oh My Zsh, Powerlevel10k prompt, plugins, NVM startup, and guarded Cargo startup.
- Six wallpaper assets (about 37 MB), including the active Beach Dark wallpaper.

## What is reconstructed instead of copied

- Oh My Zsh, Powerlevel10k, the two Zsh plugins, Oh My Tmux, and NVM are cloned from their official Git origins at revisions recorded in `config/versions.env`.
- JetBrainsMono Nerd Font v3.5.1 is downloaded from the official release and verified against its official checksum list. The four MesloLGS NF faces are downloaded from Powerlevel10k's official media repository.
- The 681 MB icon directory and 496 MB local font directory are deliberately excluded. KooL themes/icons come from its installer; only fonts directly required by the active configuration are installed here.
- Hyprland's package/dependency graph remains owned by the maintained distro installer and PPA. This avoids mixing hand-built Hypr libraries, the common cause of ABI/`.so` mismatch failures.

## Local customizations found relative to upstream KooL dots

The comparison found changes in startup, keybinds, system settings, workspaces, lock screen, Kitty, Cava, Fastfetch, Qt styling, and generated Wallust colors. Unique local work includes `ClipboardHistory.sh`, `ShowDesktop.sh`, `hyprlock-tech.conf`, TechConsole and Refined Waybar layouts/styles, the clipboard Rofi menu, and a Tech Console Kitty theme.

The installer logs contained no unresolved failures. The apparent matches were the Rust crate named `quick-error` and informational messages saying a Thunar configuration was not found and would be copied.

## Portability changes made in the repository

- Replaced the source username in qt5ct/qt6ct paths with the deploy-time `@HOME@` placeholder.
- Guarded Cargo environment loading so Zsh works before Rust exists.
- Kept generic monitor discovery and disabled hardware-specific NVIDIA variables.
- Converted active Waybar/Rofi/wallpaper selections into deploy-time links.
- Excluded generated state and old `.bak`, `.orig`, and `.before-*` files.
- Added timestamped backups, dry-run behavior, pinned Git dependencies, official font checksum verification, and a verification stage.

