#!/usr/bin/env python3
"""Visual screen-share picker for xdg-desktop-portal-hyprland.

XDPH runs this instead of `hyprland-share-picker` (see ~/.config/hypr/xdph.conf)
whenever an app such as Google Meet asks to share a screen, window, or region.

Protocol (XDPH 1.4.x):
  input   XDPH_WINDOW_SHARING_LIST = "<id>[HC>]<class>[HT>]<title>[HE>]<addr>[HA>]..."
          argv may contain --allow-token
  output  one stdout line "[SELECTION]<flags>/<choice>" where flags is "r" to
          allow a restore token and choice is one of
            screen:<output>
            window:<id>
            region:<output>@<x>,<y>,<w>,<h>   (x/y relative to that output)
          Exiting without printing a selection cancels the share.

If the panel cannot start for any reason, the stock picker is executed instead
so screen sharing keeps working.
"""

import json
import os
import subprocess
import sys
import threading

FALLBACK = "/usr/bin/hyprland-share-picker"


def fallback(reason):
    print(f"SharePicker: {reason}; using stock picker", file=sys.stderr)
    if os.access(FALLBACK, os.X_OK):
        os.execv(FALLBACK, [FALLBACK, *sys.argv[1:]])
    sys.exit(1)


os.environ.setdefault("GDK_BACKEND", "wayland")
try:
    import gi

    gi.require_version("Gtk", "3.0")
    gi.require_version("Gdk", "3.0")
    gi.require_version("GdkPixbuf", "2.0")
    from gi.repository import Gdk, GdkPixbuf, Gio, GLib, Gtk, Pango
except (ImportError, ValueError) as error:
    fallback(f"GTK unavailable ({error})")


CSS = b"""
@define-color bg #080b16;
@define-color panel #0d1220;
@define-color card #12192a;
@define-color hover #18243a;
@define-color border #26334f;
@define-color text #e5ecff;
@define-color muted #8794b3;
@define-color cyan #5ee7f7;
@define-color violet #b991ff;
@define-color green #78f0c2;
@define-color amber #ffcc66;

* { font-family: "JetBrainsMono Nerd Font", "Noto Sans"; outline: none; }
window, #root { background: @bg; color: @text; }

#top { padding: 16px 22px 10px; background: @panel; border-bottom: 1px solid @border; }
.title { color: @text; font-size: 17px; font-weight: 800; }
.subtitle { margin-top: 3px; color: @muted; font-size: 10px; }
.app-chip { padding: 3px 10px; color: @amber; background: alpha(@amber, .10); border-radius: 9px; font-size: 10px; font-weight: 800; }

button.tab {
  min-height: 34px; padding: 0 16px; margin-right: 6px;
  color: @muted; background: transparent; border: 1px solid transparent; border-radius: 9px; box-shadow: none;
  font-size: 11px; font-weight: 800;
}
button.tab:hover { color: @text; background: @hover; }
button.tab.active { color: @cyan; background: alpha(@cyan, .11); border-color: alpha(@cyan, .35); }

flowbox { padding: 14px 16px; }
flowboxchild { padding: 0; border-radius: 13px; }
flowboxchild:selected { background: transparent; }
.card {
  padding: 10px; background: @card; border: 2px solid @border; border-radius: 13px;
}
flowboxchild:hover .card { background: @hover; border-color: alpha(@cyan, .45); }
flowboxchild:selected .card { border-color: @cyan; background: #132a38; }
.thumb { background: #05070f; border-radius: 8px; }
.thumb-placeholder { color: @violet; font-size: 40px; }
.card-title { margin-top: 8px; color: @text; font-size: 12px; font-weight: 800; }
.card-meta { margin-top: 2px; color: @muted; font-size: 9px; }
.badge { padding: 2px 8px; border-radius: 8px; font-size: 9px; font-weight: 800; color: @green; background: alpha(@green, .12); }
.badge.pos { color: @violet; background: alpha(@violet, .12); }
.empty { margin: 40px; color: @muted; font-size: 11px; }

#bottom { padding: 12px 22px; background: @panel; border-top: 1px solid @border; }
checkbutton { color: @muted; font-size: 10px; }
.hint { color: @muted; font-size: 9px; }
button.action {
  min-height: 38px; padding: 0 18px; color: @text;
  background: #111827; border: 1px solid @border; border-radius: 10px; box-shadow: none;
  font-size: 11px; font-weight: 800;
}
button.action:hover { background: @hover; border-color: alpha(@cyan, .45); }
button.action.primary { color: #061014; background: @cyan; border-color: @cyan; }
button.action.primary:hover { background: #93f2fb; }
button:disabled { opacity: .38; }
scrollbar slider { min-width: 6px; min-height: 32px; background: #34415d; border-radius: 9px; }
scrollbar trough { background: transparent; }
"""

SCREEN_THUMB = (360, 203)
WINDOW_THUMB = (260, 150)


def hyprctl_json(*args):
    try:
        out = subprocess.run(["hyprctl", "-j", *args], capture_output=True, text=True, timeout=3).stdout
        return json.loads(out)
    except (OSError, subprocess.SubprocessError, ValueError):
        return []


def parse_window_list(raw):
    windows = []
    rolling = raw or ""
    while "[HA>]" in rolling:
        record, rolling = rolling.split("[HA>]", 1)
        try:
            handle, rest = record.split("[HC>]", 1)
            klass, rest = rest.split("[HT>]", 1)
            title, addr = rest.split("[HE>]", 1)
            int(handle)
        except ValueError:
            continue
        try:
            address = int(addr or "0", 0)
        except ValueError:
            address = 0
        windows.append({"id": handle, "class": klass, "title": title, "address": address})
    return windows


def capture(args, size):
    """Grab a screenshot with grim and scale it into `size`; None on failure."""
    try:
        data = subprocess.run(
            ["grim", "-t", "ppm", *args, "-"], capture_output=True, timeout=4
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    if not data:
        return None
    try:
        loader = GdkPixbuf.PixbufLoader()
        loader.write(data)
        loader.close()
        pixbuf = loader.get_pixbuf()
    except GLib.Error:
        return None
    width, height = pixbuf.get_width(), pixbuf.get_height()
    ratio = min(size[0] / width, size[1] / height)
    return pixbuf.scale_simple(max(1, int(width * ratio)), max(1, int(height * ratio)), GdkPixbuf.InterpType.BILINEAR)


def label(text, css, xalign=0.0, ellipsize=True):
    widget = Gtk.Label(label=text)
    widget.set_xalign(xalign)
    if ellipsize:
        widget.set_ellipsize(Pango.EllipsizeMode.END)
        widget.set_max_width_chars(24)  # keep natural width small so FlowBox can fit columns
    for name in css.split():
        widget.get_style_context().add_class(name)
    return widget


class SharePicker(Gtk.Window):
    def __init__(self, allow_token):
        super().__init__(title="Share your screen")
        self.set_default_size(1020, 690)
        self.set_keep_above(True)
        self.connect("destroy", Gtk.main_quit)
        self.connect("key-press-event", self.on_key)
        self.result = None
        self.tab = "screens"

        self.monitors = sorted(hyprctl_json("monitors"), key=lambda m: (m.get("x", 0), m.get("y", 0)))
        self.clients = {}
        for client in hyprctl_json("clients"):
            try:
                self.clients[int(client["address"], 16)] = client
            except (KeyError, ValueError, TypeError):
                continue
        self.visible_workspaces = {m.get("activeWorkspace", {}).get("id") for m in self.monitors}
        self.windows = [
            w for w in parse_window_list(os.environ.get("XDPH_WINDOW_SHARING_LIST", ""))
            if w["class"] not in ("SharePicker.py", "hyprland-share-picker")
        ]
        self.requester = self.guess_requester()

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        root.set_name("root")
        self.add(root)

        top = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        top.set_name("top")
        heading = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        heading.pack_start(label("󰹑  Share your screen", "title"), False, False, 0)
        if self.requester:
            heading.pack_start(label(f"requested by {self.requester}", "app-chip", ellipsize=False), False, False, 0)
        top.pack_start(heading, False, False, 0)
        top.pack_start(
            label("Pick exactly what the other people will see. Thumbnails are live snapshots.", "subtitle"),
            False, False, 0,
        )
        tabs = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        tabs.set_margin_top(12)
        self.tab_buttons = {}
        for key, text in (("screens", f"󰍹  Entire screen  ({len(self.monitors)})"),
                          ("windows", f"󰖯  Window  ({len(self.windows)})"),
                          ("region", "󰩭  Region")):
            button = Gtk.Button(label=text)
            button.get_style_context().add_class("tab")
            button.connect("clicked", lambda _b, k=key: self.show_tab(k))
            tabs.pack_start(button, False, False, 0)
            self.tab_buttons[key] = button
        top.pack_start(tabs, False, False, 0)
        root.pack_start(top, False, False, 0)

        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self.screen_box = self.flowbox(2)
        self.window_box = self.flowbox(3)
        self.stack.add_named(self.scrolled(self.screen_box), "screens")
        self.stack.add_named(self.scrolled(self.window_box), "windows")
        self.stack.add_named(self.build_region_page(), "region")
        root.pack_start(self.stack, True, True, 0)

        bottom = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        bottom.set_name("bottom")
        self.remember = Gtk.CheckButton(label="Remember this choice for this app")
        self.remember.set_active(allow_token)
        self.remember.set_tooltip_text("Lets the app re-share the same source next time without asking")
        bottom.pack_start(self.remember, False, False, 0)
        bottom.pack_start(label("Enter share  •  Tab switch  •  1-9 pick  •  Esc cancel", "hint"), True, True, 0)
        cancel = Gtk.Button(label="Cancel")
        cancel.get_style_context().add_class("action")
        cancel.connect("clicked", lambda *_: self.destroy())
        self.share = Gtk.Button(label="Share")
        for name in ("action", "primary"):
            self.share.get_style_context().add_class(name)
        self.share.connect("clicked", lambda *_: self.confirm())
        bottom.pack_end(self.share, False, False, 0)
        bottom.pack_end(cancel, False, False, 0)
        root.pack_start(bottom, False, False, 0)

        self.populate_screens()
        self.populate_windows()
        self.show_all()
        self.show_tab("screens")
        threading.Thread(target=self.load_thumbnails, daemon=True).start()

    # ---- layout helpers --------------------------------------------------- #

    def flowbox(self, columns):
        box = Gtk.FlowBox()
        box.set_selection_mode(Gtk.SelectionMode.SINGLE)
        box.set_max_children_per_line(columns)
        box.set_min_children_per_line(1)
        box.set_column_spacing(14)
        box.set_row_spacing(14)
        box.set_homogeneous(True)
        box.set_valign(Gtk.Align.START)
        box.set_activate_on_single_click(False)
        box.connect("child-activated", lambda *_: self.confirm())
        box.connect("selected-children-changed", lambda *_: self.update_share())
        return box

    @staticmethod
    def scrolled(child):
        window = Gtk.ScrolledWindow()
        window.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        window.add(child)
        return window

    def card(self, size, title, meta, badges=(), icon="󰍹", app_class=None):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box.get_style_context().add_class("card")
        frame = Gtk.Box()
        frame.get_style_context().add_class("thumb")
        frame.set_size_request(*size)
        image = Gtk.Image()
        placeholder = self.app_icon(app_class) or label(icon, "thumb-placeholder", xalign=0.5, ellipsize=False)
        frame.pack_start(placeholder, True, True, 0)
        frame.pack_start(image, True, True, 0)
        box.pack_start(frame, False, False, 0)
        title_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        title_row.pack_start(label(title, "card-title"), True, True, 0)
        for text, kind in badges:
            badge = label(text, f"badge {kind}", xalign=0.5, ellipsize=False)
            badge.set_valign(Gtk.Align.END)
            title_row.pack_end(badge, False, False, 0)
        box.pack_start(title_row, False, False, 0)
        box.pack_start(label(meta, "card-meta"), False, False, 0)
        box.image, box.placeholder = image, placeholder
        return box

    @staticmethod
    def app_icon(app_class):
        """The app's theme icon (e.g. google-chrome) for windows we cannot snapshot."""
        if not app_class:
            return None
        theme = Gtk.IconTheme.get_default()
        for name in (app_class, app_class.lower(), app_class.split(".")[-1].lower()):
            if theme.has_icon(name):
                return Gtk.Image.new_from_icon_name(name, Gtk.IconSize.DIALOG)
        info = Gio.DesktopAppInfo.new(f"{app_class}.desktop")
        if info and info.get_icon():
            return Gtk.Image.new_from_gicon(info.get_icon(), Gtk.IconSize.DIALOG)
        return None

    # ---- content ---------------------------------------------------------- #

    def screen_position(self, index):
        count = len(self.monitors)
        if count == 1:
            return "Only screen"
        if count == 2:
            return ("Left", "Right")[index]
        return f"#{index + 1} from left"

    def populate_screens(self):
        self.screen_cards = []
        cursor_monitor = next((m["name"] for m in self.monitors if m.get("focused")), None)
        for index, monitor in enumerate(self.monitors):
            badges = [(self.screen_position(index), "pos")]
            if monitor["name"] == cursor_monitor:
                badges.append(("YOU ARE HERE", ""))
            meta = (f"{index + 1}  •  {monitor['name']}  •  {monitor['width']}×{monitor['height']}"
                    f"  •  workspace {monitor.get('activeWorkspace', {}).get('name', '?')}")
            title = f"{self.screen_position(index)} screen" if len(self.monitors) > 1 else "Entire screen"
            model = (monitor.get("model") or "").strip()
            if model:
                title += f"  —  {model}"
            card = self.card(SCREEN_THUMB, title, meta, badges)
            card.choice = f"screen:{monitor['name']}"
            card.capture = ["-o", monitor["name"]]
            self.screen_box.add(card)
            self.screen_cards.append(card)
        if self.screen_cards:
            default = next((c for c, m in zip(self.screen_cards, self.monitors) if m["name"] == cursor_monitor),
                           self.screen_cards[0])
            self.screen_box.select_child(default.get_parent())

    def populate_windows(self):
        self.window_cards = []
        if not self.windows:
            self.window_box.add(label("No shareable windows were reported by the portal.", "empty", xalign=0.5))
            return
        for index, window in enumerate(self.windows):
            client = self.clients.get(window["address"])
            workspace = client.get("workspace", {}) if client else {}
            visible = bool(client) and workspace.get("id") in self.visible_workspaces and not client.get("hidden")
            meta_bits = [window["class"] or "unknown app"]
            if workspace.get("name"):
                meta_bits.append(f"workspace {workspace['name']}")
            badges = [("VISIBLE", "")] if visible else []
            card = self.card(WINDOW_THUMB, window["title"] or window["class"] or "Untitled window",
                             f"{index + 1}  •  " + "  •  ".join(meta_bits), badges, icon="󰖯",
                             app_class=window["class"])
            card.set_tooltip_text(f"{window['title']}\n{window['class']}")
            card.choice = f"window:{window['id']}"
            card.capture = None
            if visible and client.get("size") and client.get("at"):
                (x, y), (w, h) = client["at"], client["size"]
                card.capture = ["-g", f"{x},{y} {w}x{h}"]
            self.window_box.add(card)
            self.window_cards.append(card)
        self.window_box.select_child(self.window_cards[0].get_parent())

    def build_region_page(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        box.set_valign(Gtk.Align.CENTER)
        box.pack_start(label("󰩭", "thumb-placeholder", xalign=0.5, ellipsize=False), False, False, 0)
        box.pack_start(label("Share part of a screen", "card-title", xalign=0.5), False, False, 0)
        box.pack_start(
            label("This panel hides and you drag a rectangle. Only that area is shared.", "card-meta", xalign=0.5),
            False, False, 0,
        )
        button = Gtk.Button(label="Select region…")
        for name in ("action", "primary"):
            button.get_style_context().add_class(name)
        button.set_halign(Gtk.Align.CENTER)
        button.set_margin_top(8)
        button.connect("clicked", lambda *_: self.select_region())
        box.pack_start(button, False, False, 0)
        return box

    def load_thumbnails(self):
        for card in [*self.screen_cards, *self.window_cards]:
            if not card.capture:
                continue
            size = SCREEN_THUMB if card in self.screen_cards else WINDOW_THUMB
            pixbuf = capture(card.capture, size)
            if pixbuf:
                GLib.idle_add(self.set_thumb, card, pixbuf)

    @staticmethod
    def set_thumb(card, pixbuf):
        card.image.set_from_pixbuf(pixbuf)
        card.placeholder.hide()
        return False

    def guess_requester(self):
        """Best guess at which app asked: the focused window when the picker launched."""
        active = hyprctl_json("activewindow")
        if isinstance(active, dict):
            return (active.get("class") or "").replace("google-chrome", "Google Chrome") or None
        return None

    # ---- behaviour -------------------------------------------------------- #

    def show_tab(self, key):
        self.tab = key
        self.stack.set_visible_child_name(key)
        for name, button in self.tab_buttons.items():
            ctx = button.get_style_context()
            (ctx.add_class if name == key else ctx.remove_class)("active")
        self.update_share()
        box = {"screens": self.screen_box, "windows": self.window_box}.get(key)
        if box and box.get_selected_children():
            box.get_selected_children()[0].grab_focus()

    def current_box(self):
        return {"screens": self.screen_box, "windows": self.window_box}.get(self.tab)

    def selected_card(self):
        box = self.current_box()
        children = box.get_selected_children() if box else []
        card = children[0].get_child() if children else None
        return card if card is not None and hasattr(card, "choice") else None

    def update_share(self):
        if self.tab == "region":
            self.share.set_label("Select region…")
            self.share.set_sensitive(True)
            return
        card = self.selected_card()
        self.share.set_sensitive(card is not None)
        self.share.set_label("Share this screen" if self.tab == "screens" else "Share this window")

    def confirm(self):
        if self.tab == "region":
            self.select_region()
            return
        card = self.selected_card()
        if card:
            self.finish(card.choice)

    def finish(self, choice):
        flags = "r" if self.remember.get_active() else ""
        self.result = f"[SELECTION]{flags}/{choice}"
        self.destroy()

    def select_region(self):
        self.hide()
        GLib.timeout_add(250, self.run_slurp)

    def run_slurp(self):
        try:
            out = subprocess.run(
                ["slurp", "-f", "%o %x %y %w %h"], capture_output=True, text=True, timeout=120
            ).stdout.split()
            name, x, y, w, h = out[0], *map(int, out[1:5])
        except (OSError, subprocess.SubprocessError, ValueError, IndexError):
            self.show()  # cancelled the drag: go back to the panel
            return False
        monitor = next((m for m in self.monitors if m["name"] == name), None)
        if not monitor or w <= 0 or h <= 0:
            self.show()
            return False
        self.finish(f"region:{name}@{x - monitor['x']},{y - monitor['y']},{w},{h}")
        return False

    def on_key(self, _widget, event):
        key = event.keyval
        if key == Gdk.KEY_Escape:
            self.destroy()
            return True
        if key in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            self.confirm()
            return True
        if key in (Gdk.KEY_Tab, Gdk.KEY_ISO_Left_Tab):
            order = ["screens", "windows", "region"]
            step = -1 if key == Gdk.KEY_ISO_Left_Tab else 1
            self.show_tab(order[(order.index(self.tab) + step) % len(order)])
            return True
        if Gdk.KEY_1 <= key <= Gdk.KEY_9:
            cards = {"screens": self.screen_cards, "windows": self.window_cards}.get(self.tab, [])
            index = key - Gdk.KEY_1
            if index < len(cards):
                self.current_box().select_child(cards[index].get_parent())
                cards[index].get_parent().grab_focus()
            return True
        return False


def main():
    allow_token = "--allow-token" in sys.argv[1:]
    try:
        provider = Gtk.CssProvider()
        provider.load_from_data(CSS)
        screen = Gdk.Screen.get_default()
        if screen is None:
            fallback("no display")
        Gtk.StyleContext.add_provider_for_screen(screen, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        picker = SharePicker(allow_token)
    except Exception as error:  # noqa: BLE001 - never leave a share request hanging
        fallback(f"startup failed ({error})")
    Gtk.main()
    if picker.result:
        print(picker.result, flush=True)
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
