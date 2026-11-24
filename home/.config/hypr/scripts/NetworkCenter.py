#!/usr/bin/env python3
"""Network Center: Wi-Fi, saved connections, and hotspot control for Hyprland.

Everything goes through `nmcli`, so the panel works on any NetworkManager
system without extra Python bindings. Machines without a Wi-Fi adapter still
get the overview and saved-connection pages; the Wi-Fi and hotspot pages show
a clear "no adapter" state instead of failing.
"""

import os
import re
import secrets
import string
import subprocess
import sys
import threading

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, Gio, GLib, Gtk, Pango  # noqa: E402


APP_ID = "dev.eftear.hyprland.NetworkCenter"
HOTSPOT_NAME = "Network Center Hotspot"
NMCLI_TIMEOUT = 45

PAGES = (
    ("overview", "Overview", "󰛳"),
    ("wifi", "Wi-Fi", "󰖩"),
    ("saved", "Saved", "󰆓"),
    ("hotspot", "Hotspot", "󰀂"),
)
SIGNAL_ICONS = ("󰤯", "󰤟", "󰤢", "󰤥", "󰤨")
TYPE_ICONS = {
    "802-11-wireless": "󰖩",
    "wifi": "󰖩",
    "802-3-ethernet": "󰈀",
    "ethernet": "󰈀",
    "vpn": "󰖂",
    "wireguard": "󰖂",
    "bridge": "󰘘",
    "loopback": "󰑙",
    "gsm": "󰒢",
    "bluetooth": "󰂯",
    "tun": "󰖂",
}
HIDDEN_TYPES = {"loopback"}

CSS = b"""
@define-color bg #080b16;
@define-color panel #0d1220;
@define-color panel2 #111827;
@define-color card #12192a;
@define-color hover #18243a;
@define-color border #26334f;
@define-color text #e5ecff;
@define-color muted #8794b3;
@define-color cyan #5ee7f7;
@define-color violet #b991ff;
@define-color green #78f0c2;
@define-color amber #ffcc66;
@define-color red #ff6b81;

* { font-family: "JetBrainsMono Nerd Font", "Noto Sans"; outline: none; }
window, #root, dialog, dialog box { background: @bg; color: @text; }

headerbar {
  min-height: 58px;
  padding: 6px 12px;
  color: @text;
  background: @panel;
  border: 0;
  border-bottom: 1px solid @border;
  box-shadow: none;
}
headerbar .title { color: @text; font-size: 17px; font-weight: 800; }
headerbar .subtitle { color: @muted; font-size: 11px; }

#sidebar { min-width: 190px; padding: 18px 12px; background: @panel; border-right: 1px solid @border; }
.sidebar-title { margin: 2px 10px 12px; color: @muted; font-size: 10px; font-weight: 800; }
button.nav {
  min-height: 40px; margin: 2px 0; padding: 0 11px;
  color: @muted; background: transparent; border: 0; border-radius: 9px; box-shadow: none;
}
button.nav:hover { color: @text; background: @hover; }
button.nav.active { color: @cyan; background: alpha(@cyan, .11); }
.nav-icon { min-width: 24px; color: @violet; font-size: 15px; }
button.nav.active .nav-icon { color: @cyan; }
.nav-name { font-size: 12px; font-weight: 700; }
.nav-badge { color: @muted; font-size: 10px; }

.page { background: @bg; }
.page-header { min-height: 74px; padding: 0 22px; border-bottom: 1px solid @border; }
.section-title { color: @text; font-size: 15px; font-weight: 800; }
.section-copy { margin-top: 3px; color: @muted; font-size: 10px; }

switch { background: @panel2; border: 1px solid @border; border-radius: 14px; }
switch:checked { background: alpha(@cyan, .55); }
switch slider { background: @text; border-radius: 12px; min-width: 22px; min-height: 22px; }

list { padding: 6px 14px 14px; background: @bg; }
row.net-row {
  margin: 3px 0; padding: 0; color: @text;
  background: @card; border: 1px solid @border; border-radius: 11px;
}
row.net-row:hover { background: @hover; border-color: alpha(@cyan, .35); }
row.net-row:selected { color: @text; background-color: #132a38; background-image: none; border-color: @cyan; }
row.net-row.current { border-color: alpha(@green, .65); }
.row-inner { min-height: 52px; padding: 5px 12px; }
.row-icon {
  min-width: 34px; min-height: 34px; color: @violet; font-size: 16px;
  background: alpha(@violet, .10); border: 1px solid alpha(@violet, .24); border-radius: 9px;
}
.row-icon.strong { color: @green; background: alpha(@green, .10); border-color: alpha(@green, .30); }
.row-icon.weak { color: @amber; background: alpha(@amber, .10); border-color: alpha(@amber, .30); }
.row-title { color: @text; font-size: 12px; font-weight: 700; }
.row-meta { margin-top: 2px; color: @muted; font-size: 9px; }
.pill { padding: 2px 8px; border-radius: 9px; font-size: 9px; font-weight: 800; }
.pill.on { color: @green; background: alpha(@green, .12); }
.pill.off { color: @muted; background: alpha(@muted, .10); }
.pill.warn { color: @amber; background: alpha(@amber, .12); }
.pill.bad { color: @red; background: alpha(@red, .12); }
.lock { color: @muted; font-size: 11px; }

.card {
  margin: 0; padding: 16px 18px;
  background: @card; border: 1px solid @border; border-radius: 12px;
}
.card-title { color: @text; font-size: 13px; font-weight: 800; }
.card-icon { color: @cyan; font-size: 22px; min-width: 34px; }
.kv-key { color: @muted; font-size: 10px; }
.kv-value { color: @text; font-size: 11px; }
.big-state { font-size: 20px; font-weight: 800; }
.state-good { color: @green; }
.state-warn { color: @amber; }
.state-bad { color: @red; }
.state-off { color: @muted; }

entry {
  min-height: 36px; padding: 0 12px; color: @text; caret-color: @cyan;
  background: #151d30; border: 1px solid @border; border-radius: 10px; box-shadow: none;
}
entry:focus { border-color: @cyan; }
combobox button, combobox box {
  min-height: 34px; color: @text; background: #151d30;
  border: 1px solid @border; border-radius: 10px; box-shadow: none;
}
.form-label { color: @muted; font-size: 10px; font-weight: 800; }
.hint { color: @muted; font-size: 10px; }
.warning-box { padding: 10px 14px; color: @amber; background: alpha(@amber, .08); border: 1px solid alpha(@amber, .30); border-radius: 10px; font-size: 10px; }

#empty { margin: 60px 28px; }
.empty-icon { color: @violet; font-size: 46px; }
.empty-title { margin-top: 12px; color: @text; font-size: 15px; font-weight: 800; }
.empty-copy { margin-top: 6px; color: @muted; font-size: 10px; }

.actions { min-height: 64px; padding: 0 18px; border-top: 1px solid @border; background: @panel; }
button.action {
  min-height: 35px; padding: 0 14px; color: @text;
  background: @panel2; border: 1px solid @border; border-radius: 9px; box-shadow: none;
  font-size: 10px; font-weight: 800;
}
button.action:hover { background: @hover; border-color: alpha(@cyan, .45); }
button.action.primary { color: #061014; background: @cyan; border-color: @cyan; }
button.action.primary:hover { background: #93f2fb; }
button.action.danger { color: @red; }
button.action.danger:hover { background: alpha(@red, .10); border-color: alpha(@red, .55); }
button:disabled { opacity: .38; }

#statusbar { min-height: 34px; padding: 0 18px; color: @muted; background: @panel; border-top: 1px solid @border; font-size: 9px; }
spinner { color: @cyan; }
scrollbar slider { min-width: 6px; min-height: 32px; background: #34415d; border-radius: 9px; }
scrollbar trough { background: transparent; }
"""


# --------------------------------------------------------------------------- #
# nmcli helpers
# --------------------------------------------------------------------------- #


class NmcliError(RuntimeError):
    pass


def nmcli(*args, timeout=NMCLI_TIMEOUT):
    env = dict(os.environ, LC_ALL="C")
    try:
        result = subprocess.run(
            ["nmcli", *args], capture_output=True, text=True, timeout=timeout, env=env
        )
    except FileNotFoundError as error:
        raise NmcliError("nmcli is not installed (install network-manager)") from error
    except subprocess.TimeoutExpired as error:
        raise NmcliError("NetworkManager did not answer in time") from error
    if result.returncode != 0:
        message = (result.stderr or result.stdout).strip()
        message = re.sub(r"^Error:\s*", "", message)
        raise NmcliError(message or f"nmcli exited with status {result.returncode}")
    return result.stdout


def split_terse(line):
    """Split one line of `nmcli -t` output, honouring `\\:` and `\\\\` escapes."""
    fields, current, escaped = [], [], False
    for char in line:
        if escaped:
            current.append(char)
            escaped = False
        elif char == "\\":
            escaped = True
        elif char == ":":
            fields.append("".join(current))
            current = []
        else:
            current.append(char)
    fields.append("".join(current))
    return fields


def terse_rows(output, width):
    rows = []
    for line in output.splitlines():
        if not line.strip():
            continue
        fields = split_terse(line)
        if len(fields) < width:
            fields += [""] * (width - len(fields))
        rows.append(fields[:width])
    return rows


def read_devices():
    rows = terse_rows(nmcli("-t", "-f", "DEVICE,TYPE,STATE,CONNECTION", "device"), 4)
    return [
        {"device": d, "type": t, "state": s, "connection": c}
        for d, t, s, c in rows
        if t not in HIDDEN_TYPES
    ]


def read_device_details():
    """Return IP details for every device keyed by interface name."""
    details, current = {}, None
    output = nmcli(
        "-t",
        "-f",
        "GENERAL.DEVICE,GENERAL.TYPE,GENERAL.HWADDR,GENERAL.STATE,GENERAL.CONNECTION,"
        "IP4.ADDRESS,IP4.GATEWAY,IP4.DNS,IP6.ADDRESS",
        "device",
        "show",
    )
    for line in output.splitlines():
        key, _, value = line.partition(":")
        value = value.replace("\\:", ":")
        base = key.split("[", 1)[0]
        if base == "GENERAL.DEVICE":
            current = details.setdefault(value, {"ip4": [], "dns": [], "ip6": []})
            continue
        if current is None or not value:
            continue
        if base == "IP4.ADDRESS":
            current["ip4"].append(value)
        elif base == "IP6.ADDRESS":
            current["ip6"].append(value)
        elif base == "IP4.DNS":
            current["dns"].append(value)
        elif base == "IP4.GATEWAY":
            current["gateway"] = value
        elif base == "GENERAL.HWADDR":
            current["mac"] = value
        elif base == "GENERAL.STATE":
            current["state"] = re.sub(r"^\d+\s*", "", value).strip("() ")
        elif base == "GENERAL.CONNECTION":
            current["connection"] = value
        elif base == "GENERAL.TYPE":
            current["type"] = value
    return details


def read_general():
    state, connectivity = (terse_rows(nmcli("-t", "-f", "STATE,CONNECTIVITY", "general"), 2) or [["", ""]])[0]
    radio = nmcli("-t", "-f", "WIFI", "radio").strip()
    return {"state": state, "connectivity": connectivity, "wifi_radio": radio == "enabled"}


def wifi_supports_ap(iface):
    try:
        output = nmcli("-t", "-f", "WIFI-PROPERTIES.AP", "device", "show", iface)
    except NmcliError:
        return None
    return output.strip().endswith(":yes")


def read_connections():
    rows = terse_rows(
        nmcli("-t", "-f", "NAME,UUID,TYPE,DEVICE,AUTOCONNECT,ACTIVE", "connection", "show"), 6
    )
    connections = []
    for name, uuid, kind, device, autoconnect, active in rows:
        if kind in HIDDEN_TYPES:
            continue
        connections.append(
            {
                "name": name,
                "uuid": uuid,
                "type": kind,
                "device": device if device != "--" else "",
                "autoconnect": autoconnect == "yes",
                "active": active == "yes",
            }
        )
    return connections


def connection_fields(ident, fields, secrets=False, by="uuid"):
    """Read profile properties as a dict (`connection show` prints one key:value per line)."""
    args = ["-s"] if secrets else []
    output = nmcli(*args, "-t", "-f", ",".join(fields), "connection", "show", by, ident)
    values = {}
    for line in output.splitlines():
        key, _, value = line.partition(":")
        values[key] = value
    return values


def wifi_profile_ssids(connections):
    """Map SSID -> saved profile for client-mode Wi-Fi connections."""
    mapping = {}
    for conn in connections:
        if conn["type"] != "802-11-wireless" or conn["name"] == HOTSPOT_NAME:
            continue
        try:
            values = connection_fields(conn["uuid"], ("802-11-wireless.ssid", "802-11-wireless.mode"))
        except NmcliError:
            continue
        ssid, mode = values.get("802-11-wireless.ssid", ""), values.get("802-11-wireless.mode", "")
        if mode == "ap":
            continue
        mapping.setdefault(ssid or conn["name"], conn)
    return mapping


def scan_wifi(iface, rescan):
    output = nmcli(
        "-t",
        "-f",
        "IN-USE,SSID,BSSID,SIGNAL,SECURITY,CHAN,FREQ,RATE",
        "device",
        "wifi",
        "list",
        "ifname",
        iface,
        "--rescan",
        "yes" if rescan else "no",
        timeout=30,
    )
    best = {}
    for in_use, ssid, bssid, signal, security, chan, freq, rate in terse_rows(output, 8):
        if not ssid:
            continue
        try:
            strength = int(signal)
        except ValueError:
            strength = 0
        entry = {
            "ssid": ssid,
            "bssid": bssid,
            "signal": strength,
            "security": "" if security in ("", "--") else security,
            "channel": chan,
            "freq": freq,
            "rate": rate,
            "in_use": in_use.strip() == "*",
        }
        previous = best.get(ssid)
        if previous is None or entry["in_use"] or (not previous["in_use"] and strength > previous["signal"]):
            best[ssid] = entry
    return sorted(best.values(), key=lambda n: (not n["in_use"], -n["signal"], n["ssid"].lower()))


def read_hotspot_settings():
    try:
        values = connection_fields(
            HOTSPOT_NAME,
            ("802-11-wireless.ssid", "802-11-wireless-security.psk", "802-11-wireless.band"),
            secrets=True,
            by="id",
        )
    except NmcliError:
        return None
    return {
        "ssid": values.get("802-11-wireless.ssid", ""),
        "password": values.get("802-11-wireless-security.psk", ""),
        "band": values.get("802-11-wireless.band", ""),
    }


def hotspot_clients(iface):
    try:
        output = subprocess.run(
            ["ip", "-4", "neigh", "show", "dev", iface], capture_output=True, text=True, timeout=5
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    clients = []
    for line in output.splitlines():
        parts = line.split()
        if not parts or "FAILED" in parts or "INCOMPLETE" in parts:
            continue
        mac = parts[parts.index("lladdr") + 1] if "lladdr" in parts else "?"
        clients.append((parts[0], mac))
    return clients


def signal_icon(strength):
    return SIGNAL_ICONS[min(4, max(0, strength // 20))]


def band_label(freq):
    digits = re.sub(r"\D", "", freq or "")
    if not digits:
        return ""
    mhz = int(digits)
    if mhz >= 5925:
        return "6 GHz"
    if mhz >= 4900:
        return "5 GHz"
    return "2.4 GHz"


def generate_password(length=12):
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def is_auth_failure(message):
    lowered = message.lower()
    return any(
        token in lowered
        for token in ("secrets were required", "802-1x supplicant", "no secrets", "password", "psk")
    )


# --------------------------------------------------------------------------- #
# UI helpers
# --------------------------------------------------------------------------- #


def label(text="", css=None, xalign=0.0, ellipsize=True, wrap=False, markup=False):
    widget = Gtk.Label()
    if markup:
        widget.set_markup(text)
    else:
        widget.set_text(text)
    widget.set_xalign(xalign)
    if ellipsize and not wrap:
        widget.set_ellipsize(Pango.EllipsizeMode.END)
    if wrap:
        widget.set_line_wrap(True)
        widget.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
    for name in (css or "").split():
        widget.get_style_context().add_class(name)
    return widget


def css_button(text, *classes, tooltip=None):
    button = Gtk.Button(label=text)
    for name in ("action", *classes):
        button.get_style_context().add_class(name)
    if tooltip:
        button.set_tooltip_text(tooltip)
    return button


def clear(container):
    for child in container.get_children():
        container.remove(child)


def scrolled(child):
    window = Gtk.ScrolledWindow()
    window.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
    window.add(child)
    return window


def empty_state(icon, title, copy):
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
    box.set_name("empty")
    box.set_valign(Gtk.Align.CENTER)
    box.pack_start(label(icon, "empty-icon", xalign=0.5), False, False, 0)
    box.pack_start(label(title, "empty-title", xalign=0.5), False, False, 0)
    copy_label = label(copy, "empty-copy", xalign=0.5, wrap=True)
    copy_label.set_justify(Gtk.Justification.CENTER)
    copy_label.set_halign(Gtk.Align.CENTER)
    copy_label.set_max_width_chars(70)
    box.pack_start(copy_label, False, False, 0)
    return box


def page_header(title, copy, *end_widgets):
    header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
    header.get_style_context().add_class("page-header")
    text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
    text.set_valign(Gtk.Align.CENTER)
    text.pack_start(label(title, "section-title"), False, False, 0)
    copy_label = label(copy, "section-copy")
    text.pack_start(copy_label, False, False, 0)
    header.pack_start(text, True, True, 0)
    for widget in end_widgets:
        widget.set_valign(Gtk.Align.CENTER)
        header.pack_end(widget, False, False, 0)
    header.copy_label = copy_label
    return header


def pill(text, kind):
    widget = label(text, f"pill {kind}", xalign=0.5, ellipsize=False)
    widget.set_valign(Gtk.Align.CENTER)
    return widget


# --------------------------------------------------------------------------- #
# Application
# --------------------------------------------------------------------------- #


class NetworkCenter(Gtk.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE)
        self.window = None
        self.page = "wifi"
        self.nav_buttons = {}
        self.nav_badges = {}
        self.busy = 0
        self.wifi_iface = None
        self.ap_capable = None
        self.general = {}
        self.devices = []
        self.details = {}
        self.connections = []
        self.saved_ssids = {}
        self.networks = []
        self.selected_ssid = None
        self.selected_uuid = None
        self.hotspot_loaded = False
        self.refresh_running = False

    # ---- lifecycle -------------------------------------------------------- #

    def do_startup(self):
        Gtk.Application.do_startup(self)
        provider = Gtk.CssProvider()
        provider.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

    def do_command_line(self, command_line):
        args = command_line.get_arguments()[1:]
        for arg in args:
            if arg.startswith("--page="):
                self.page = arg.split("=", 1)[1]
            elif arg in ("--hotspot", "--wifi", "--saved", "--overview"):
                self.page = arg[2:]
        self.activate()
        if self.window:
            self.show_page(self.page)
        return 0

    def do_activate(self):
        if self.window:
            self.window.present()
            self.refresh(rescan=False)
            return
        self.build_window()
        self.window.show_all()
        self.show_page(self.page)
        self.refresh(rescan=True)
        GLib.timeout_add_seconds(6, self.on_tick)

    def on_tick(self):
        if not self.window:
            return False
        if self.busy == 0 and not self.refresh_running:
            self.refresh(rescan=False, quiet=True)
        return True

    # ---- background work -------------------------------------------------- #

    def run_async(self, work, done=None, message=None):
        """Run `work()` off the UI thread, then `done(result, error)` on it."""
        self.busy += 1
        self.set_busy(message)

        def thread():
            try:
                result, error = work(), None
            except Exception as exc:  # noqa: BLE001 - surfaced to the user
                result, error = None, exc
            GLib.idle_add(finish, result, error)

        def finish(result, error):
            self.busy -= 1
            self.set_busy(None)
            if done:
                done(result, error)
            elif error:
                self.status(str(error), "bad")
            return False

        threading.Thread(target=thread, daemon=True).start()

    def set_busy(self, message):
        if self.busy > 0:
            self.spinner.start()
            if message:
                self.status(message, "busy")
        else:
            self.spinner.stop()

    def status(self, text, kind="info"):
        colors = {"good": "#78f0c2", "bad": "#ff6b81", "warn": "#ffcc66", "busy": "#5ee7f7"}
        escaped = GLib.markup_escape_text(text)
        if kind in colors:
            self.status_label.set_markup(f"<span foreground='{colors[kind]}'><b>{escaped}</b></span>")
        else:
            self.status_label.set_text(text)

    def refresh(self, rescan=False, quiet=False):
        if self.refresh_running:
            return
        self.refresh_running = True

        def work():
            general = read_general()
            devices = read_devices()
            details = read_device_details()
            connections = read_connections()
            saved = wifi_profile_ssids(connections)
            wifi = next((d for d in devices if d["type"] == "wifi"), None)
            iface = wifi["device"] if wifi else None
            networks, scan_error = [], None
            ap = None
            if iface:
                ap = wifi_supports_ap(iface)
                if general["wifi_radio"]:
                    try:
                        networks = scan_wifi(iface, rescan)
                    except NmcliError as error:
                        scan_error = str(error)
                        if rescan:
                            networks = scan_wifi(iface, False)
            return general, devices, details, connections, saved, iface, ap, networks, scan_error

        def done(result, error):
            self.refresh_running = False
            if error:
                self.status(str(error), "bad")
                return
            (self.general, self.devices, self.details, self.connections, self.saved_ssids,
             self.wifi_iface, self.ap_capable, self.networks, scan_error) = result
            self.render_all()
            if scan_error and not quiet:
                self.status(f"Scan: {scan_error}", "warn")
            elif not quiet:
                self.status(f"Updated  •  {len(self.networks)} networks  •  {len(self.connections)} saved profiles")

        self.run_async(work, done, None if quiet else ("Scanning for networks…" if rescan else "Refreshing…"))

    # ---- window ----------------------------------------------------------- #

    def build_window(self):
        self.window = Gtk.ApplicationWindow(application=self)
        self.window.set_title("Network Center")
        self.window.set_default_size(1060, 720)
        self.window.set_size_request(860, 560)
        self.window.set_position(Gtk.WindowPosition.CENTER)
        self.window.connect("key-press-event", self.on_key_press)
        self.window.connect("destroy", self.on_destroy)

        header = Gtk.HeaderBar()
        header.set_show_close_button(True)
        header.props.title = "NETWORK CENTER"
        header.props.subtitle = "Checking NetworkManager…"
        self.header = header
        refresh_button = Gtk.Button(label="󰑐")
        refresh_button.set_tooltip_text("Rescan and refresh (F5)")
        refresh_button.get_style_context().add_class("action")
        refresh_button.connect("clicked", lambda *_: self.refresh(rescan=True))
        header.pack_end(refresh_button)
        self.spinner = Gtk.Spinner()
        header.pack_end(self.spinner)
        self.window.set_titlebar(header)

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        root.set_name("root")
        body = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        root.pack_start(body, True, True, 0)
        body.pack_start(self.build_sidebar(), False, False, 0)

        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self.stack.set_transition_duration(120)
        self.stack.add_named(self.build_overview_page(), "overview")
        self.stack.add_named(self.build_wifi_page(), "wifi")
        self.stack.add_named(self.build_saved_page(), "saved")
        self.stack.add_named(self.build_hotspot_page(), "hotspot")
        body.pack_start(self.stack, True, True, 0)

        statusbar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        statusbar.set_name("statusbar")
        self.status_label = label("Ready")
        statusbar.pack_start(self.status_label, True, True, 0)
        statusbar.pack_end(label("F5 rescan  •  Ctrl+1-4 pages  •  Esc close", xalign=1.0), False, False, 0)
        root.pack_start(statusbar, False, False, 0)
        self.window.add(root)

    def on_destroy(self, *_args):
        self.window = None

    def build_sidebar(self):
        sidebar = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        sidebar.set_name("sidebar")
        sidebar.pack_start(label("CONTROL", "sidebar-title"), False, False, 0)
        for key, name, icon in PAGES:
            button = Gtk.Button()
            button.get_style_context().add_class("nav")
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            row.pack_start(label(icon, "nav-icon", xalign=0.5, ellipsize=False), False, False, 0)
            row.pack_start(label(name, "nav-name"), True, True, 0)
            badge = label("", "nav-badge", xalign=1.0, ellipsize=False)
            row.pack_end(badge, False, False, 0)
            button.add(row)
            button.connect("clicked", lambda _b, k=key: self.show_page(k))
            sidebar.pack_start(button, False, False, 0)
            self.nav_buttons[key] = button
            self.nav_badges[key] = badge

        sidebar.pack_start(Gtk.Box(), True, True, 0)
        tools = label("TOOLS", "sidebar-title")
        sidebar.pack_start(tools, False, False, 0)
        nmtui = css_button("󰆍  Open nmtui", tooltip="Advanced editing in the terminal (VPN, 802.1X, static IP)")
        nmtui.connect("clicked", self.open_nmtui)
        sidebar.pack_start(nmtui, False, False, 2)
        return sidebar

    def show_page(self, key):
        if key not in self.nav_buttons:
            key = "wifi"
        self.page = key
        self.stack.set_visible_child_name(key)
        for name, button in self.nav_buttons.items():
            context = button.get_style_context()
            (context.add_class if name == key else context.remove_class)("active")

    def open_nmtui(self, *_args):
        script = os.path.expanduser("~/.config/hypr/scripts/WaybarScripts.sh")
        try:
            if os.access(script, os.X_OK):
                subprocess.Popen([script, "--nmtui"], start_new_session=True)
            else:
                subprocess.Popen(["kitty", "nmtui"], start_new_session=True)
        except OSError as error:
            self.status(f"Could not open nmtui: {error}", "bad")

    def on_key_press(self, _window, event):
        control = bool(event.state & Gdk.ModifierType.CONTROL_MASK)
        if event.keyval == Gdk.KEY_Escape:
            self.window.close()
            return True
        if event.keyval == Gdk.KEY_F5:
            self.refresh(rescan=True)
            return True
        if control and Gdk.KEY_1 <= event.keyval <= Gdk.KEY_4:
            self.show_page(PAGES[event.keyval - Gdk.KEY_1][0])
            return True
        return False

    # ---- rendering -------------------------------------------------------- #

    def render_all(self):
        connectivity = self.general.get("connectivity", "unknown")
        active = [d for d in self.devices if d["state"] == "connected" and d["type"] not in ("bridge", "tun")]
        summary = ", ".join(d["connection"] for d in active[:2]) or "No active connection"
        self.header.props.subtitle = f"{summary}  •  internet: {connectivity}"
        self.nav_badges["wifi"].set_text(str(len(self.networks)) if self.wifi_iface else "—")
        self.nav_badges["saved"].set_text(str(len(self.connections)))
        hotspot_on = any(c["name"] == HOTSPOT_NAME and c["active"] for c in self.connections)
        self.nav_badges["hotspot"].set_text("ON" if hotspot_on else ("—" if not self.wifi_iface else ""))
        self.render_overview()
        self.render_wifi()
        self.render_saved()
        self.render_hotspot()

    # ---- overview page ---------------------------------------------------- #

    def build_overview_page(self):
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        page.get_style_context().add_class("page")
        page.pack_start(page_header("Overview", "Live state of every network interface"), False, False, 0)
        self.overview_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.overview_box.set_margin_start(22)
        self.overview_box.set_margin_end(22)
        self.overview_box.set_margin_top(18)
        self.overview_box.set_margin_bottom(18)
        page.pack_start(scrolled(self.overview_box), True, True, 0)
        return page

    def render_overview(self):
        clear(self.overview_box)
        connectivity = self.general.get("connectivity", "unknown")
        state_class = {"full": "state-good", "limited": "state-warn", "portal": "state-warn"}.get(
            connectivity, "state-bad"
        )
        state_text = {
            "full": "Online",
            "limited": "Limited connectivity",
            "portal": "Captive portal — sign in required",
            "none": "Offline",
        }.get(connectivity, connectivity.capitalize() or "Unknown")

        hero = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=14)
        hero.get_style_context().add_class("card")
        hero.pack_start(label("󰖟", "card-icon", ellipsize=False), False, False, 0)
        texts = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        texts.pack_start(label(state_text, f"big-state {state_class}"), False, False, 0)
        wifi_text = (
            f"Wi-Fi adapter: {self.wifi_iface} ({'radio on' if self.general.get('wifi_radio') else 'radio off'})"
            if self.wifi_iface
            else "No Wi-Fi adapter detected on this machine"
        )
        texts.pack_start(label(wifi_text, "section-copy"), False, False, 0)
        hero.pack_start(texts, True, True, 0)
        if self.wifi_iface:
            radio = Gtk.Switch()
            radio.set_active(bool(self.general.get("wifi_radio")))
            radio.set_valign(Gtk.Align.CENTER)
            radio.set_tooltip_text("Wi-Fi radio")
            radio.connect("notify::active", self.on_radio_toggled)
            hero.pack_end(radio, False, False, 0)
        self.overview_box.pack_start(hero, False, False, 0)

        grid = Gtk.FlowBox()
        grid.set_selection_mode(Gtk.SelectionMode.NONE)
        grid.set_max_children_per_line(2)
        grid.set_min_children_per_line(1)
        grid.set_column_spacing(12)
        grid.set_row_spacing(12)
        grid.set_homogeneous(True)
        for device in self.devices:
            if "externally" not in device["state"]:
                grid.add(self.device_card(device))
        self.overview_box.pack_start(grid, False, False, 0)
        self.overview_box.show_all()

    def device_card(self, device):
        info = self.details.get(device["device"], {})
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        card.get_style_context().add_class("card")
        top = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        top.pack_start(label(TYPE_ICONS.get(device["type"], "󰛳"), "card-icon", ellipsize=False), False, False, 0)
        names = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        names.pack_start(label(device["device"], "card-title"), False, False, 0)
        names.pack_start(label(device["type"], "row-meta"), False, False, 0)
        top.pack_start(names, True, True, 0)
        state = device["state"]
        kind = "on" if state == "connected" else ("warn" if "connecting" in state else "off")
        top.pack_end(pill(state.upper(), kind), False, False, 0)
        card.pack_start(top, False, False, 0)

        grid = Gtk.Grid(column_spacing=14, row_spacing=4)
        rows = [
            ("Connection", device["connection"] if device["connection"] != "--" else "—"),
            ("IPv4", ", ".join(info.get("ip4", [])) or "—"),
            ("Gateway", info.get("gateway") or "—"),
            ("DNS", ", ".join(info.get("dns", [])) or "—"),
            ("MAC", info.get("mac") or "—"),
        ]
        for index, (key, value) in enumerate(rows):
            grid.attach(label(key, "kv-key"), 0, index, 1, 1)
            value_label = label(value, "kv-value")
            value_label.set_selectable(True)
            value_label.set_hexpand(True)
            grid.attach(value_label, 1, index, 1, 1)
        card.pack_start(grid, False, False, 0)

        if device["state"] == "connected" and device["type"] not in ("bridge", "tun", "loopback"):
            actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            disconnect = css_button("Disconnect", "danger")
            disconnect.connect("clicked", lambda *_: self.disconnect_device(device["device"]))
            actions.pack_end(disconnect, False, False, 0)
            card.pack_start(actions, False, False, 0)
        elif device["state"] == "disconnected" and device["type"] in ("ethernet", "wifi"):
            actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            connect = css_button("Connect", "primary")
            connect.connect("clicked", lambda *_: self.connect_device(device["device"]))
            actions.pack_end(connect, False, False, 0)
            card.pack_start(actions, False, False, 0)
        return card

    # ---- Wi-Fi page ------------------------------------------------------- #

    def build_wifi_page(self):
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        page.get_style_context().add_class("page")
        self.wifi_switch = Gtk.Switch()
        self.wifi_switch.set_tooltip_text("Wi-Fi radio on/off")
        self.wifi_switch_handler = self.wifi_switch.connect("notify::active", self.on_radio_toggled)
        hidden = css_button("󰛐  Hidden network", tooltip="Connect to a network that does not broadcast its name")
        hidden.connect("clicked", self.on_hidden_network)
        self.wifi_header = page_header("Wi-Fi", "Nearby networks", self.wifi_switch, hidden)
        page.pack_start(self.wifi_header, False, False, 0)

        self.wifi_stack = Gtk.Stack()
        self.wifi_list = Gtk.ListBox()
        self.wifi_list.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.wifi_list.connect("row-selected", self.on_wifi_selected)
        self.wifi_list.connect("row-activated", lambda *_: self.on_wifi_primary())
        self.wifi_stack.add_named(scrolled(self.wifi_list), "list")
        self.wifi_empty = Gtk.Box()
        self.wifi_stack.add_named(self.wifi_empty, "empty")
        page.pack_start(self.wifi_stack, True, True, 0)

        actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        actions.get_style_context().add_class("actions")
        self.wifi_detail = label("Select a network", "hint")
        actions.pack_start(self.wifi_detail, True, True, 0)
        self.wifi_forget = css_button("Forget", "danger")
        self.wifi_forget.connect("clicked", lambda *_: self.on_wifi_forget())
        self.wifi_primary = css_button("Connect", "primary")
        self.wifi_primary.connect("clicked", lambda *_: self.on_wifi_primary())
        for widget in (self.wifi_primary, self.wifi_forget):
            widget.set_valign(Gtk.Align.CENTER)
            actions.pack_end(widget, False, False, 0)
        page.pack_start(actions, False, False, 0)
        return page

    def render_wifi(self):
        self.wifi_switch.handler_block(self.wifi_switch_handler)
        self.wifi_switch.set_active(bool(self.general.get("wifi_radio")))
        self.wifi_switch.handler_unblock(self.wifi_switch_handler)
        self.wifi_switch.set_sensitive(self.wifi_iface is not None)

        if not self.wifi_iface:
            self.set_empty(
                self.wifi_stack,
                "wifi",
                empty_state(
                    "󰖪",
                    "No Wi-Fi adapter detected",
                    "NetworkManager does not see any wireless hardware on this machine. Plug in a USB "
                    "Wi-Fi dongle or install the adapter's driver and this page will light up automatically. "
                    "Wired and saved connections are still managed from Overview and Saved.",
                ),
            )
            self.wifi_header.copy_label.set_text("No wireless hardware")
            self.update_wifi_actions()
            return
        if not self.general.get("wifi_radio"):
            self.set_empty(
                self.wifi_stack,
                "wifi",
                empty_state("󰖪", "Wi-Fi is turned off", "Use the switch above to turn the radio on and scan."),
            )
            self.wifi_header.copy_label.set_text(f"{self.wifi_iface}  •  radio off")
            self.update_wifi_actions()
            return

        current = next((n for n in self.networks if n["in_use"]), None)
        self.wifi_header.copy_label.set_text(
            f"{self.wifi_iface}  •  {len(self.networks)} networks"
            + (f"  •  connected to {current['ssid']}" if current else "")
        )
        clear(self.wifi_list)
        if not self.networks:
            self.set_empty(
                self.wifi_stack,
                "wifi",
                empty_state("󰤮", "No networks found", "Press F5 or the refresh button to scan again."),
            )
            self.update_wifi_actions()
            return

        reselect = None
        for network in self.networks:
            row = self.wifi_row(network)
            self.wifi_list.add(row)
            if network["ssid"] == self.selected_ssid:
                reselect = row
        self.wifi_list.show_all()
        self.wifi_stack.set_visible_child_name("list")
        if reselect:
            self.wifi_list.select_row(reselect)
        self.update_wifi_actions()

    def set_empty(self, stack, key, widget):
        holder = stack.get_child_by_name("empty")
        clear(holder)
        holder.pack_start(widget, True, True, 0)
        holder.show_all()
        stack.set_visible_child_name("empty")
        if key == "wifi":
            self.selected_ssid = None

    def wifi_row(self, network):
        row = Gtk.ListBoxRow()
        row.network = network
        context = row.get_style_context()
        context.add_class("net-row")
        if network["in_use"]:
            context.add_class("current")
        inner = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        inner.get_style_context().add_class("row-inner")
        icon = label(signal_icon(network["signal"]), "row-icon", xalign=0.5, ellipsize=False)
        icon.get_style_context().add_class("strong" if network["signal"] >= 60 else ("weak" if network["signal"] < 35 else ""))
        icon.set_valign(Gtk.Align.CENTER)
        inner.pack_start(icon, False, False, 0)

        texts = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        texts.set_valign(Gtk.Align.CENTER)
        texts.pack_start(label(network["ssid"], "row-title"), False, False, 0)
        meta = [f"{network['signal']}%", band_label(network["freq"]), f"ch {network['channel']}" if network["channel"] else "",
                network["security"] or "Open"]
        texts.pack_start(label("  •  ".join(m for m in meta if m), "row-meta"), False, False, 0)
        inner.pack_start(texts, True, True, 0)

        if network["in_use"]:
            inner.pack_end(pill("CONNECTED", "on"), False, False, 0)
        elif network["ssid"] in self.saved_ssids:
            inner.pack_end(pill("SAVED", "off"), False, False, 0)
        if network["security"]:
            lock = label("󰌾", "lock", ellipsize=False)
            lock.set_valign(Gtk.Align.CENTER)
            inner.pack_end(lock, False, False, 0)
        row.add(inner)
        return row

    def on_wifi_selected(self, _listbox, row):
        self.selected_ssid = row.network["ssid"] if row else None
        self.update_wifi_actions()

    def selected_network(self):
        return next((n for n in self.networks if n["ssid"] == self.selected_ssid), None)

    def update_wifi_actions(self):
        network = self.selected_network() if self.wifi_iface else None
        if not network:
            self.wifi_primary.set_label("Connect")
            self.wifi_primary.set_sensitive(False)
            self.wifi_forget.set_sensitive(False)
            self.wifi_detail.set_text("Select a network  •  double-click or Enter to connect")
            return
        saved = network["ssid"] in self.saved_ssids
        self.wifi_primary.set_sensitive(True)
        self.wifi_primary.set_label("Disconnect" if network["in_use"] else "Connect")
        context = self.wifi_primary.get_style_context()
        if network["in_use"]:
            context.remove_class("primary")
        else:
            context.add_class("primary")
        self.wifi_forget.set_sensitive(saved)
        details = [network["ssid"], network["bssid"], network["rate"]]
        self.wifi_detail.set_text("  •  ".join(d for d in details if d))

    def on_wifi_primary(self):
        network = self.selected_network()
        if not network:
            return
        if network["in_use"]:
            self.disconnect_device(self.wifi_iface)
        else:
            self.connect_wifi(network)

    def connect_wifi(self, network, password=None, hidden=False):
        ssid = network["ssid"]
        profile = self.saved_ssids.get(ssid)
        if profile and password is None:
            self.run_async(
                lambda: nmcli("connection", "up", "uuid", profile["uuid"], "ifname", self.wifi_iface, timeout=90),
                lambda _r, error: self.after_connect(network, error, retry_with_password=True),
                f"Connecting to {ssid}…",
            )
            return
        if network.get("security") and password is None and not hidden:
            password = self.ask_password(ssid, network["security"])
            if password is None:
                return

        def work():
            if profile:
                nmcli("connection", "delete", "uuid", profile["uuid"])
            args = ["device", "wifi", "connect", ssid, "ifname", self.wifi_iface]
            if password:
                args += ["password", password]
            if hidden:
                args += ["hidden", "yes"]
            try:
                return nmcli(*args, timeout=90)
            except NmcliError:
                # nmcli keeps a half-created profile after a failed attempt; drop it
                # so the next try asks for the password again.
                try:
                    nmcli("connection", "delete", "id", ssid)
                except NmcliError:
                    pass
                raise

        self.run_async(work, lambda _r, error: self.after_connect(network, error), f"Connecting to {ssid}…")

    def after_connect(self, network, error, retry_with_password=False):
        if not error:
            self.status(f"Connected to {network['ssid']}", "good")
            self.refresh()
            return
        message = str(error)
        if retry_with_password and network.get("security") and is_auth_failure(message):
            self.status("Saved password was rejected — enter it again", "warn")
            password = self.ask_password(network["ssid"], network["security"], retry=True)
            if password is not None:
                self.connect_wifi(network, password=password)
            return
        if is_auth_failure(message):
            message = "Wrong password or authentication failed"
        self.status(f"Could not connect to {network['ssid']}: {message}", "bad")
        self.refresh()

    def on_wifi_forget(self):
        network = self.selected_network()
        profile = self.saved_ssids.get(network["ssid"]) if network else None
        if not profile:
            return
        if not self.confirm(f"Forget “{network['ssid']}”?", "The saved password and settings will be removed."):
            return
        self.run_async(
            lambda: nmcli("connection", "delete", "uuid", profile["uuid"]),
            lambda _r, error: self.after_action(error, f"Forgot {network['ssid']}"),
            "Removing saved network…",
        )

    def on_hidden_network(self, *_args):
        if not self.wifi_iface:
            self.status("No Wi-Fi adapter detected", "warn")
            return
        dialog, entries = self.form_dialog(
            "Connect to hidden network",
            "Enter the exact network name. Leave the password empty for open networks.",
            [("Network name (SSID)", False), ("Password", True)],
            "Connect",
        )
        response = dialog.run()
        ssid, password = entries[0].get_text().strip(), entries[1].get_text()
        dialog.destroy()
        if response != Gtk.ResponseType.OK or not ssid:
            return
        network = {"ssid": ssid, "security": "WPA" if password else ""}
        self.connect_wifi(network, password=password or "", hidden=True)

    def on_radio_toggled(self, switch, _pspec):
        enabled = switch.get_active()
        self.run_async(
            lambda: nmcli("radio", "wifi", "on" if enabled else "off"),
            lambda _r, error: self.after_radio(error, enabled),
            "Turning Wi-Fi on…" if enabled else "Turning Wi-Fi off…",
        )

    def after_radio(self, error, enabled):
        if error:
            self.status(str(error), "bad")
            self.refresh()
            return
        self.status("Wi-Fi on — scanning…" if enabled else "Wi-Fi off", "good")
        # Give the driver a moment before scanning.
        GLib.timeout_add(1800 if enabled else 200, lambda: (self.refresh(rescan=enabled), False)[1])

    def disconnect_device(self, iface):
        self.run_async(
            lambda: nmcli("device", "disconnect", iface),
            lambda _r, error: self.after_action(error, f"Disconnected {iface}"),
            f"Disconnecting {iface}…",
        )

    def connect_device(self, iface):
        self.run_async(
            lambda: nmcli("device", "connect", iface, timeout=90),
            lambda _r, error: self.after_action(error, f"Connected {iface}"),
            f"Connecting {iface}…",
        )

    def after_action(self, error, success):
        if error:
            self.status(str(error), "bad")
        else:
            self.status(success, "good")
        self.refresh()

    # ---- saved page ------------------------------------------------------- #

    def build_saved_page(self):
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        page.get_style_context().add_class("page")
        page.pack_start(
            page_header("Saved connections", "Every NetworkManager profile: Wi-Fi, wired, VPN, hotspot"), False, False, 0
        )
        self.saved_list = Gtk.ListBox()
        self.saved_list.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.saved_list.connect("row-selected", self.on_saved_selected)
        self.saved_list.connect("row-activated", lambda *_: self.on_saved_primary())
        page.pack_start(scrolled(self.saved_list), True, True, 0)

        actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        actions.get_style_context().add_class("actions")
        self.saved_auto = Gtk.CheckButton(label="Connect automatically")
        self.saved_auto.get_style_context().add_class("hint")
        self.saved_auto_handler = self.saved_auto.connect("toggled", self.on_saved_autoconnect)
        self.saved_auto.set_valign(Gtk.Align.CENTER)
        actions.pack_start(self.saved_auto, False, False, 0)
        self.saved_forget = css_button("Forget", "danger")
        self.saved_forget.connect("clicked", lambda *_: self.on_saved_forget())
        self.saved_primary = css_button("Activate", "primary")
        self.saved_primary.connect("clicked", lambda *_: self.on_saved_primary())
        for widget in (self.saved_primary, self.saved_forget):
            widget.set_valign(Gtk.Align.CENTER)
            actions.pack_end(widget, False, False, 0)
        page.pack_start(actions, False, False, 0)
        return page

    def render_saved(self):
        clear(self.saved_list)
        reselect = None
        external = {d["connection"] for d in self.devices if "externally" in d["state"]}
        ordered = sorted((c for c in self.connections if not (c["active"] and c["name"] in external)), key=lambda c: (not c["active"], c["type"], c["name"].lower()))
        for conn in ordered:
            row = Gtk.ListBoxRow()
            row.conn = conn
            context = row.get_style_context()
            context.add_class("net-row")
            if conn["active"]:
                context.add_class("current")
            inner = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
            inner.get_style_context().add_class("row-inner")
            icon = label(TYPE_ICONS.get(conn["type"], "󰛳"), "row-icon", xalign=0.5, ellipsize=False)
            icon.set_valign(Gtk.Align.CENTER)
            inner.pack_start(icon, False, False, 0)
            texts = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            texts.set_valign(Gtk.Align.CENTER)
            texts.pack_start(label(conn["name"], "row-title"), False, False, 0)
            kind = {"802-11-wireless": "Wi-Fi", "802-3-ethernet": "Ethernet"}.get(conn["type"], conn["type"])
            meta = [kind, conn["device"], "auto-connect" if conn["autoconnect"] else "manual"]
            texts.pack_start(label("  •  ".join(m for m in meta if m), "row-meta"), False, False, 0)
            inner.pack_start(texts, True, True, 0)
            inner.pack_end(pill("ACTIVE", "on") if conn["active"] else pill("IDLE", "off"), False, False, 0)
            row.add(inner)
            self.saved_list.add(row)
            if conn["uuid"] == self.selected_uuid:
                reselect = row
        self.saved_list.show_all()
        if reselect:
            self.saved_list.select_row(reselect)
        self.update_saved_actions()

    def selected_connection(self):
        return next((c for c in self.connections if c["uuid"] == self.selected_uuid), None)

    def on_saved_selected(self, _listbox, row):
        self.selected_uuid = row.conn["uuid"] if row else None
        self.update_saved_actions()

    def update_saved_actions(self):
        conn = self.selected_connection()
        self.saved_primary.set_sensitive(conn is not None)
        self.saved_forget.set_sensitive(conn is not None)
        self.saved_auto.set_sensitive(conn is not None)
        self.saved_auto.handler_block(self.saved_auto_handler)
        self.saved_auto.set_active(bool(conn and conn["autoconnect"]))
        self.saved_auto.handler_unblock(self.saved_auto_handler)
        context = self.saved_primary.get_style_context()
        if conn and conn["active"]:
            self.saved_primary.set_label("Deactivate")
            context.remove_class("primary")
        else:
            self.saved_primary.set_label("Activate")
            context.add_class("primary")

    def on_saved_primary(self):
        conn = self.selected_connection()
        if not conn:
            return
        action = "down" if conn["active"] else "up"
        self.run_async(
            lambda: nmcli("connection", action, "uuid", conn["uuid"], timeout=90),
            lambda _r, error: self.after_action(
                error, f"{'Deactivated' if action == 'down' else 'Activated'} {conn['name']}"
            ),
            f"{'Deactivating' if action == 'down' else 'Activating'} {conn['name']}…",
        )

    def on_saved_forget(self):
        conn = self.selected_connection()
        if not conn:
            return
        warning = "This profile is currently active and will disconnect.\n" if conn["active"] else ""
        if not self.confirm(f"Forget “{conn['name']}”?", warning + "The profile and its saved secrets will be deleted."):
            return
        self.run_async(
            lambda: nmcli("connection", "delete", "uuid", conn["uuid"]),
            lambda _r, error: self.after_action(error, f"Forgot {conn['name']}"),
            "Removing profile…",
        )

    def on_saved_autoconnect(self, button):
        conn = self.selected_connection()
        if not conn:
            return
        value = "yes" if button.get_active() else "no"
        self.run_async(
            lambda: nmcli("connection", "modify", "uuid", conn["uuid"], "connection.autoconnect", value),
            lambda _r, error: self.after_action(
                error, f"{conn['name']}: auto-connect {'on' if value == 'yes' else 'off'}"
            ),
        )

    # ---- hotspot page ----------------------------------------------------- #

    def build_hotspot_page(self):
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        page.get_style_context().add_class("page")
        page.pack_start(
            page_header("Hotspot", "Share this machine's internet connection over Wi-Fi"), False, False, 0
        )
        self.hotspot_stack = Gtk.Stack()
        page.pack_start(self.hotspot_stack, True, True, 0)

        form = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        form.set_margin_start(22)
        form.set_margin_end(22)
        form.set_margin_top(18)
        form.set_margin_bottom(18)

        status = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=14)
        status.get_style_context().add_class("card")
        status.pack_start(label("󰀂", "card-icon", ellipsize=False), False, False, 0)
        texts = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.hotspot_state = label("Hotspot is off", "big-state")
        self.hotspot_sub = label("", "section-copy")
        texts.pack_start(self.hotspot_state, False, False, 0)
        texts.pack_start(self.hotspot_sub, False, False, 0)
        status.pack_start(texts, True, True, 0)
        self.hotspot_toggle = css_button("Start hotspot", "primary")
        self.hotspot_toggle.set_valign(Gtk.Align.CENTER)
        self.hotspot_toggle.connect("clicked", self.on_hotspot_toggle)
        status.pack_end(self.hotspot_toggle, False, False, 0)
        form.pack_start(status, False, False, 0)

        self.hotspot_warning = label("", "warning-box", wrap=True)
        form.pack_start(self.hotspot_warning, False, False, 0)

        settings = Gtk.Grid(column_spacing=14, row_spacing=10)
        settings.get_style_context().add_class("card")
        settings.attach(label("NETWORK NAME", "form-label"), 0, 0, 1, 1)
        self.hotspot_ssid = Gtk.Entry()
        self.hotspot_ssid.set_hexpand(True)
        self.hotspot_ssid.set_max_length(32)
        settings.attach(self.hotspot_ssid, 1, 0, 2, 1)

        settings.attach(label("PASSWORD", "form-label"), 0, 1, 1, 1)
        self.hotspot_password = Gtk.Entry()
        self.hotspot_password.set_visibility(False)
        self.hotspot_password.set_max_length(63)
        self.hotspot_password.set_icon_from_icon_name(Gtk.EntryIconPosition.SECONDARY, "view-reveal-symbolic")
        self.hotspot_password.set_icon_tooltip_text(Gtk.EntryIconPosition.SECONDARY, "Show / hide")
        self.hotspot_password.connect(
            "icon-press", lambda entry, *_: entry.set_visibility(not entry.get_visibility())
        )
        settings.attach(self.hotspot_password, 1, 1, 1, 1)
        generate = css_button("󰒓  Generate", tooltip="Create a random 12-character password")
        generate.connect("clicked", self.on_generate_password)
        settings.attach(generate, 2, 1, 1, 1)

        settings.attach(label("BAND", "form-label"), 0, 2, 1, 1)
        self.hotspot_band = Gtk.ComboBoxText()
        for key, text in (("", "Automatic"), ("bg", "2.4 GHz — best range & compatibility"), ("a", "5 GHz — faster, shorter range")):
            self.hotspot_band.append(key, text)
        self.hotspot_band.set_active_id("bg")
        settings.attach(self.hotspot_band, 1, 2, 2, 1)

        copy_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        copy_creds = css_button("󰆏  Copy credentials")
        copy_creds.connect("clicked", self.on_copy_hotspot)
        copy_box.pack_end(copy_creds, False, False, 0)
        save = css_button("Save settings")
        save.set_tooltip_text("Store the settings without starting the hotspot")
        save.connect("clicked", lambda *_: self.save_hotspot(start=False))
        copy_box.pack_end(save, False, False, 0)
        settings.attach(copy_box, 0, 3, 3, 1)
        settings.attach(
            label("Password must be 8-63 characters (WPA2). Settings are stored in the NetworkManager "
                  f"profile “{HOTSPOT_NAME}”.", "hint", wrap=True),
            0, 4, 3, 1,
        )
        form.pack_start(settings, False, False, 0)

        clients_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        clients_card.get_style_context().add_class("card")
        clients_card.pack_start(label("CONNECTED DEVICES", "form-label"), False, False, 0)
        self.hotspot_clients = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        clients_card.pack_start(self.hotspot_clients, False, False, 0)
        form.pack_start(clients_card, False, False, 0)

        self.hotspot_stack.add_named(scrolled(form), "form")
        self.hotspot_stack.add_named(Gtk.Box(), "empty")
        return page

    def hotspot_connection(self):
        return next((c for c in self.connections if c["name"] == HOTSPOT_NAME), None)

    def render_hotspot(self):
        if not self.wifi_iface:
            self.set_empty(
                self.hotspot_stack,
                "hotspot",
                empty_state(
                    "󰀂",
                    "Hotspot needs a Wi-Fi adapter",
                    "This machine has no wireless hardware, so it cannot broadcast a hotspot. "
                    "The page becomes available as soon as NetworkManager detects a Wi-Fi device.",
                ),
            )
            return
        self.hotspot_stack.set_visible_child_name("form")

        if not self.hotspot_loaded:
            self.hotspot_loaded = True
            self.run_async(read_hotspot_settings, self.fill_hotspot_form)

        conn = self.hotspot_connection()
        active = bool(conn and conn["active"])
        ctx = self.hotspot_state.get_style_context()
        for name in ("state-good", "state-off"):
            ctx.remove_class(name)
        ctx.add_class("state-good" if active else "state-off")
        self.hotspot_state.set_text("Hotspot is ON" if active else "Hotspot is off")
        self.hotspot_toggle.set_label("Stop hotspot" if active else "Start hotspot")
        toggle_ctx = self.hotspot_toggle.get_style_context()
        if active:
            toggle_ctx.remove_class("primary")
            toggle_ctx.add_class("danger")
        else:
            toggle_ctx.remove_class("danger")
            toggle_ctx.add_class("primary")

        uplink = [
            d for d in self.devices
            if d["state"] == "connected" and d["type"] in ("ethernet", "gsm", "wifi", "bluetooth")
            and d["device"] != self.wifi_iface
        ]
        if active:
            ip = ", ".join(self.details.get(self.wifi_iface, {}).get("ip4", [])) or "—"
            self.hotspot_sub.set_text(f"Broadcasting on {self.wifi_iface}  •  gateway {ip}")
        else:
            self.hotspot_sub.set_text(
                f"Will share: {', '.join(d['connection'] for d in uplink)}" if uplink else "No other uplink — clients get a local network only"
            )

        warnings = []
        if self.ap_capable is False:
            warnings.append("This adapter does not report access-point (AP) support; starting a hotspot may fail.")
        wifi_device = next((d for d in self.devices if d["device"] == self.wifi_iface), None)
        if wifi_device and wifi_device["state"] == "connected" and not active:
            warnings.append(
                f"{self.wifi_iface} is connected to “{wifi_device['connection']}”. Most adapters cannot be a client and a "
                "hotspot at once, so starting the hotspot will drop that Wi-Fi connection."
            )
        if not self.general.get("wifi_radio"):
            warnings.append("Wi-Fi radio is off — it will be turned on when the hotspot starts.")
        self.hotspot_warning.set_text("\n".join(warnings))
        self.hotspot_warning.set_visible(bool(warnings))
        self.hotspot_warning.set_no_show_all(not warnings)

        clear(self.hotspot_clients)
        clients = hotspot_clients(self.wifi_iface) if active else []
        if clients:
            for ip, mac in clients:
                self.hotspot_clients.pack_start(label(f"󰾰  {ip}    {mac}", "kv-value"), False, False, 0)
        else:
            self.hotspot_clients.pack_start(
                label("No devices connected" if active else "Start the hotspot to see connected devices", "hint"),
                False, False, 0,
            )
        self.hotspot_clients.show_all()

    def fill_hotspot_form(self, settings, _error):
        if settings:
            self.hotspot_ssid.set_text(settings["ssid"])
            self.hotspot_password.set_text(settings["password"])
            self.hotspot_band.set_active_id(settings["band"] if settings["band"] in ("a", "bg") else "")
        if not self.hotspot_ssid.get_text():
            host = os.uname().nodename.split(".")[0] or "Linux"
            self.hotspot_ssid.set_text(f"{host}-hotspot"[:32])
        if not self.hotspot_password.get_text():
            self.hotspot_password.set_text(generate_password())

    def on_generate_password(self, *_args):
        self.hotspot_password.set_text(generate_password())
        self.hotspot_password.set_visibility(True)

    def on_copy_hotspot(self, *_args):
        text = f"Wi-Fi: {self.hotspot_ssid.get_text()}\nPassword: {self.hotspot_password.get_text()}"
        Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD).set_text(text, -1)
        self.status("Hotspot name and password copied", "good")

    def on_hotspot_toggle(self, *_args):
        conn = self.hotspot_connection()
        if conn and conn["active"]:
            self.run_async(
                lambda: nmcli("connection", "down", "id", HOTSPOT_NAME),
                lambda _r, error: self.after_action(error, "Hotspot stopped"),
                "Stopping hotspot…",
            )
            return
        self.save_hotspot(start=True)

    def save_hotspot(self, start):
        ssid = self.hotspot_ssid.get_text().strip()
        password = self.hotspot_password.get_text()
        band = self.hotspot_band.get_active_id() or ""
        if not ssid:
            self.status("Hotspot name cannot be empty", "bad")
            return
        if not 8 <= len(password) <= 63:
            self.status("Hotspot password must be 8-63 characters", "bad")
            return
        iface = self.wifi_iface
        exists = self.hotspot_connection() is not None

        def work():
            settings = [
                "connection.interface-name", iface,
                "connection.autoconnect", "no",
                "802-11-wireless.ssid", ssid,
                "802-11-wireless.mode", "ap",
                "802-11-wireless.band", band,
                "802-11-wireless.channel", "",
                "ipv4.method", "shared",
                "ipv6.method", "ignore",
                "wifi-sec.key-mgmt", "wpa-psk",
                "wifi-sec.proto", "rsn",
                "wifi-sec.pairwise", "ccmp",
                "wifi-sec.group", "ccmp",
                "wifi-sec.psk", password,
            ]
            if exists:
                nmcli("connection", "modify", "id", HOTSPOT_NAME, *settings)
            else:
                nmcli("connection", "add", "type", "wifi", "con-name", HOTSPOT_NAME, *settings)
            if start:
                nmcli("radio", "wifi", "on")
                nmcli("connection", "up", "id", HOTSPOT_NAME, timeout=90)

        def done(_result, error):
            if error:
                message = str(error)
                if start and self.ap_capable is False:
                    message += " (adapter has no AP mode)"
                self.status(f"Hotspot: {message}", "bad")
            else:
                self.status(f"Hotspot “{ssid}” is live" if start else "Hotspot settings saved", "good")
            self.refresh()

        self.run_async(work, done, "Starting hotspot…" if start else "Saving hotspot settings…")

    # ---- dialogs ---------------------------------------------------------- #

    def form_dialog(self, title, copy, fields, accept):
        dialog = Gtk.Dialog(transient_for=self.window, modal=True)
        dialog.set_title(title)
        dialog.set_default_size(420, -1)
        dialog.add_button("Cancel", Gtk.ResponseType.CANCEL)
        ok = dialog.add_button(accept, Gtk.ResponseType.OK)
        ok.get_style_context().add_class("action")
        ok.get_style_context().add_class("primary")
        dialog.set_default_response(Gtk.ResponseType.OK)
        box = dialog.get_content_area()
        box.set_spacing(8)
        box.set_margin_start(18)
        box.set_margin_end(18)
        box.set_margin_top(16)
        box.set_margin_bottom(10)
        box.pack_start(label(title, "section-title"), False, False, 0)
        box.pack_start(label(copy, "section-copy", wrap=True), False, False, 4)
        entries = []
        for name, secret in fields:
            box.pack_start(label(name.upper(), "form-label"), False, False, 0)
            entry = Gtk.Entry()
            entry.set_activates_default(True)
            if secret:
                entry.set_visibility(False)
                entry.set_icon_from_icon_name(Gtk.EntryIconPosition.SECONDARY, "view-reveal-symbolic")
                entry.connect("icon-press", lambda e, *_: e.set_visibility(not e.get_visibility()))
            box.pack_start(entry, False, False, 0)
            entries.append(entry)
        dialog.show_all()
        return dialog, entries

    def ask_password(self, ssid, security, retry=False):
        copy = f"{security} network." + (" The previous password did not work." if retry else "")
        dialog, entries = self.form_dialog(f"Connect to “{ssid}”", copy, [("Password", True)], "Connect")
        response = dialog.run()
        password = entries[0].get_text()
        dialog.destroy()
        if response != Gtk.ResponseType.OK:
            self.status("Connection cancelled")
            return None
        return password

    def confirm(self, title, copy):
        dialog = Gtk.MessageDialog(
            transient_for=self.window,
            flags=Gtk.DialogFlags.MODAL,
            message_type=Gtk.MessageType.WARNING,
            buttons=Gtk.ButtonsType.NONE,
            text=title,
        )
        dialog.format_secondary_text(copy)
        dialog.add_button("Cancel", Gtk.ResponseType.CANCEL)
        dialog.add_button("Forget", Gtk.ResponseType.ACCEPT)
        response = dialog.run()
        dialog.destroy()
        return response == Gtk.ResponseType.ACCEPT


if __name__ == "__main__":
    sys.exit(NetworkCenter().run(sys.argv))
