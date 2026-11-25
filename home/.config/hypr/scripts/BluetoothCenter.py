#!/usr/bin/env python3
"""Bluetooth Center: scan, pair, connect, and manage Bluetooth devices on Hyprland.

Talks to BlueZ over D-Bus (no extra packages) and registers its own pairing
agent, so PIN / passkey prompts appear as dialogs while the window is open.

  My devices   paired devices: connect/disconnect, battery level, trust, forget
  Nearby       devices found while scanning: pair & connect in one click

Machines without a Bluetooth adapter get a clear empty state.
Set BLUETOOTH_CENTER_BUS=session to run against a mock BlueZ for testing.
"""

import os
import subprocess
import sys

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, Gio, GLib, Gtk, Pango  # noqa: E402

APP_ID = "dev.eftear.hyprland.BluetoothCenter"
BLUEZ = "org.bluez"
ADAPTER = "org.bluez.Adapter1"
DEVICE = "org.bluez.Device1"
BATTERY = "org.bluez.Battery1"
PROPS = "org.freedesktop.DBus.Properties"
AGENT_PATH = "/dev/eftear/BluetoothCenter/agent"
SCAN_SECONDS = 30

DEVICE_ICONS = {
    "audio-headset": "󰋎", "audio-headphones": "󰋋", "audio-card": "󰓃", "audio-speakers": "󰓃",
    "input-mouse": "󰍽", "input-keyboard": "󰌌", "input-gaming": "󰊴", "input-tablet": "󰓶",
    "phone": "󰏲", "computer": "󰌢", "video-display": "󰍹", "camera-photo": "󰄀",
    "camera-video": "󰕧", "printer": "󰐪", "network-wireless": "󰖩",
}

AGENT_XML = """
<node>
  <interface name="org.bluez.Agent1">
    <method name="Release"/>
    <method name="RequestPinCode"><arg type="o" direction="in"/><arg type="s" direction="out"/></method>
    <method name="DisplayPinCode"><arg type="o" direction="in"/><arg type="s" direction="in"/></method>
    <method name="RequestPasskey"><arg type="o" direction="in"/><arg type="u" direction="out"/></method>
    <method name="DisplayPasskey"><arg type="o" direction="in"/><arg type="u" direction="in"/><arg type="q" direction="in"/></method>
    <method name="RequestConfirmation"><arg type="o" direction="in"/><arg type="u" direction="in"/></method>
    <method name="RequestAuthorization"><arg type="o" direction="in"/></method>
    <method name="AuthorizeService"><arg type="o" direction="in"/><arg type="s" direction="in"/></method>
    <method name="Cancel"/>
  </interface>
</node>
"""

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
headerbar { min-height: 58px; padding: 6px 12px; color: @text; background: @panel; border: 0; border-bottom: 1px solid @border; box-shadow: none; }
headerbar .title { color: @text; font-size: 17px; font-weight: 800; }
headerbar .subtitle { color: @muted; font-size: 11px; }

#controls { min-height: 64px; padding: 0 22px; background: @panel; border-bottom: 1px solid @border; }
.ctl-label { color: @text; font-size: 12px; font-weight: 800; }
.ctl-copy { color: @muted; font-size: 9px; }
switch { background: @panel2; border: 1px solid @border; border-radius: 14px; }
switch:checked { background: alpha(@cyan, .55); }
switch slider { background: @text; border-radius: 12px; min-width: 22px; min-height: 22px; }

.group-title { margin: 16px 2px 4px; color: @muted; font-size: 10px; font-weight: 800; }
list { background: transparent; }
row.dev { margin: 3px 0; padding: 0; background: @card; border: 1px solid @border; border-radius: 11px; }
row.dev:hover { background: @hover; border-color: alpha(@cyan, .35); }
row.dev.connected { border-color: alpha(@green, .65); }
.row-inner { min-height: 56px; padding: 6px 12px; }
.dev-icon { min-width: 38px; min-height: 38px; color: @violet; font-size: 18px; background: alpha(@violet, .10); border: 1px solid alpha(@violet, .24); border-radius: 10px; }
row.dev.connected .dev-icon { color: @green; background: alpha(@green, .10); border-color: alpha(@green, .30); }
.dev-name { color: @text; font-size: 12px; font-weight: 800; }
.dev-meta { margin-top: 2px; color: @muted; font-size: 9px; }
.pill { padding: 2px 8px; border-radius: 9px; font-size: 9px; font-weight: 800; }
.pill.on { color: @green; background: alpha(@green, .12); }
.pill.batt { color: @cyan; background: alpha(@cyan, .10); }
.pill.low { color: @red; background: alpha(@red, .12); }

button.action, button.icon {
  min-height: 32px; padding: 0 12px; color: @text; background: @panel2;
  border: 1px solid @border; border-radius: 9px; box-shadow: none; font-size: 10px; font-weight: 800;
}
button.icon { min-width: 32px; padding: 0; font-size: 13px; color: @muted; }
button.action:hover, button.icon:hover { background: @hover; border-color: alpha(@cyan, .45); color: @text; }
button.action.primary { color: #061014; background: @cyan; border-color: @cyan; }
button.action.primary:hover { background: #93f2fb; }
button.action.danger { color: @red; }
button.action.scanning { color: @cyan; border-color: @cyan; background: alpha(@cyan, .10); }
button:disabled { opacity: .38; }
spinner { color: @cyan; }

#empty { margin: 60px 28px; }
.empty-icon { color: @violet; font-size: 46px; }
.empty-title { margin-top: 12px; color: @text; font-size: 15px; font-weight: 800; }
.empty-copy { margin-top: 6px; color: @muted; font-size: 10px; }
.hint { color: @muted; font-size: 10px; }
.passkey { color: @cyan; font-size: 30px; font-weight: 800; letter-spacing: 4px; }
entry { min-height: 36px; padding: 0 12px; color: @text; background: #151d30; border: 1px solid @border; border-radius: 10px; }
entry:focus { border-color: @cyan; }
#statusbar { min-height: 32px; padding: 0 18px; color: @muted; background: @panel; border-top: 1px solid @border; font-size: 9px; }
menu, menuitem { background: @panel; color: @text; }
scrollbar slider { min-width: 6px; min-height: 32px; background: #34415d; border-radius: 9px; }
scrollbar trough { background: transparent; }
"""


def label(text, css="", xalign=0.0, ellipsize=True, wrap=False):
    widget = Gtk.Label(label=text)
    widget.set_xalign(xalign)
    if wrap:
        widget.set_line_wrap(True)
        widget.set_max_width_chars(70)
    elif ellipsize:
        widget.set_ellipsize(Pango.EllipsizeMode.END)
    for name in css.split():
        widget.get_style_context().add_class(name)
    return widget


def clear(container):
    for child in container.get_children():
        container.remove(child)


def dbus_error_text(error):
    message = getattr(error, "message", str(error))
    if "GDBus.Error:" in message:
        message = message.split(":", 2)[-1].strip()
    friendly = {
        "Page Timeout": "Device did not answer — is it in pairing mode and close by?",
        "Authentication Failed": "Pairing was rejected or the code did not match",
        "Authentication Canceled": "Pairing was cancelled",
        "Authentication Rejected": "Pairing was rejected",
        "Connection refused": "Device refused the connection",
        "br-connection-profile-unavailable": "No usable profile — for headphones check the audio service is running",
        "Blocked through rfkill": "Bluetooth is blocked (airplane mode / rfkill)",
        "In Progress": "Already in progress…",
    }
    for key, text in friendly.items():
        if key.lower() in message.lower():
            return text
    return message


class BluetoothCenter(Gtk.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.FLAGS_NONE)
        self.window = None
        self.bus = None
        self.objects = {}
        self.adapter_path = None
        self.busy = set()
        self.refresh_pending = False
        self.scan_timer = None
        self.agent_id = None
        self.service_up = False

    # ---- lifecycle -------------------------------------------------------- #

    def do_startup(self):
        Gtk.Application.do_startup(self)
        provider = Gtk.CssProvider()
        provider.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), provider,
                                                 Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

    def do_activate(self):
        if self.window:
            self.window.present()
            return
        self.build_window()
        self.window.show_all()
        bus_type = Gio.BusType.SESSION if os.environ.get("BLUETOOTH_CENTER_BUS") == "session" else Gio.BusType.SYSTEM
        try:
            self.bus = Gio.bus_get_sync(bus_type, None)
        except GLib.Error as error:
            self.show_empty("󰂲", "Cannot reach D-Bus", dbus_error_text(error))
            return
        self.bus.signal_subscribe(BLUEZ, None, None, None, None, Gio.DBusSignalFlags.NONE, self.on_signal)
        Gio.bus_watch_name_on_connection(self.bus, BLUEZ, Gio.BusNameWatcherFlags.NONE,
                                         self.on_service_up, self.on_service_down)

    def on_service_up(self, *_args):
        self.service_up = True
        self.register_agent()
        self.reload(start_scan=True)

    def on_service_down(self, *_args):
        self.service_up = False
        self.objects, self.adapter_path = {}, None
        self.render()

    def on_destroy(self, *_args):
        if self.bus and self.adapter_path and self.adapter_prop("Discovering"):
            self.call(self.adapter_path, ADAPTER, "StopDiscovery")
        if self.bus and self.agent_id:
            try:
                self.bus.call_sync(BLUEZ, "/org/bluez", "org.bluez.AgentManager1", "UnregisterAgent",
                                   GLib.Variant("(o)", (AGENT_PATH,)), None, Gio.DBusCallFlags.NONE, 1000, None)
            except GLib.Error:
                pass
        self.window = None

    # ---- D-Bus plumbing --------------------------------------------------- #

    def call(self, path, iface, method, params=None, done=None, timeout=25000):
        def finish(bus, result):
            try:
                value = bus.call_finish(result)
                error = None
            except GLib.Error as exc:
                value, error = None, exc
            if done:
                done(value, error)
            elif error:
                self.status(dbus_error_text(error), "bad")

        self.bus.call(BLUEZ, path, iface, method, params, None, Gio.DBusCallFlags.NONE, timeout, None, finish)

    def set_prop(self, path, iface, name, variant, done=None):
        self.call(path, PROPS, "Set", GLib.Variant("(ssv)", (iface, name, variant)), done)

    def reload(self, start_scan=False):
        def done(value, error):
            if error:
                self.objects = {}
                self.status(dbus_error_text(error), "bad")
            else:
                self.objects = value.unpack()[0]
            adapters = sorted(p for p, ifaces in self.objects.items() if ADAPTER in ifaces)
            self.adapter_path = adapters[0] if adapters else None
            self.render()
            if start_scan and self.adapter_path and self.adapter_prop("Powered") and not self.adapter_prop("Discovering"):
                self.set_scanning(True)

        self.call("/", "org.freedesktop.DBus.ObjectManager", "GetManagedObjects", None, done, 5000)

    def on_signal(self, _bus, _sender, path, iface, signal, params):
        if signal == "PropertiesChanged":
            target, changed, _invalid = params.unpack()
            if path in self.objects and target in self.objects[path]:
                self.objects[path][target].update(changed)
                self.schedule_render()
            else:
                self.schedule_reload()
        elif signal in ("InterfacesAdded", "InterfacesRemoved"):
            self.schedule_reload()

    def schedule_render(self):
        if not self.refresh_pending:
            self.refresh_pending = True
            GLib.timeout_add(150, self.flush_render)

    def flush_render(self):
        self.refresh_pending = False
        self.render()
        return False

    def schedule_reload(self):
        GLib.timeout_add(150, lambda: (self.reload(), False)[1])

    def adapter_prop(self, name, default=None):
        return self.objects.get(self.adapter_path, {}).get(ADAPTER, {}).get(name, default)

    def devices(self):
        result = []
        for path, ifaces in self.objects.items():
            dev = ifaces.get(DEVICE)
            if not dev or dev.get("Adapter") != self.adapter_path:
                continue
            item = dict(dev)
            item["path"] = path
            item["battery"] = ifaces.get(BATTERY, {}).get("Percentage")
            result.append(item)
        return result

    # ---- pairing agent ---------------------------------------------------- #

    def register_agent(self):
        if self.agent_id is None:
            info = Gio.DBusNodeInfo.new_for_xml(AGENT_XML)
            try:
                self.agent_id = self.bus.register_object(AGENT_PATH, info.interfaces[0], self.on_agent_call, None, None)
            except GLib.Error as error:
                self.status(f"Pairing agent unavailable: {dbus_error_text(error)}", "warn")
                return
        self.call("/org/bluez", "org.bluez.AgentManager1", "RegisterAgent",
                  GLib.Variant("(os)", (AGENT_PATH, "KeyboardDisplay")),
                  lambda _v, e: e is None and self.call("/org/bluez", "org.bluez.AgentManager1", "RequestDefaultAgent",
                                                        GLib.Variant("(o)", (AGENT_PATH,)), lambda *_: None))

    def device_name(self, path):
        dev = self.objects.get(path, {}).get(DEVICE, {})
        return dev.get("Alias") or dev.get("Name") or dev.get("Address") or "device"

    def on_agent_call(self, _bus, _sender, _path, _iface, method, params, invocation):
        args = params.unpack()
        reject = lambda: invocation.return_dbus_error("org.bluez.Error.Rejected", "Rejected by user")  # noqa: E731
        if method in ("Release", "Cancel"):
            invocation.return_value(None)
            return
        name = self.device_name(args[0]) if args else "device"
        if method == "RequestConfirmation":
            code = f"{args[1]:06d}"
            ok = self.ask(f"Pair with {name}?", "Check that this code is shown on the device, then confirm.", code=code)
            invocation.return_value(None) if ok else reject()
        elif method in ("RequestAuthorization", "AuthorizeService"):
            ok = self.ask(f"Allow {name}?", "The device wants to connect to this computer.")
            invocation.return_value(None) if ok else reject()
        elif method == "RequestPinCode":
            pin = self.ask(f"PIN for {name}", "Enter the PIN shown on or documented for the device (often 0000 or 1234).", entry=True)
            invocation.return_value(GLib.Variant("(s)", (pin,))) if pin else reject()
        elif method == "RequestPasskey":
            key = self.ask(f"Passkey for {name}", "Enter the 6-digit passkey shown on the device.", entry=True)
            if key and key.isdigit():
                invocation.return_value(GLib.Variant("(u)", (int(key),)))
            else:
                reject()
        elif method in ("DisplayPinCode", "DisplayPasskey"):
            code = str(args[1]) if method == "DisplayPinCode" else f"{args[1]:06d}"
            self.status(f"Type {code} on {name} and press Enter", "warn")
            self.show_code_dialog(name, code)
            invocation.return_value(None)
        else:
            reject()

    def ask(self, title, copy, code=None, entry=False):
        dialog = Gtk.Dialog(transient_for=self.window, modal=True)
        dialog.set_title(title)
        dialog.add_button("Cancel", Gtk.ResponseType.CANCEL)
        ok = dialog.add_button("Pair" if (code or entry) else "Allow", Gtk.ResponseType.OK)
        for name in ("action", "primary"):
            ok.get_style_context().add_class(name)
        dialog.set_default_response(Gtk.ResponseType.OK)
        box = dialog.get_content_area()
        box.set_spacing(8)
        for side in ("start", "end", "top", "bottom"):
            getattr(box, f"set_margin_{side}")(18)
        box.pack_start(label(title, "ctl-label"), False, False, 0)
        box.pack_start(label(copy, "hint", wrap=True), False, False, 0)
        field = None
        if code:
            box.pack_start(label(code, "passkey", xalign=0.5, ellipsize=False), False, False, 8)
        if entry:
            field = Gtk.Entry()
            field.set_activates_default(True)
            box.pack_start(field, False, False, 4)
        dialog.show_all()
        response = dialog.run()
        value = field.get_text().strip() if field else None
        dialog.destroy()
        if response != Gtk.ResponseType.OK:
            return None if entry else False
        return value if entry else True

    def show_code_dialog(self, name, code):
        dialog = Gtk.MessageDialog(transient_for=self.window, modal=False, message_type=Gtk.MessageType.INFO,
                                   buttons=Gtk.ButtonsType.CLOSE, text=f"Type this code on {name}")
        dialog.format_secondary_markup(f"<span size='xx-large' weight='bold'>{code}</span>\nthen press Enter on the device.")
        dialog.connect("response", lambda d, _r: d.destroy())
        dialog.show_all()

    # ---- window ----------------------------------------------------------- #

    def build_window(self):
        self.window = Gtk.ApplicationWindow(application=self)
        self.window.set_title("Bluetooth Center")
        self.window.set_default_size(900, 680)
        self.window.set_size_request(720, 500)
        self.window.connect("destroy", self.on_destroy)
        self.window.connect("key-press-event", self.on_key)

        header = Gtk.HeaderBar()
        header.set_show_close_button(True)
        header.props.title = "BLUETOOTH CENTER"
        header.props.subtitle = "Looking for Bluetooth…"
        self.header = header
        self.spinner = Gtk.Spinner()
        header.pack_end(self.spinner)
        self.window.set_titlebar(header)

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        root.set_name("root")

        controls = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=14)
        controls.set_name("controls")
        text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        text.set_valign(Gtk.Align.CENTER)
        self.adapter_label = label("Bluetooth", "ctl-label")
        self.adapter_copy = label("", "ctl-copy")
        text.pack_start(self.adapter_label, False, False, 0)
        text.pack_start(self.adapter_copy, False, False, 0)
        controls.pack_start(text, True, True, 0)
        self.visible_check = Gtk.CheckButton(label="Visible to others")
        self.visible_check.get_style_context().add_class("hint")
        self.visible_check.set_tooltip_text("Let phones and other computers find this machine (2 minutes)")
        self.visible_handler = self.visible_check.connect("toggled", self.on_visible)
        self.visible_check.set_valign(Gtk.Align.CENTER)
        self.scan_button = Gtk.Button(label="󰑐  Scan")
        self.scan_button.get_style_context().add_class("action")
        self.scan_button.set_valign(Gtk.Align.CENTER)
        self.scan_button.connect("clicked", lambda *_: self.set_scanning(not self.adapter_prop("Discovering")))
        self.power = Gtk.Switch()
        self.power.set_valign(Gtk.Align.CENTER)
        self.power.set_tooltip_text("Bluetooth on/off")
        self.power_handler = self.power.connect("notify::active", self.on_power)
        for widget in (self.power, self.scan_button, self.visible_check):
            controls.pack_end(widget, False, False, 0)
        root.pack_start(controls, False, False, 0)

        self.stack = Gtk.Stack()
        self.list_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        for side in ("start", "end"):
            getattr(self.list_box, f"set_margin_{side}")(22)
        self.list_box.set_margin_bottom(18)
        scroller = Gtk.ScrolledWindow()
        scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroller.add(self.list_box)
        self.stack.add_named(scroller, "list")
        self.empty_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.stack.add_named(self.empty_box, "empty")
        root.pack_start(self.stack, True, True, 0)

        status = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        status.set_name("statusbar")
        self.status_label = label("Ready")
        status.pack_start(self.status_label, True, True, 0)
        status.pack_end(label("F5 scan  •  Esc close", xalign=1.0), False, False, 0)
        root.pack_start(status, False, False, 0)
        self.window.add(root)

    def on_key(self, _widget, event):
        if event.keyval == Gdk.KEY_Escape:
            self.window.close()
            return True
        if event.keyval == Gdk.KEY_F5 and self.adapter_path:
            self.set_scanning(True)
            return True
        return False

    def status(self, text, kind=None):
        colors = {"good": "#78f0c2", "bad": "#ff6b81", "warn": "#ffcc66", "busy": "#5ee7f7"}
        if kind in colors:
            self.status_label.set_markup(f"<span foreground='{colors[kind]}'><b>{GLib.markup_escape_text(text)}</b></span>")
        else:
            self.status_label.set_text(text)

    def show_empty(self, icon, title, copy, button=None):
        clear(self.empty_box)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box.set_name("empty")
        box.set_valign(Gtk.Align.CENTER)
        box.set_vexpand(True)
        box.pack_start(label(icon, "empty-icon", xalign=0.5, ellipsize=False), False, False, 0)
        box.pack_start(label(title, "empty-title", xalign=0.5), False, False, 0)
        copy_label = label(copy, "empty-copy", xalign=0.5, wrap=True)
        copy_label.set_justify(Gtk.Justification.CENTER)
        copy_label.set_halign(Gtk.Align.CENTER)
        box.pack_start(copy_label, False, False, 0)
        if button:
            button.set_halign(Gtk.Align.CENTER)
            button.set_margin_top(14)
            box.pack_start(button, False, False, 0)
        self.empty_box.pack_start(box, True, True, 0)
        self.empty_box.show_all()
        self.stack.set_visible_child_name("empty")

    # ---- rendering -------------------------------------------------------- #

    def render(self):
        if not self.window:
            return
        has_adapter = bool(self.adapter_path)
        powered = bool(self.adapter_prop("Powered"))
        scanning = bool(self.adapter_prop("Discovering"))
        for widget in (self.power, self.scan_button, self.visible_check):
            widget.set_sensitive(has_adapter)
        self.scan_button.set_sensitive(has_adapter and powered)
        self.visible_check.set_sensitive(has_adapter and powered)
        self.power.handler_block(self.power_handler)
        self.power.set_active(powered)
        self.power.handler_unblock(self.power_handler)
        self.visible_check.handler_block(self.visible_handler)
        self.visible_check.set_active(bool(self.adapter_prop("Discoverable")))
        self.visible_check.handler_unblock(self.visible_handler)
        ctx = self.scan_button.get_style_context()
        (ctx.add_class if scanning else ctx.remove_class)("scanning")
        self.scan_button.set_label("󰓛  Stop scan" if scanning else "󰑐  Scan")
        (self.spinner.start if scanning or self.busy else self.spinner.stop)()

        if not self.service_up:
            start = Gtk.Button(label="Start Bluetooth service")
            for name in ("action", "primary"):
                start.get_style_context().add_class(name)
            start.connect("clicked", self.start_service)
            self.header.props.subtitle = "Bluetooth service is not running"
            self.adapter_label.set_text("Bluetooth")
            self.adapter_copy.set_text("Service stopped")
            self.show_empty("󰂲", "Bluetooth service is not running",
                            "BlueZ (bluetoothd) is stopped. On machines without a Bluetooth adapter this is normal — "
                            "the service only starts when an adapter is present. Plug in a USB Bluetooth dongle, or "
                            "start the service if you know there is an adapter.", start)
            return
        if not has_adapter:
            self.header.props.subtitle = "No adapter"
            self.adapter_label.set_text("Bluetooth")
            self.adapter_copy.set_text("No adapter found")
            self.show_empty("󰂲", "No Bluetooth adapter detected",
                            "BlueZ is running but sees no Bluetooth hardware. Plug in a USB Bluetooth dongle and this "
                            "window will update automatically.")
            return

        adapter = self.objects[self.adapter_path][ADAPTER]
        name = adapter.get("Alias") or adapter.get("Name") or "This computer"
        self.adapter_label.set_text(f"{name}")
        self.adapter_copy.set_text(f"{adapter.get('Address', '')}  •  {'on' if powered else 'off'}"
                                   + ("  •  visible" if adapter.get("Discoverable") else ""))
        devices = self.devices()
        connected = [d for d in devices if d.get("Connected")]
        self.header.props.subtitle = (", ".join(d.get("Alias") or d.get("Name", "?") for d in connected[:3]) + " connected"
                                      if connected else ("Scanning…" if scanning else ("On" if powered else "Off")))
        if not powered:
            turn_on = Gtk.Button(label="Turn Bluetooth on")
            for cls in ("action", "primary"):
                turn_on.get_style_context().add_class(cls)
            turn_on.connect("clicked", lambda *_: self.power.set_active(True))
            self.show_empty("󰂲", "Bluetooth is off", "Turn it on to connect headphones, mice, keyboards and phones.", turn_on)
            return

        clear(self.list_box)
        paired = sorted((d for d in devices if d.get("Paired")),
                        key=lambda d: (not d.get("Connected"), (d.get("Alias") or "").lower()))
        nearby = sorted((d for d in devices if not d.get("Paired") and (d.get("Name") or d.get("Alias"))
                         and d.get("Alias") != d.get("Address", "").replace(":", "-")),
                        key=lambda d: -(d.get("RSSI") or -999))
        self.list_box.pack_start(label("MY DEVICES", "group-title"), False, False, 0)
        if not paired:
            self.list_box.pack_start(label("No paired devices yet — put a device in pairing mode and it will show up below.",
                                           "hint"), False, False, 4)
        for dev in paired:
            self.list_box.pack_start(self.device_row(dev), False, False, 0)
        self.list_box.pack_start(label("NEARBY" + ("  •  scanning…" if scanning else ""), "group-title"), False, False, 0)
        if not nearby:
            self.list_box.pack_start(label("Nothing found yet. Make sure the device is in pairing mode (often: hold the "
                                           "power or Bluetooth button until a light flashes)." if scanning else
                                           "Press Scan to look for devices.", "hint", wrap=True), False, False, 4)
        for dev in nearby:
            self.list_box.pack_start(self.device_row(dev), False, False, 0)
        self.list_box.show_all()
        self.stack.set_visible_child_name("list")

    def device_row(self, dev):
        row = Gtk.ListBoxRow()
        ctx = row.get_style_context()
        ctx.add_class("dev")
        if dev.get("Connected"):
            ctx.add_class("connected")
        inner = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        inner.get_style_context().add_class("row-inner")
        icon = label(DEVICE_ICONS.get(dev.get("Icon", ""), "󰂯"), "dev-icon", xalign=0.5, ellipsize=False)
        icon.set_valign(Gtk.Align.CENTER)
        inner.pack_start(icon, False, False, 0)
        names = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        names.set_valign(Gtk.Align.CENTER)
        names.pack_start(label(dev.get("Alias") or dev.get("Name") or dev.get("Address", "?"), "dev-name"), False, False, 0)
        kinds = {"audio-headset": "Headset", "audio-headphones": "Headphones", "audio-card": "Speaker",
                 "audio-speakers": "Speaker", "input-mouse": "Mouse", "input-keyboard": "Keyboard",
                 "input-gaming": "Game controller", "input-tablet": "Tablet", "phone": "Phone",
                 "computer": "Computer", "video-display": "Display", "printer": "Printer"}
        meta = [kinds.get(dev.get("Icon", ""), ""), dev.get("Address", "")]
        if dev.get("Paired"):
            meta.append("trusted" if dev.get("Trusted") else "not trusted")
        elif dev.get("RSSI") is not None:
            rssi = dev["RSSI"]
            meta.append("strong signal" if rssi > -60 else ("ok signal" if rssi > -80 else "weak signal"))
        names.pack_start(label("  •  ".join(m for m in meta if m), "dev-meta"), False, False, 0)
        inner.pack_start(names, True, True, 0)

        path = dev["path"]
        busy = path in self.busy
        if dev.get("Paired"):
            menu_button = Gtk.MenuButton(label="⋯")
            menu_button.get_style_context().add_class("icon")
            menu_button.set_valign(Gtk.Align.CENTER)
            menu = Gtk.Menu()
            trust = Gtk.MenuItem(label="Don't auto-connect (untrust)" if dev.get("Trusted") else "Trust (auto-connect)")
            trust.connect("activate", lambda *_: self.set_prop(path, DEVICE, "Trusted", GLib.Variant("b", not dev.get("Trusted"))))
            forget = Gtk.MenuItem(label="Forget device")
            forget.connect("activate", lambda *_: self.forget(dev))
            menu.append(trust)
            menu.append(forget)
            menu.show_all()
            menu_button.set_popup(menu)
            inner.pack_end(menu_button, False, False, 0)

        if busy:
            spin = Gtk.Spinner()
            spin.start()
            inner.pack_end(spin, False, False, 4)
        elif dev.get("Connected"):
            button = Gtk.Button(label="Disconnect")
            button.get_style_context().add_class("action")
            button.connect("clicked", lambda *_: self.disconnect_device(dev))
            inner.pack_end(button, False, False, 0)
        elif dev.get("Paired"):
            button = Gtk.Button(label="Connect")
            for cls in ("action", "primary"):
                button.get_style_context().add_class(cls)
            button.connect("clicked", lambda *_: self.connect_device(dev))
            inner.pack_end(button, False, False, 0)
        else:
            button = Gtk.Button(label="Pair")
            for cls in ("action", "primary"):
                button.get_style_context().add_class(cls)
            button.connect("clicked", lambda *_: self.pair(dev))
            inner.pack_end(button, False, False, 0)
        for widget in inner.get_children()[-1:]:
            widget.set_valign(Gtk.Align.CENTER)

        battery = dev.get("battery")
        if battery is not None:
            pill = label(f"󰁹 {battery}%", f"pill {'low' if battery <= 20 else 'batt'}", ellipsize=False)
            pill.set_valign(Gtk.Align.CENTER)
            inner.pack_end(pill, False, False, 0)
        if dev.get("Connected"):
            pill = label("CONNECTED", "pill on", ellipsize=False)
            pill.set_valign(Gtk.Align.CENTER)
            inner.pack_end(pill, False, False, 0)
        row.add(inner)
        return row

    # ---- actions ---------------------------------------------------------- #

    def mark_busy(self, path, on):
        (self.busy.add if on else self.busy.discard)(path)
        self.render()

    def connect_device(self, dev):
        path, name = dev["path"], dev.get("Alias") or dev.get("Name", "device")
        self.mark_busy(path, True)
        self.status(f"Connecting to {name}…", "busy")

        def done(_value, error):
            self.mark_busy(path, False)
            self.status(f"{name}: {dbus_error_text(error)}" if error else f"Connected to {name}", "bad" if error else "good")

        self.call(path, DEVICE, "Connect", None, done, 30000)

    def disconnect_device(self, dev):
        path, name = dev["path"], dev.get("Alias") or dev.get("Name", "device")
        self.mark_busy(path, True)

        def done(_value, error):
            self.mark_busy(path, False)
            self.status(f"{name}: {dbus_error_text(error)}" if error else f"Disconnected {name}", "bad" if error else "good")

        self.call(path, DEVICE, "Disconnect", None, done)

    def pair(self, dev):
        path, name = dev["path"], dev.get("Alias") or dev.get("Name", "device")
        self.mark_busy(path, True)
        self.status(f"Pairing with {name}… confirm on the device if asked", "busy")

        def paired(_value, error):
            if error and "Already Exists" not in str(error):
                self.mark_busy(path, False)
                self.status(f"{name}: {dbus_error_text(error)}", "bad")
                return
            # trust so it reconnects automatically, then connect
            self.set_prop(path, DEVICE, "Trusted", GLib.Variant("b", True), lambda *_: None)
            self.status(f"Paired with {name} — connecting…", "busy")
            self.call(path, DEVICE, "Connect", None, connected, 30000)

        def connected(_value, error):
            self.mark_busy(path, False)
            if error:
                self.status(f"Paired with {name}, but connecting failed: {dbus_error_text(error)}", "warn")
            else:
                self.status(f"{name} is paired and connected", "good")

        self.call(path, DEVICE, "Pair", None, paired, 60000)

    def forget(self, dev):
        name = dev.get("Alias") or dev.get("Name", "device")
        dialog = Gtk.MessageDialog(transient_for=self.window, modal=True, message_type=Gtk.MessageType.WARNING,
                                   buttons=Gtk.ButtonsType.NONE, text=f"Forget {name}?")
        dialog.format_secondary_text("You will need to pair it again to use it.")
        dialog.add_buttons("Cancel", Gtk.ResponseType.CANCEL, "Forget", Gtk.ResponseType.ACCEPT)
        response = dialog.run()
        dialog.destroy()
        if response != Gtk.ResponseType.ACCEPT:
            return
        self.call(self.adapter_path, ADAPTER, "RemoveDevice", GLib.Variant("(o)", (dev["path"],)),
                  lambda _v, e: self.status(dbus_error_text(e) if e else f"Forgot {name}", "bad" if e else "good"))

    def on_power(self, switch, _pspec):
        on = switch.get_active()

        def done(_value, error):
            if error and "rfkill" in str(error).lower() and on:
                self.status("Bluetooth was blocked — unblocking…", "warn")
                subprocess.run(["rfkill", "unblock", "bluetooth"], capture_output=True)
                GLib.timeout_add(800, lambda: (self.set_prop(self.adapter_path, ADAPTER, "Powered",
                                                             GLib.Variant("b", True), done), False)[1])
                return
            if error:
                self.status(dbus_error_text(error), "bad")
                self.render()
            elif on:
                self.status("Bluetooth on", "good")
                GLib.timeout_add(600, lambda: (self.set_scanning(True), False)[1])
            else:
                self.status("Bluetooth off", "good")

        self.set_prop(self.adapter_path, ADAPTER, "Powered", GLib.Variant("b", on), done)

    def on_visible(self, check):
        on = check.get_active()
        if on:
            self.set_prop(self.adapter_path, ADAPTER, "DiscoverableTimeout", GLib.Variant("u", 120), lambda *_: None)
        self.set_prop(self.adapter_path, ADAPTER, "Discoverable", GLib.Variant("b", on),
                      lambda _v, e: self.status(dbus_error_text(e) if e else
                                                ("Visible to nearby devices for 2 minutes" if on else "Hidden"),
                                                "bad" if e else "good"))

    def set_scanning(self, on):
        if not self.adapter_path:
            return
        if self.scan_timer:
            GLib.source_remove(self.scan_timer)
            self.scan_timer = None
        if on:
            self.call(self.adapter_path, ADAPTER, "StartDiscovery", None,
                      lambda _v, e: e and "In Progress" not in str(e) and self.status(dbus_error_text(e), "bad"))
            self.scan_timer = GLib.timeout_add_seconds(SCAN_SECONDS, self.stop_scan_timer)
            self.status(f"Scanning for {SCAN_SECONDS}s…", "busy")
        else:
            self.call(self.adapter_path, ADAPTER, "StopDiscovery", None, lambda *_: None)
            self.status("Scan stopped")

    def stop_scan_timer(self):
        self.scan_timer = None
        if self.adapter_prop("Discovering"):
            self.call(self.adapter_path, ADAPTER, "StopDiscovery", None, lambda *_: None)
        return False

    def start_service(self, *_args):
        self.status("Starting bluetooth.service…", "busy")
        try:
            subprocess.Popen(["systemctl", "start", "bluetooth.service"])
        except OSError as error:
            self.status(str(error), "bad")


if __name__ == "__main__":
    sys.exit(BluetoothCenter().run(sys.argv))
