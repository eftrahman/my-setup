#!/usr/bin/env python3
"""Sound Center: outputs, inputs, per-app volume, and card profiles for Hyprland.

Talks to PipeWire through `pactl` (pipewire-pulse), so it needs no extra
Python bindings. Updates live via `pactl subscribe`.

  Output   pick the default speaker/headphones (playing apps follow), volume, mute, port
  Input    pick the default mic, volume, mute, port, live level meter
  Apps     per-app volume/mute and which device each app plays to or records from
  Devices  sound-card profiles (HDMI vs analog, Bluetooth headset vs high quality)
"""

import array
import json
import os
import subprocess
import sys
import threading
import time

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, Gio, GLib, Gtk, Pango  # noqa: E402

APP_ID = "dev.eftear.hyprland.SoundCenter"
METER_NAME = "Sound Center meter"
MAX_VOLUME = 150

PAGES = (
    ("output", "Output", "󰓃"),
    ("input", "Input", "󰍬"),
    ("apps", "Apps", "󰀻"),
    ("devices", "Devices", "󰓂"),
)

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
window, #root { background: @bg; color: @text; }
headerbar { min-height: 58px; padding: 6px 12px; color: @text; background: @panel; border: 0; border-bottom: 1px solid @border; box-shadow: none; }
headerbar .title { color: @text; font-size: 17px; font-weight: 800; }
headerbar .subtitle { color: @muted; font-size: 11px; }

#sidebar { min-width: 190px; padding: 18px 12px; background: @panel; border-right: 1px solid @border; }
.sidebar-title { margin: 2px 10px 12px; color: @muted; font-size: 10px; font-weight: 800; }
button.nav { min-height: 40px; margin: 2px 0; padding: 0 11px; color: @muted; background: transparent; border: 0; border-radius: 9px; box-shadow: none; }
button.nav:hover { color: @text; background: @hover; }
button.nav.active { color: @cyan; background: alpha(@cyan, .11); }
.nav-icon { min-width: 24px; color: @violet; font-size: 15px; }
button.nav.active .nav-icon { color: @cyan; }
.nav-name { font-size: 12px; font-weight: 700; }
.nav-badge { color: @muted; font-size: 10px; }

.page-header { min-height: 70px; padding: 0 22px; border-bottom: 1px solid @border; }
levelbar, levelbar trough { min-height: 10px; padding: 0; }
levelbar block { min-height: 10px; min-width: 1px; }
.section-title { color: @text; font-size: 15px; font-weight: 800; }
.section-copy { margin-top: 3px; color: @muted; font-size: 10px; }
.group-title { margin: 14px 2px 2px; color: @muted; font-size: 10px; font-weight: 800; }

.card { padding: 14px 16px; background: @card; border: 1px solid @border; border-radius: 12px; }
.card.default { border-color: alpha(@cyan, .70); background: #10202e; }
.card-icon { min-width: 40px; min-height: 40px; color: @violet; font-size: 20px; background: alpha(@violet, .10); border-radius: 10px; }
.card.default .card-icon { color: @cyan; background: alpha(@cyan, .12); }
.card-title { color: @text; font-size: 12px; font-weight: 800; }
.card-meta { margin-top: 2px; color: @muted; font-size: 9px; }
.pill { padding: 2px 8px; border-radius: 9px; font-size: 9px; font-weight: 800; color: @green; background: alpha(@green, .12); }
.pill.rec { color: @red; background: alpha(@red, .12); }
.pct { min-width: 48px; color: @text; font-size: 11px; font-weight: 800; }
.hint { color: @muted; font-size: 10px; }
.empty { margin: 40px; color: @muted; font-size: 11px; }

scale trough { min-height: 6px; background: #1d2740; border-radius: 4px; }
scale highlight { background: @cyan; border-radius: 4px; }
scale.muted highlight { background: #4b5878; }
scale.over highlight { background: @amber; }
scale slider { min-width: 16px; min-height: 16px; background: @text; border-radius: 9px; border: 0; box-shadow: none; }
scale marks, scale mark { color: @muted; }

levelbar trough { min-height: 8px; background: #1d2740; border-radius: 4px; border: 0; }
levelbar block.filled { background: @green; border-radius: 4px; }
levelbar block.high { background: @amber; }
levelbar block.full { background: @red; }
levelbar block.empty { background: transparent; }

button.icon, button.action {
  min-height: 32px; min-width: 32px; padding: 0 10px; color: @muted;
  background: @panel2; border: 1px solid @border; border-radius: 9px; box-shadow: none; font-size: 13px;
}
button.action { font-size: 10px; font-weight: 800; color: @text; }
button.icon:hover, button.action:hover { color: @text; background: @hover; border-color: alpha(@cyan, .45); }
button.icon.muted { color: @red; border-color: alpha(@red, .55); background: alpha(@red, .08); }
button.action.primary { color: #061014; background: @cyan; border-color: @cyan; }
combobox button, combobox box { min-height: 30px; color: @text; background: #151d30; border: 1px solid @border; border-radius: 9px; box-shadow: none; font-size: 10px; }
#statusbar { min-height: 32px; padding: 0 18px; color: @muted; background: @panel; border-top: 1px solid @border; font-size: 9px; }
scrollbar slider { min-width: 6px; min-height: 32px; background: #34415d; border-radius: 9px; }
scrollbar trough { background: transparent; }
"""


# --------------------------------------------------------------------------- #
# pactl helpers
# --------------------------------------------------------------------------- #


def pactl(*args, timeout=5):
    try:
        result = subprocess.run(["pactl", *args], capture_output=True, text=True, timeout=timeout,
                                env=dict(os.environ, LC_ALL="C"))
    except (OSError, subprocess.SubprocessError) as error:
        raise RuntimeError(f"pactl failed: {error}") from error
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout).strip() or "pactl failed")
    return result.stdout


def pactl_async(*args):
    """Fire-and-forget for slider drags; results arrive through `pactl subscribe`."""
    try:
        subprocess.Popen(["pactl", *args], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        pass


def pactl_json(*args):
    try:
        return json.loads(pactl("-f", "json", *args) or "[]")
    except (RuntimeError, ValueError):
        return []


def volume_percent(obj):
    values = []
    for channel in (obj.get("volume") or {}).values():
        try:
            values.append(int(str(channel.get("value_percent", "0")).rstrip("%")))
        except ValueError:
            pass
    return round(sum(values) / len(values)) if values else 0


def read_state():
    sinks = pactl_json("list", "sinks")
    sources = [s for s in pactl_json("list", "sources")
               if s.get("properties", {}).get("device.class") != "monitor" and not s.get("name", "").endswith(".monitor")]
    sink_inputs = pactl_json("list", "sink-inputs")
    source_outputs = [o for o in pactl_json("list", "source-outputs")
                      if o.get("properties", {}).get("application.name") != METER_NAME
                      and o.get("properties", {}).get("media.name") != METER_NAME]
    cards = pactl_json("list", "cards")
    try:
        default_sink = pactl("get-default-sink").strip()
        default_source = pactl("get-default-source").strip()
    except RuntimeError:
        default_sink = default_source = ""
    return {
        "sinks": sinks, "sources": sources, "sink_inputs": sink_inputs,
        "source_outputs": source_outputs, "cards": cards,
        "default_sink": default_sink, "default_source": default_source,
    }


def device_icon(obj, is_input):
    props = obj.get("properties", {})
    form = (props.get("device.form_factor") or "").lower()
    bus = (props.get("device.bus") or "").lower()
    port = (obj.get("active_port") or "").lower()
    if bus == "bluetooth":
        return "󰋋" if not is_input else "󰋎"
    if "headphone" in port or form in ("headphone", "headset"):
        return "󰋋"
    if "hdmi" in port or "hdmi" in obj.get("name", ""):
        return "󰡁"
    if bus == "usb":
        return "󰍮" if is_input else "󰓃"
    return "󰍬" if is_input else "󰓃"


def app_name(stream):
    props = stream.get("properties", {})
    return (props.get("application.name") or props.get("application.process.binary")
            or props.get("node.name") or "Unknown app")


def app_icon_widget(stream, size=32):
    props = stream.get("properties", {})
    theme = Gtk.IconTheme.get_default()
    candidates = [props.get("application.icon_name"), props.get("application.id"),
                  props.get("application.process.binary"), (props.get("application.name") or "").lower()]
    for name in candidates:
        if name and theme.has_icon(name):
            image = Gtk.Image.new_from_icon_name(name, Gtk.IconSize.DND)
            image.set_pixel_size(size)
            return image
    binary = props.get("application.process.binary")
    if binary:
        try:
            info = Gio.DesktopAppInfo.new(f"{binary}.desktop")
        except TypeError:  # PyGObject raises instead of returning None
            info = None
        if info and info.get_icon():
            image = Gtk.Image.new_from_gicon(info.get_icon(), Gtk.IconSize.DND)
            image.set_pixel_size(size)
            return image
    return None


# --------------------------------------------------------------------------- #
# widgets
# --------------------------------------------------------------------------- #


def label(text, css="", xalign=0.0, ellipsize=True):
    widget = Gtk.Label(label=text)
    widget.set_xalign(xalign)
    if ellipsize:
        widget.set_ellipsize(Pango.EllipsizeMode.END)
    for name in css.split():
        widget.get_style_context().add_class(name)
    return widget


def clear(container):
    for child in container.get_children():
        container.remove(child)


class VolumeRow(Gtk.Box):
    """Mute button + slider (0-150%) + percentage, wired to a pactl target."""

    def __init__(self, kind, ident, volume, muted, on_change=None):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        self.kind, self.ident, self.on_change = kind, ident, on_change
        self.last_user_change = 0.0
        self.mute_button = Gtk.Button()
        self.mute_button.get_style_context().add_class("icon")
        self.mute_button.connect("clicked", self.toggle_mute)
        self.pack_start(self.mute_button, False, False, 0)

        self.scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, MAX_VOLUME, 1)
        self.scale.set_draw_value(False)
        self.scale.set_hexpand(True)
        self.scale.add_mark(100, Gtk.PositionType.BOTTOM, None)
        self.handler = self.scale.connect("value-changed", self.changed)
        self.pack_start(self.scale, True, True, 0)
        self.pct = label("", "pct", xalign=1.0, ellipsize=False)
        self.pack_start(self.pct, False, False, 0)
        self.update(volume, muted, force=True)

    def update(self, volume, muted, force=False):
        self.muted = muted
        is_input = self.kind in ("source", "source-output")
        self.mute_button.set_label(("󰍭" if is_input else "󰖁") if muted else ("󰍬" if is_input else "󰕾"))
        self.mute_button.set_tooltip_text("Unmute" if muted else "Mute")
        ctx = self.mute_button.get_style_context()
        (ctx.add_class if muted else ctx.remove_class)("muted")
        sctx = self.scale.get_style_context()
        (sctx.add_class if muted else sctx.remove_class)("muted")
        # don't fight the user while they are dragging
        if force or time.monotonic() - self.last_user_change > 0.8:
            self.scale.handler_block(self.handler)
            self.scale.set_value(volume)
            self.scale.handler_unblock(self.handler)
            self.show_pct(volume)

    def show_pct(self, volume):
        self.pct.set_text(f"{int(volume)}%")
        sctx = self.scale.get_style_context()
        (sctx.add_class if volume > 100 else sctx.remove_class)("over")

    def changed(self, scale):
        value = int(scale.get_value())
        self.last_user_change = time.monotonic()
        self.show_pct(value)
        pactl_async(f"set-{self.kind}-volume", str(self.ident), f"{value}%")
        if self.muted and value > 0:
            pactl_async(f"set-{self.kind}-mute", str(self.ident), "0")

    def toggle_mute(self, *_args):
        pactl_async(f"set-{self.kind}-mute", str(self.ident), "toggle")


# --------------------------------------------------------------------------- #
# application
# --------------------------------------------------------------------------- #


class SoundCenter(Gtk.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE)
        self.window = None
        self.page = "output"
        self.state = None
        self.signatures = {}
        self.rows = {}
        self.nav_buttons, self.nav_badges = {}, {}
        self.refresh_pending = False
        self.subscriber = None
        self.meter_proc = None
        self.meter_source = None
        self.meter_level = 0.0

    def do_startup(self):
        Gtk.Application.do_startup(self)
        provider = Gtk.CssProvider()
        provider.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), provider,
                                                 Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

    def do_command_line(self, command_line):
        for arg in command_line.get_arguments()[1:]:
            if arg.lstrip("-") in dict((p[0], p) for p in PAGES):
                self.page = arg.lstrip("-")
        self.activate()
        if self.window:
            self.show_page(self.page)
        return 0

    def do_activate(self):
        if self.window:
            self.window.present()
            return
        self.build_window()
        self.window.show_all()
        self.show_page(self.page)
        self.refresh()
        self.start_subscriber()
        GLib.timeout_add(50, self.tick_meter)

    # ---- window ----------------------------------------------------------- #

    def build_window(self):
        self.window = Gtk.ApplicationWindow(application=self)
        self.window.set_title("Sound Center")
        self.window.set_default_size(980, 680)
        self.window.set_size_request(820, 520)
        self.window.connect("key-press-event", self.on_key)
        self.window.connect("destroy", self.on_destroy)

        header = Gtk.HeaderBar()
        header.set_show_close_button(True)
        header.props.title = "SOUND CENTER"
        header.props.subtitle = "Reading audio devices…"
        self.header = header
        mixer = Gtk.Button(label="󰒓  Advanced")
        mixer.get_style_context().add_class("action")
        mixer.set_tooltip_text("Open pavucontrol")
        mixer.connect("clicked", lambda *_: self.spawn(["pavucontrol"]))
        header.pack_end(mixer)
        self.window.set_titlebar(header)

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        root.set_name("root")
        body = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        root.pack_start(body, True, True, 0)

        sidebar = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        sidebar.set_name("sidebar")
        sidebar.pack_start(label("AUDIO", "sidebar-title"), False, False, 0)
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
            self.nav_buttons[key], self.nav_badges[key] = button, badge
        body.pack_start(sidebar, False, False, 0)

        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self.stack.set_transition_duration(120)
        self.boxes = {}
        copies = {
            "output": ("Output", "Click a device to make it the default. Playing apps move with it."),
            "input": ("Input", "Pick the microphone Meet and other apps use. Speak to see the level."),
            "apps": ("Apps", "Volume and device per application"),
            "devices": ("Devices", "Sound-card profiles: HDMI vs analog, Bluetooth headset vs high quality"),
        }
        for key, (title, copy) in copies.items():
            page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            header_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            header_box.get_style_context().add_class("page-header")
            header_box.set_valign(Gtk.Align.START)
            inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            inner.set_valign(Gtk.Align.CENTER)
            inner.pack_start(label(title, "section-title"), False, False, 0)
            inner.pack_start(label(copy, "section-copy"), False, False, 0)
            header_box.pack_start(inner, True, True, 0)
            page.pack_start(header_box, False, False, 0)
            content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
            content.set_valign(Gtk.Align.START)
            content.set_margin_start(22)
            content.set_margin_end(22)
            content.set_margin_top(16)
            content.set_margin_bottom(18)
            scroller = Gtk.ScrolledWindow()
            scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
            scroller.add(content)
            page.pack_start(scroller, True, True, 0)
            self.stack.add_named(page, key)
            self.boxes[key] = content
        body.pack_start(self.stack, True, True, 0)

        status = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        status.set_name("statusbar")
        self.status_label = label("Ready")
        status.pack_start(self.status_label, True, True, 0)
        status.pack_end(label("Ctrl+1-4 pages  •  M mute output  •  Ctrl+M mute mic  •  Esc close", xalign=1.0), False, False, 0)
        root.pack_start(status, False, False, 0)
        self.window.add(root)

    def show_page(self, key):
        self.page = key
        self.stack.set_visible_child_name(key)
        for name, button in self.nav_buttons.items():
            ctx = button.get_style_context()
            (ctx.add_class if name == key else ctx.remove_class)("active")
        self.update_meter()

    def status(self, text, color=None):
        if color:
            self.status_label.set_markup(f"<span foreground='{color}'><b>{GLib.markup_escape_text(text)}</b></span>")
        else:
            self.status_label.set_text(text)

    def spawn(self, argv):
        try:
            subprocess.Popen(argv, start_new_session=True)
        except OSError as error:
            self.status(f"Could not start {argv[0]}: {error}", "#ff6b81")

    def on_key(self, _widget, event):
        ctrl = bool(event.state & Gdk.ModifierType.CONTROL_MASK)
        if event.keyval == Gdk.KEY_Escape:
            self.window.close()
            return True
        if ctrl and Gdk.KEY_1 <= event.keyval <= Gdk.KEY_4:
            self.show_page(PAGES[event.keyval - Gdk.KEY_1][0])
            return True
        if event.keyval in (Gdk.KEY_m, Gdk.KEY_M) and self.state:
            if ctrl:
                pactl_async("set-source-mute", "@DEFAULT_SOURCE@", "toggle")
            else:
                pactl_async("set-sink-mute", "@DEFAULT_SINK@", "toggle")
            return True
        return False

    def on_destroy(self, *_args):
        self.stop_meter()
        if self.subscriber:
            self.subscriber.terminate()
        self.window = None

    # ---- live updates ----------------------------------------------------- #

    def start_subscriber(self):
        try:
            self.subscriber = subprocess.Popen(["pactl", "subscribe"], stdout=subprocess.PIPE,
                                               stderr=subprocess.DEVNULL, text=True)
        except OSError:
            GLib.timeout_add_seconds(2, lambda: (self.refresh(), True)[1])
            return

        def reader():
            for line in self.subscriber.stdout:
                if "client" in line and "sink-input" not in line and "source-output" not in line:
                    continue
                GLib.idle_add(self.schedule_refresh)

        threading.Thread(target=reader, daemon=True).start()

    def schedule_refresh(self):
        if not self.refresh_pending:
            self.refresh_pending = True
            GLib.timeout_add(120, self.refresh)
        return False

    def refresh(self):
        self.refresh_pending = False

        def work():
            state = read_state()
            GLib.idle_add(self.apply_state, state)

        threading.Thread(target=work, daemon=True).start()
        return False

    def apply_state(self, state):
        if not self.window:
            return False
        self.state = state
        default_sink = next((s for s in state["sinks"] if s["name"] == state["default_sink"]), None)
        default_source = next((s for s in state["sources"] if s["name"] == state["default_source"]), None)
        bits = []
        if default_sink:
            bits.append(f"󰓃 {default_sink['description']} {'muted' if default_sink['mute'] else str(volume_percent(default_sink)) + '%'}")
        if default_source:
            bits.append(f"󰍬 {default_source['description']}{' (muted)' if default_source['mute'] else ''}")
        self.header.props.subtitle = "   •   ".join(bits) or "No audio devices"
        self.nav_badges["output"].set_text(str(len(state["sinks"])))
        self.nav_badges["input"].set_text(str(len(state["sources"])))
        streams = len(state["sink_inputs"]) + len(state["source_outputs"])
        self.nav_badges["apps"].set_text(str(streams) if streams else "")
        self.nav_badges["devices"].set_text(str(len(state["cards"])))
        self.render_devices_page("output", state["sinks"], state["default_sink"], "sink")
        self.render_devices_page("input", state["sources"], state["default_source"], "source")
        self.render_apps()
        self.render_cards()
        self.update_meter()
        return False

    def structure_changed(self, key, signature):
        if self.signatures.get(key) == signature:
            return False
        self.signatures[key] = signature
        return True

    # ---- output / input pages --------------------------------------------- #

    def render_devices_page(self, page, devices, default_name, kind):
        signature = tuple((d["index"], d["name"], d["name"] == default_name, d.get("active_port"),
                           tuple(p["name"] + p.get("availability", "") for p in d.get("ports", [])))
                          for d in devices)
        box = self.boxes[page]
        if self.structure_changed(page, signature):
            clear(box)
            if not devices:
                box.pack_start(label("No devices found", "empty", xalign=0.5), False, False, 0)
            for device in sorted(devices, key=lambda d: d["name"] != default_name):
                box.pack_start(self.device_card(device, device["name"] == default_name, kind), False, False, 0)
            if kind == "source":
                box.pack_start(self.meter_card(), False, False, 0)
            box.show_all()
        else:
            for device in devices:
                row = self.rows.get((kind, device["index"]))
                if row:
                    row.update(volume_percent(device), device["mute"])

    def device_card(self, device, is_default, kind):
        card = Gtk.EventBox()
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        ctx = box.get_style_context()
        ctx.add_class("card")
        if is_default:
            ctx.add_class("default")
        card.add(box)

        top = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        icon = label(device_icon(device, kind == "source"), "card-icon", xalign=0.5, ellipsize=False)
        top.pack_start(icon, False, False, 0)
        names = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        names.set_valign(Gtk.Align.CENTER)
        names.pack_start(label(device["description"], "card-title"), False, False, 0)
        port = next((p for p in device.get("ports", []) if p["name"] == device.get("active_port")), None)
        meta = [port["description"] if port else "", device.get("state", "").lower()]
        names.pack_start(label("  •  ".join(m for m in meta if m), "card-meta"), False, False, 0)
        top.pack_start(names, True, True, 0)
        if is_default:
            pill = label("DEFAULT", "pill", ellipsize=False)
            pill.set_valign(Gtk.Align.CENTER)
            top.pack_end(pill, False, False, 0)
        else:
            use = Gtk.Button(label="Use this")
            for name in ("action", "primary"):
                use.get_style_context().add_class(name)
            use.set_valign(Gtk.Align.CENTER)
            use.connect("clicked", lambda *_: self.set_default(kind, device))
            top.pack_end(use, False, False, 0)

        ports = [p for p in device.get("ports", [])]
        if len(ports) > 1:
            combo = Gtk.ComboBoxText()
            for p in ports:
                suffix = "  (unplugged)" if p.get("availability") == "not available" else ""
                combo.append(p["name"], p["description"] + suffix)
            combo.set_active_id(device.get("active_port"))
            combo.set_valign(Gtk.Align.CENTER)
            combo.set_tooltip_text("Connector / jack")
            combo.connect("changed", lambda c: c.get_active_id() and c.get_active_id() != device.get("active_port")
                          and self.set_port(kind, device, c.get_active_id()))
            top.pack_end(combo, False, False, 0)
        box.pack_start(top, False, False, 0)

        row = VolumeRow(kind, device["index"], volume_percent(device), device["mute"])
        self.rows[(kind, device["index"])] = row
        box.pack_start(row, False, False, 0)

        card.connect("button-press-event", lambda _w, e: (e.button == 1 and not is_default
                                                          and e.type == Gdk.EventType.BUTTON_PRESS
                                                          and self.set_default(kind, device), False)[1])
        return card

    def set_default(self, kind, device):
        name = device["name"]

        def work():
            pactl(f"set-default-{kind}", name)
            streams = self.state["sink_inputs"] if kind == "sink" else self.state["source_outputs"]
            for stream in streams:
                try:
                    pactl("move-sink-input" if kind == "sink" else "move-source-output", str(stream["index"]), name)
                except RuntimeError:
                    pass

        def done(error):
            if error:
                self.status(str(error), "#ff6b81")
            else:
                self.status(f"{'Output' if kind == 'sink' else 'Microphone'}: {device['description']}", "#78f0c2")
            return False

        self.run_task(work, done)

    def set_port(self, kind, device, port):
        self.run_task(lambda: pactl(f"set-{kind}-port", device["name"], port),
                 lambda error: self.status(str(error) if error else f"Switched to {port}",
                                           "#ff6b81" if error else "#78f0c2"))

    def run_task(self, work, done):
        def thread():
            try:
                work()
                error = None
            except RuntimeError as exc:
                error = exc
            GLib.idle_add(done, error)

        threading.Thread(target=thread, daemon=True).start()

    # ---- mic level meter -------------------------------------------------- #

    def meter_card(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.get_style_context().add_class("card")
        head = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        head.pack_start(label("MICROPHONE TEST", "group-title"), False, False, 0)
        self.meter_hint = label("Speak — the bar should move", "hint", xalign=1.0)
        head.pack_end(self.meter_hint, False, False, 0)
        box.pack_start(head, False, False, 0)
        self.meter = Gtk.LevelBar()
        self.meter.set_min_value(0)
        self.meter.set_max_value(1)
        self.meter.add_offset_value("high", 0.75)
        self.meter.add_offset_value("full", 0.95)
        self.meter.set_size_request(-1, 10)
        self.meter.set_valign(Gtk.Align.CENTER)
        box.pack_start(self.meter, False, False, 0)
        return box

    def update_meter(self):
        wanted = self.state["default_source"] if self.state and self.page == "input" else None
        if wanted == self.meter_source and (wanted is None or self.meter_proc):
            return
        self.stop_meter()
        if not wanted:
            return
        try:
            self.meter_proc = subprocess.Popen(
                ["parec", "-d", wanted, "--format=s16le", "--rate=16000", "--channels=1",
                 "--latency-msec=30", "--raw", f"--client-name={METER_NAME}",
                 f"--stream-name={METER_NAME}", "--property=application.name=" + METER_NAME],
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        except OSError:
            self.meter_proc = None
            return
        self.meter_source = wanted
        proc = self.meter_proc

        def reader():
            while proc.poll() is None:
                data = proc.stdout.read(640)
                if not data:
                    break
                samples = array.array("h", data[: len(data) // 2 * 2])
                peak = max((abs(s) for s in samples), default=0) / 32768
                self.meter_level = max(peak, self.meter_level * 0.85)

        threading.Thread(target=reader, daemon=True).start()

    def stop_meter(self):
        if self.meter_proc:
            self.meter_proc.terminate()
        self.meter_proc, self.meter_source, self.meter_level = None, None, 0.0

    def tick_meter(self):
        if not self.window:
            return False
        meter = getattr(self, "meter", None)
        if meter and meter.get_mapped():
            level = min(1.0, self.meter_level ** 0.5)  # perceptual-ish curve
            meter.set_value(level)
            self.meter_level *= 0.9
            source = next((s for s in (self.state or {}).get("sources", []) if s["name"] == self.meter_source), None)
            if source and source["mute"]:
                self.meter_hint.set_text("Microphone is muted")
            elif level > 0.08:
                self.meter_hint.set_text("Hearing you ✓")
            else:
                self.meter_hint.set_text("Speak — the bar should move")
        return True

    # ---- apps page -------------------------------------------------------- #

    def render_apps(self):
        state = self.state
        signature = (
            tuple((s["index"], s.get("sink"), app_name(s)) for s in state["sink_inputs"]),
            tuple((o["index"], o.get("source"), app_name(o)) for o in state["source_outputs"]),
            tuple((d["index"], d["description"]) for d in state["sinks"] + state["sources"]),
        )
        box = self.boxes["apps"]
        if not self.structure_changed("apps", signature):
            for stream in state["sink_inputs"]:
                row = self.rows.get(("sink-input", stream["index"]))
                if row:
                    row.update(volume_percent(stream), stream["mute"])
            for stream in state["source_outputs"]:
                row = self.rows.get(("source-output", stream["index"]))
                if row:
                    row.update(volume_percent(stream), stream["mute"])
            return
        clear(box)
        box.pack_start(label("PLAYING", "group-title"), False, False, 0)
        if not state["sink_inputs"]:
            box.pack_start(label("Nothing is playing sound right now", "hint"), False, False, 4)
        for stream in state["sink_inputs"]:
            box.pack_start(self.stream_card(stream, "sink-input", state["sinks"], stream.get("sink")), False, False, 0)
        box.pack_start(label("USING THE MICROPHONE", "group-title"), False, False, 0)
        if not state["source_outputs"]:
            box.pack_start(label("No app is recording", "hint"), False, False, 4)
        for stream in state["source_outputs"]:
            box.pack_start(self.stream_card(stream, "source-output", state["sources"], stream.get("source")), False, False, 0)
        box.show_all()

    def stream_card(self, stream, kind, devices, current_index):
        props = stream.get("properties", {})
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        box.get_style_context().add_class("card")
        top = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        icon = app_icon_widget(stream) or label("󰝚" if kind == "sink-input" else "󰍬", "card-icon", xalign=0.5, ellipsize=False)
        icon.set_valign(Gtk.Align.CENTER)
        top.pack_start(icon, False, False, 0)
        names = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        names.set_valign(Gtk.Align.CENTER)
        names.pack_start(label(app_name(stream), "card-title"), False, False, 0)
        media = props.get("media.name") or ""
        if media and media != app_name(stream):
            names.pack_start(label(media, "card-meta"), False, False, 0)
        top.pack_start(names, True, True, 0)
        if kind == "source-output":
            pill = label("● REC", "pill rec", ellipsize=False)
            pill.set_valign(Gtk.Align.CENTER)
            top.pack_end(pill, False, False, 0)
        if len(devices) > 1:
            combo = Gtk.ComboBoxText()
            for device in devices:
                combo.append(str(device["index"]), device["description"])
            combo.set_active_id(str(current_index))
            combo.set_valign(Gtk.Align.CENTER)
            combo.set_tooltip_text("Play on" if kind == "sink-input" else "Record from")
            verb = "move-sink-input" if kind == "sink-input" else "move-source-output"
            combo.connect("changed", lambda c: c.get_active_id() and c.get_active_id() != str(current_index)
                          and self.run_task(lambda: pactl(verb, str(stream["index"]), c.get_active_id()),
                                       lambda e: self.status(str(e) if e else f"Moved {app_name(stream)}",
                                                             "#ff6b81" if e else "#78f0c2")))
            top.pack_end(combo, False, False, 0)
        box.pack_start(top, False, False, 0)
        row = VolumeRow(kind, stream["index"], volume_percent(stream), stream.get("mute", False))
        self.rows[(kind, stream["index"])] = row
        box.pack_start(row, False, False, 0)
        return box

    # ---- devices page ----------------------------------------------------- #

    def render_cards(self):
        cards = self.state["cards"]
        signature = tuple((c["index"], c.get("active_profile"),
                           tuple((k, v.get("available")) for k, v in c.get("profiles", {}).items())) for c in cards)
        if not self.structure_changed("devices", signature):
            return
        box = self.boxes["devices"]
        clear(box)
        if not cards:
            box.pack_start(label("No sound cards found", "empty", xalign=0.5), False, False, 0)
        for card in cards:
            props = card.get("properties", {})
            item = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
            item.get_style_context().add_class("card")
            top = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
            bus = (props.get("device.bus") or "").lower()
            top.pack_start(label("󰂯" if bus == "bluetooth" else ("󰗾" if bus == "usb" else "󰓂"),
                                 "card-icon", xalign=0.5, ellipsize=False), False, False, 0)
            names = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            names.set_valign(Gtk.Align.CENTER)
            names.pack_start(label(props.get("device.description") or card["name"], "card-title"), False, False, 0)
            names.pack_start(label(props.get("device.product.name") or card["name"], "card-meta"), False, False, 0)
            top.pack_start(names, True, True, 0)
            item.pack_start(top, False, False, 0)

            combo = Gtk.ComboBoxText()
            active = card.get("active_profile")
            for key, profile in card.get("profiles", {}).items():
                if profile.get("available") or key == active:
                    combo.append(key, profile.get("description") or key)
            combo.set_active_id(active)
            combo.connect("changed", lambda c, name=card["name"], cur=active:
                          c.get_active_id() and c.get_active_id() != cur
                          and self.run_task(lambda: pactl("set-card-profile", name, c.get_active_id()),
                                       lambda e: self.status(str(e) if e else "Profile changed",
                                                             "#ff6b81" if e else "#78f0c2")))
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
            row.pack_start(label("Profile", "hint", ellipsize=False), False, False, 0)
            row.pack_start(combo, True, True, 0)
            item.pack_start(row, False, False, 0)
            if bus == "bluetooth":
                item.pack_start(label("Tip: a headset profile (HFP/HSP) is needed for the mic in calls; "
                                      "A2DP gives better music quality but no mic.", "hint"), False, False, 0)
            box.pack_start(item, False, False, 0)
        hidden = sum(1 for c in cards for p in c.get("profiles", {}).values() if not p.get("available"))
        if hidden:
            box.pack_start(label(f"{hidden} profiles hidden because their connector is unplugged (e.g. HDMI without a monitor speaker).",
                                 "hint"), False, False, 4)
        box.show_all()


if __name__ == "__main__":
    sys.exit(SoundCenter().run(sys.argv))
