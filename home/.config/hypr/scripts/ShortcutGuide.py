#!/usr/bin/env python3
"""A searchable, visual guide to the keybinds loaded by Hyprland."""

import json
import subprocess
import sys

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, Gio, GLib, Gtk  # noqa: E402


APP_ID = "dev.eftear.hyprland.ShortcutGuide"

CATEGORIES = (
    ("All", "󰌌"),
    ("Essentials", ""),
    ("Apps & tools", "󰀻"),
    ("Windows", "󰖲"),
    ("Workspaces", "󰕰"),
    ("Layout", "󰕮"),
    ("Appearance", "󰏘"),
    ("System", ""),
    ("Media", "󰎈"),
    ("Screenshots", "󰄀"),
    ("Other", "󰘥"),
)

CATEGORY_ICONS = dict(CATEGORIES)

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

* {
  font-family: "JetBrainsMono Nerd Font", "Noto Sans";
  outline: none;
}

window, #root { background: @bg; color: @text; }

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

entry.search {
  min-height: 36px;
  min-width: 320px;
  padding: 0 14px;
  color: @text;
  caret-color: @cyan;
  background: #151d30;
  border: 1px solid @border;
  border-radius: 10px;
  box-shadow: none;
}

entry.search:focus { border-color: @cyan; box-shadow: 0 0 0 1px alpha(@cyan, .25); }

#sidebar {
  min-width: 205px;
  padding: 18px 12px;
  background: @panel;
  border-right: 1px solid @border;
}

.sidebar-title { margin: 2px 10px 12px; color: @muted; font-size: 10px; font-weight: 800; }

button.category {
  min-height: 38px;
  margin: 2px 0;
  padding: 0 11px;
  color: @muted;
  background: transparent;
  border: 0;
  border-radius: 9px;
  box-shadow: none;
}

button.category:hover { color: @text; background: @hover; }
button.category.active { color: @cyan; background: alpha(@cyan, .11); }
.category-icon { min-width: 24px; color: @violet; font-size: 15px; }
button.category.active .category-icon { color: @cyan; }
.category-name { font-size: 12px; font-weight: 700; }
.category-count { color: @muted; font-size: 10px; }

#content { background: @bg; }

#hero {
  margin: 18px 20px 8px;
  padding: 16px 18px;
  background: linear-gradient(115deg, alpha(@cyan, .11), alpha(@violet, .11));
  border: 1px solid alpha(@cyan, .25);
  border-radius: 13px;
}

.hero-title { color: @text; font-size: 16px; font-weight: 800; }
.hero-copy { margin-top: 3px; color: @muted; font-size: 11px; }
.live-dot { color: @green; font-size: 16px; }
.live-label { color: @green; font-size: 10px; font-weight: 800; }

#results-title { margin: 9px 22px 3px; color: @text; font-size: 14px; font-weight: 800; }
#results-meta { margin: 9px 22px 3px; color: @muted; font-size: 10px; }

flowbox { padding: 8px 14px 18px; background: @bg; }
flowboxchild { padding: 0; background: transparent; }

.shortcut-card {
  min-width: 385px;
  min-height: 92px;
  margin: 5px;
  padding: 13px 14px;
  color: @text;
  background: @card;
  border: 1px solid @border;
  border-radius: 12px;
}

.shortcut-card:hover { background: @hover; border-color: alpha(@cyan, .52); }
.card-action { color: @text; font-size: 12px; font-weight: 800; }
.card-detail { margin-top: 4px; color: @muted; font-size: 9px; }
.category-pill { color: @violet; font-size: 9px; font-weight: 800; }
.keycap {
  min-width: 23px;
  min-height: 25px;
  padding: 0 7px;
  color: @cyan;
  background: #0a1020;
  border: 1px solid #344566;
  border-radius: 6px;
  box-shadow: inset 0 -2px alpha(#000000, .48);
  font-size: 10px;
  font-weight: 800;
}
.plus { padding: 0 3px; color: #667390; font-size: 9px; }

#empty { margin: 70px; }
.empty-icon { color: @violet; font-size: 42px; }
.empty-title { margin-top: 12px; color: @text; font-size: 16px; font-weight: 800; }
.empty-copy { margin-top: 6px; color: @muted; font-size: 11px; }

#statusbar {
  min-height: 34px;
  padding: 0 20px;
  color: @muted;
  background: @panel;
  border-top: 1px solid @border;
  font-size: 10px;
}
.status-accent { color: @cyan; font-weight: 800; }

scrollbar slider { min-width: 6px; min-height: 32px; background: #34415d; border-radius: 9px; }
scrollbar trough { background: transparent; }
"""


KEYCODE_NAMES = {
    10: "1", 11: "2", 12: "3", 13: "4", 14: "5",
    15: "6", 16: "7", 17: "8", 18: "9", 19: "0",
}

KEY_NAMES = {
    "Return": "Enter",
    "SPACE": "Space",
    "tab": "Tab",
    "Print": "Print",
    "mouse_down": "Wheel ↓",
    "mouse_up": "Wheel ↑",
    "mouse:272": "Left Click",
    "mouse:273": "Right Click",
    "bracketleft": "[",
    "bracketright": "]",
    "period": ".",
    "comma": ",",
    "Super_L": "Super",
    "Super_R": "Super",
    "SHIFT_L": "Left Shift",
    "ALT_L": "Left Alt",
}

MODIFIERS = ((64, "Super"), (4, "Ctrl"), (8, "Alt"), (1, "Shift"))


def load_binds():
    try:
        result = subprocess.run(
            ["hyprctl", "binds", "-j"],
            check=True,
            capture_output=True,
            text=True,
            timeout=3,
        )
        raw_binds = json.loads(result.stdout)
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError) as error:
        raise RuntimeError("Could not read shortcuts from the running Hyprland session") from error

    binds = []
    seen = set()
    for bind in raw_binds:
        key = bind.get("key") or KEYCODE_NAMES.get(bind.get("keycode"), f"Key {bind.get('keycode', '?')}")
        key = KEY_NAMES.get(key, key)
        parts = [name for bit, name in MODIFIERS if bind.get("modmask", 0) & bit]
        if key not in parts:
            parts.append(key)

        action = bind.get("description", "").strip()
        if not action:
            action = describe_dispatcher(bind.get("dispatcher", ""), bind.get("arg", ""))
        action = action[:1].upper() + action[1:]

        category = classify(action, bind.get("dispatcher", ""), bind.get("arg", ""))
        item = {
            "keys": parts,
            "combo": " + ".join(parts),
            "action": action,
            "category": category,
            "detail": detail_for(bind),
            "essential": is_essential(action),
        }
        signature = (item["combo"], item["action"])
        if signature not in seen:
            binds.append(item)
            seen.add(signature)

    return sorted(binds, key=lambda item: (item["category"], item["action"].lower(), item["combo"]))


def describe_dispatcher(dispatcher, arg):
    names = {
        "killactive": "Close active window",
        "togglefloating": "Toggle floating window",
        "fullscreen": "Toggle fullscreen",
        "movefocus": "Move window focus",
        "movewindow": "Move active window",
        "resizeactive": "Resize active window",
        "workspace": "Switch workspace",
        "movetoworkspace": "Move window to workspace",
        "movetoworkspacesilent": "Move window silently",
        "cyclenext": "Cycle windows",
        "bringactivetotop": "Bring active window to top",
    }
    if dispatcher in names:
        return names[dispatcher]
    if dispatcher == "exec":
        command = arg.rsplit("/", 1)[-1].split()[0] if arg else "command"
        return f"Launch {command.removesuffix('.sh')}"
    return " ".join((dispatcher, arg)).strip().replace("_", " ") or "Hyprland action"


def detail_for(bind):
    dispatcher = bind.get("dispatcher", "").replace("_", " ")
    arg = bind.get("arg", "")
    if dispatcher == "exec":
        return "Launch command"
    if arg and len(arg) <= 26 and not arg.startswith("/"):
        return f"{dispatcher}  ·  {arg}"
    return dispatcher or "Hyprland"


def classify(action, dispatcher, arg):
    text = f"{action} {dispatcher} {arg}".lower()
    if any(word in text for word in ("screenshot", "grim", "swappy", "screen shot")):
        return "Screenshots"
    if any(word in text for word in ("volume", "audio", "media", "music", "player", "microphone", "mute")):
        return "Media"
    if "workspace" in text:
        return "Workspaces"
    if any(word in text for word in ("wallpaper", "theme", "blur", "opacity", "animation", "night light", "dark-light")):
        return "Appearance"
    if any(word in text for word in ("master", "layout", "split", "pseudo", "group")):
        return "Layout"
    if any(word in text for word in (
        "window", "fullscreen", "maximize", "floating", "resize", "movefocus",
        "movewindow", "swapwindow", "cyclenext", "bringactivetotop", "close active",
    )):
        return "Windows"
    if any(word in text for word in (
        "launcher", "terminal", "browser", "file manager", "search", "clipboard",
        "emoji", "calculator", "overview", "rofi", "app ",
    )):
        return "Apps & tools"
    if any(word in text for word in (
        "lock", "exit", "power", "sleep", "suspend", "brightness", "airplane",
        "monitor", "keyboard layout", "waybar", "notification", "touchpad", "refresh",
    )):
        return "System"
    return "Other"


def is_essential(action):
    text = action.lower()
    return any(word in text for word in (
        "app launcher", "open terminal", "file manager", "close active window",
        "desktop overview", "show or restore desktop", "lock screen", "help / cheat",
        "toggle special workspace", "move to special workspace", "window switcher",
    ))


class ShortcutGuide(Gtk.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.FLAGS_NONE)
        self.window = None
        self.binds = []
        self.category = "All"
        self.query = ""
        self.category_buttons = {}

    def do_startup(self):
        Gtk.Application.do_startup(self)
        provider = Gtk.CssProvider()
        provider.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

    def do_activate(self):
        if self.window:
            self.window.present()
            return

        try:
            self.binds = load_binds()
        except RuntimeError as error:
            self.binds = []
            GLib.idle_add(self.show_error, str(error))

        self.window = Gtk.ApplicationWindow(application=self)
        self.window.set_title("Hyprland Shortcut Guide")
        self.window.set_default_size(1160, 760)
        self.window.set_size_request(900, 580)
        self.window.set_position(Gtk.WindowPosition.CENTER)
        self.window.connect("key-press-event", self.on_key_press)

        header = Gtk.HeaderBar()
        header.set_show_close_button(True)
        header.props.title = "SHORTCUT COMMAND CENTER"
        header.props.subtitle = "Your live Hyprland keymap"
        self.search = Gtk.SearchEntry()
        self.search.get_style_context().add_class("search")
        self.search.set_placeholder_text("Search shortcuts or actions…   Ctrl+F")
        self.search.connect("search-changed", self.on_search)
        header.pack_end(self.search)
        self.window.set_titlebar(header)

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        root.set_name("root")
        body = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        root.pack_start(body, True, True, 0)

        sidebar = self.build_sidebar()
        body.pack_start(sidebar, False, False, 0)

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        content.set_name("content")
        body.pack_start(content, True, True, 0)
        content.pack_start(self.build_hero(), False, False, 0)

        title_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self.results_title = Gtk.Label(label="All shortcuts", xalign=0)
        self.results_title.set_name("results-title")
        self.results_meta = Gtk.Label(xalign=1)
        self.results_meta.set_name("results-meta")
        title_row.pack_start(self.results_title, True, True, 0)
        title_row.pack_end(self.results_meta, False, False, 0)
        content.pack_start(title_row, False, False, 0)

        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self.stack.set_transition_duration(140)

        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.flow = Gtk.FlowBox()
        self.flow.set_selection_mode(Gtk.SelectionMode.NONE)
        self.flow.set_homogeneous(True)
        self.flow.set_min_children_per_line(1)
        self.flow.set_max_children_per_line(2)
        self.flow.set_row_spacing(1)
        self.flow.set_column_spacing(1)
        scroll.add(self.flow)
        self.stack.add_named(scroll, "results")
        self.stack.add_named(self.build_empty(), "empty")
        content.pack_start(self.stack, True, True, 0)

        status = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        status.set_name("statusbar")
        self.status_label = Gtk.Label(label="Click any shortcut card to copy it", xalign=0)
        hint = Gtk.Label(label="ESC  close     CTRL+F  search", xalign=1)
        hint.get_style_context().add_class("status-accent")
        status.pack_start(self.status_label, True, True, 0)
        status.pack_end(hint, False, False, 0)
        root.pack_end(status, False, False, 0)

        self.window.add(root)
        self.refresh_results()
        self.window.show_all()

    def build_sidebar(self):
        sidebar = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        sidebar.set_name("sidebar")
        label = Gtk.Label(label="BROWSE BY CATEGORY", xalign=0)
        label.get_style_context().add_class("sidebar-title")
        sidebar.pack_start(label, False, False, 0)

        for name, icon in CATEGORIES:
            count = self.count_for(name)
            button = Gtk.Button()
            button.get_style_context().add_class("category")
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=7)
            icon_label = Gtk.Label(label=icon)
            icon_label.get_style_context().add_class("category-icon")
            name_label = Gtk.Label(label=name, xalign=0)
            name_label.get_style_context().add_class("category-name")
            count_label = Gtk.Label(label=str(count), xalign=1)
            count_label.get_style_context().add_class("category-count")
            row.pack_start(icon_label, False, False, 0)
            row.pack_start(name_label, True, True, 0)
            row.pack_end(count_label, False, False, 0)
            button.add(row)
            button.connect("clicked", self.on_category, name)
            sidebar.pack_start(button, False, False, 0)
            self.category_buttons[name] = button

        self.category_buttons["All"].get_style_context().add_class("active")
        return sidebar

    def build_hero(self):
        hero = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=14)
        hero.set_name("hero")
        icon = Gtk.Label(label="󰌌")
        icon.set_markup("<span size='26000' foreground='#5ee7f7'>󰌌</span>")
        copy = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        title = Gtk.Label(label="Find the command before you forget it", xalign=0)
        title.get_style_context().add_class("hero-title")
        subtitle = Gtk.Label(
            label="Search by action, key, or category. The guide refreshes from your live Hyprland session.",
            xalign=0,
        )
        subtitle.get_style_context().add_class("hero-copy")
        copy.pack_start(title, False, False, 0)
        copy.pack_start(subtitle, False, False, 0)
        live = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
        dot = Gtk.Label(label="●")
        dot.get_style_context().add_class("live-dot")
        live_text = Gtk.Label(label=f"LIVE  ·  {len(self.binds)} BINDS")
        live_text.get_style_context().add_class("live-label")
        live.pack_start(dot, False, False, 0)
        live.pack_start(live_text, False, False, 0)
        hero.pack_start(icon, False, False, 0)
        hero.pack_start(copy, True, True, 0)
        hero.pack_end(live, False, False, 0)
        return hero

    @staticmethod
    def build_empty():
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box.set_name("empty")
        box.set_valign(Gtk.Align.CENTER)
        icon = Gtk.Label(label="󰍉")
        icon.get_style_context().add_class("empty-icon")
        title = Gtk.Label(label="No matching shortcuts")
        title.get_style_context().add_class("empty-title")
        copy = Gtk.Label(label="Try another search or choose a different category.")
        copy.get_style_context().add_class("empty-copy")
        box.pack_start(icon, False, False, 0)
        box.pack_start(title, False, False, 0)
        box.pack_start(copy, False, False, 0)
        return box

    def count_for(self, category):
        if category == "All":
            return len(self.binds)
        if category == "Essentials":
            return sum(item["essential"] for item in self.binds)
        return sum(item["category"] == category for item in self.binds)

    def on_category(self, _button, category):
        self.category = category
        for name, button in self.category_buttons.items():
            context = button.get_style_context()
            (context.add_class if name == category else context.remove_class)("active")
        self.refresh_results()

    def on_search(self, entry):
        self.query = entry.get_text().strip().lower()
        self.refresh_results()

    def matching_binds(self):
        results = []
        for item in self.binds:
            category_match = (
                self.category == "All"
                or (self.category == "Essentials" and item["essential"])
                or item["category"] == self.category
            )
            haystack = f"{item['combo']} {item['action']} {item['category']} {item['detail']}".lower()
            if category_match and (not self.query or self.query in haystack):
                results.append(item)
        return results

    def refresh_results(self):
        for child in self.flow.get_children():
            self.flow.remove(child)

        results = self.matching_binds()
        self.results_title.set_text("Search results" if self.query else f"{self.category} shortcuts")
        self.results_meta.set_text(f"{len(results)} shown")
        self.status_label.set_text(f"{len(results)} shortcuts  ·  Click a card to copy its key combination")

        for item in results:
            self.flow.add(self.build_card(item))

        self.stack.set_visible_child_name("results" if results else "empty")
        self.flow.show_all()

    def build_card(self, item):
        card = Gtk.EventBox()
        card.set_visible_window(True)
        card.set_size_request(385, 92)
        card.get_style_context().add_class("shortcut-card")
        card.set_tooltip_text(f"Click to copy {item['combo']}")
        card.connect("button-release-event", self.copy_shortcut, item)

        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        pill = Gtk.Label(
            label=f"{CATEGORY_ICONS.get(item['category'], '•')}  {item['category'].upper()}", xalign=0
        )
        pill.get_style_context().add_class("category-pill")
        action = Gtk.Label(label=item["action"], xalign=0)
        action.set_line_wrap(True)
        action.set_max_width_chars(36)
        action.get_style_context().add_class("card-action")
        detail = Gtk.Label(label=item["detail"].upper(), xalign=0)
        detail.get_style_context().add_class("card-detail")
        text.pack_start(pill, False, False, 0)
        text.pack_start(action, False, False, 2)
        text.pack_start(detail, False, False, 0)

        keys = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        keys.set_valign(Gtk.Align.CENTER)
        for index, key in enumerate(item["keys"]):
            if index:
                plus = Gtk.Label(label="+")
                plus.get_style_context().add_class("plus")
                keys.pack_start(plus, False, False, 0)
            keycap = Gtk.Label(label=key)
            keycap.get_style_context().add_class("keycap")
            keys.pack_start(keycap, False, False, 0)

        row.pack_start(text, True, True, 0)
        row.pack_end(keys, False, False, 0)
        card.add(row)
        return card

    def copy_shortcut(self, _widget, event, item):
        if event.button != 1:
            return False
        clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        clipboard.set_text(item["combo"], -1)
        clipboard.store()
        self.status_label.set_markup(
            f"<span foreground='#78f0c2'><b>Copied</b></span>  {GLib.markup_escape_text(item['combo'])}"
        )
        return True

    def on_key_press(self, _window, event):
        if event.keyval == Gdk.KEY_Escape:
            self.window.close()
            return True
        if event.keyval in (Gdk.KEY_f, Gdk.KEY_F) and event.state & Gdk.ModifierType.CONTROL_MASK:
            self.search.grab_focus()
            return True
        return False

    def show_error(self, message):
        dialog = Gtk.MessageDialog(
            transient_for=self.window,
            flags=Gtk.DialogFlags.MODAL,
            message_type=Gtk.MessageType.ERROR,
            buttons=Gtk.ButtonsType.CLOSE,
            text=message,
        )
        dialog.run()
        dialog.destroy()
        return False


if __name__ == "__main__":
    app = ShortcutGuide()
    sys.exit(app.run(sys.argv))
