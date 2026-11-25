#!/usr/bin/env python3
"""Workspace Overview for Hyprland (Super+A).

Every workspace is drawn as a miniature of its monitor with windows at their
real positions. Workspaces currently on screen use a live snapshot; the rest
show the wallpaper with app icons.

  click window        focus it (switches workspace)
  click empty space   go to that workspace
  drag window         move it to another workspace
  middle-click        close window
  right-click         window menu
  type                search windows; Enter focuses the first match
  1-9                 go to workspace (when the search box is empty)
  Esc / Super+A       close
"""

import json
import os
import subprocess
import sys

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
try:
    gi.require_foreign("cairo")
except ImportError:
    print("WorkspaceOverview: python3-gi-cairo is required", file=sys.stderr)
    subprocess.run(["notify-send", "Overview", "Install python3-gi-cairo to use the overview"])
    sys.exit(1)
from gi.repository import Gdk, GdkPixbuf, Gio, GLib, Gtk, Pango  # noqa: E402

CARD_WIDTH = 330
MIN_WORKSPACES = 5
WALLPAPER = os.path.expanduser("~/.config/hypr/wallpaper_effects/.wallpaper_current")

CSS = b"""
@define-color bg #080b16;
@define-color panel #0d1220;
@define-color card #12192a;
@define-color border #26334f;
@define-color text #e5ecff;
@define-color muted #8794b3;
@define-color cyan #5ee7f7;
@define-color violet #b991ff;
@define-color green #78f0c2;

* { font-family: "JetBrainsMono Nerd Font", "Noto Sans"; outline: none; }
window, #root { background: alpha(@bg, .96); color: @text; }
#top { padding: 16px 24px 8px; }
.title { color: @text; font-size: 16px; font-weight: 800; }
.hint { color: @muted; font-size: 9px; }
entry {
  min-height: 38px; min-width: 380px; padding: 0 14px; color: @text; caret-color: @cyan;
  background: #151d30; border: 1px solid @border; border-radius: 11px; box-shadow: none;
}
entry:focus { border-color: @cyan; }
flowbox { padding: 10px 20px 20px; }
flowboxchild { padding: 0; }
.ws-card { padding: 10px; background: @card; border: 2px solid @border; border-radius: 14px; }
.ws-card.current { border-color: alpha(@cyan, .75); }
.ws-card.drop { border-color: @violet; background: #1b1830; }
.ws-card.dim { opacity: .35; }
.ws-name { color: @text; font-size: 12px; font-weight: 800; }
.ws-meta { color: @muted; font-size: 9px; }
.badge { padding: 1px 7px; border-radius: 8px; font-size: 8px; font-weight: 800; color: @green; background: alpha(@green, .12); }
.badge.mon { color: @violet; background: alpha(@violet, .12); }
"""


def hyprctl(*args):
    try:
        return subprocess.run(["hyprctl", *args], capture_output=True, text=True, timeout=3).stdout
    except (OSError, subprocess.SubprocessError):
        return ""


def hypr_json(what):
    try:
        return json.loads(hyprctl("-j", what) or "[]")
    except ValueError:
        return []


def dispatch(*args):
    hyprctl("dispatch", *args)


def grab_output(name):
    """Snapshot one monitor (taken before our window maps, so it is not in it)."""
    try:
        data = subprocess.run(["grim", "-t", "ppm", "-s", "0.5", "-o", name, "-"],
                              capture_output=True, timeout=4).stdout
        loader = GdkPixbuf.PixbufLoader()
        loader.write(data)
        loader.close()
        return loader.get_pixbuf()
    except (OSError, subprocess.SubprocessError, GLib.Error):
        return None


def rounded(cr, x, y, w, h, r):
    r = max(0, min(r, w / 2, h / 2))
    cr.new_sub_path()
    cr.arc(x + w - r, y + r, r, -1.5708, 0)
    cr.arc(x + w - r, y + h - r, r, 0, 1.5708)
    cr.arc(x + r, y + h - r, r, 1.5708, 3.1416)
    cr.arc(x + r, y + r, r, 3.1416, 4.7124)
    cr.close_path()


class IconCache:
    def __init__(self):
        self.theme = Gtk.IconTheme.get_default()
        self.cache = {}

    def get(self, app_class, size):
        key = (app_class, size)
        if key in self.cache:
            return self.cache[key]
        pixbuf = None
        names = [app_class, app_class.lower(), app_class.split(".")[-1].lower()]
        info = Gio.DesktopAppInfo.new(f"{app_class}.desktop") if app_class else None
        if info is None and app_class:
            matches = Gio.DesktopAppInfo.search(app_class)
            if matches and matches[0]:
                info = Gio.DesktopAppInfo.new(matches[0][0])
        if info and info.get_icon():
            names.insert(0, info.get_icon().to_string())
        for name in names + ["application-x-executable"]:
            try:
                if name and name.startswith("/") and os.path.exists(name):
                    pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(name, size, size)
                elif name and self.theme.has_icon(name):
                    pixbuf = self.theme.load_icon(name, size, Gtk.IconLookupFlags.FORCE_SIZE)
            except GLib.Error:
                pixbuf = None
            if pixbuf:
                break
        self.cache[key] = pixbuf
        return pixbuf


class Overview(Gtk.Window):
    def __init__(self):
        super().__init__(title="Workspace Overview")
        self.set_default_size(1400, 860)
        self.connect("destroy", Gtk.main_quit)
        self.connect("key-press-event", self.on_key)
        self.icons = IconCache()
        self.query = ""
        self.press = None
        self.drop_card = None

        self.monitors = hypr_json("monitors")
        self.snapshots = {m["name"]: grab_output(m["name"]) for m in self.monitors}
        self.wallpaper = None
        try:
            self.wallpaper = GdkPixbuf.Pixbuf.new_from_file_at_scale(WALLPAPER, CARD_WIDTH * 2, -1, True)
        except GLib.Error:
            pass

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        root.set_name("root")
        top = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)
        top.set_name("top")
        title = Gtk.Label(label="󰕰  Overview", xalign=0)
        title.get_style_context().add_class("title")
        top.pack_start(title, False, False, 0)
        self.search = Gtk.SearchEntry(placeholder_text="Search windows…   Enter to focus")
        self.search.connect("search-changed", self.on_search)
        self.search.connect("activate", self.on_search_activate)
        top.pack_start(self.search, False, False, 0)
        hint = Gtk.Label(label="Click: go  •  Drag: move window  •  Middle-click: close  •  Right-click: menu  •  1-9: workspace  •  Esc: close",
                         xalign=1)
        hint.get_style_context().add_class("hint")
        hint.set_ellipsize(Pango.EllipsizeMode.START)
        top.pack_end(hint, True, True, 0)
        root.pack_start(top, False, False, 0)

        self.flow = Gtk.FlowBox()
        self.flow.set_selection_mode(Gtk.SelectionMode.NONE)
        self.flow.set_max_children_per_line(4)
        self.flow.set_min_children_per_line(2)
        self.flow.set_column_spacing(16)
        self.flow.set_row_spacing(16)
        self.flow.set_homogeneous(True)
        self.flow.set_valign(Gtk.Align.START)
        scroller = Gtk.ScrolledWindow()
        scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroller.add(self.flow)
        root.pack_start(scroller, True, True, 0)
        self.add(root)

        self.reload()
        self.show_all()
        self.search.grab_focus()

    # ---- data -------------------------------------------------------------- #

    def reload(self):
        self.clients = [c for c in hypr_json("clients")
                        if c.get("mapped", True) and c.get("pid") != os.getpid()
                        and c.get("workspace", {}).get("id", 0) != 0]
        self.workspaces = {w["id"]: w for w in hypr_json("workspaces")}
        self.monitors = hypr_json("monitors") or self.monitors
        active = hypr_json("activewindow")
        self.active_address = active.get("address") if isinstance(active, dict) else None
        focused = next((m for m in self.monitors if m.get("focused")), self.monitors[0] if self.monitors else None)
        self.current_ws = focused["activeWorkspace"]["id"] if focused else 1
        self.visible = {m["activeWorkspace"]["id"]: m for m in self.monitors}

        normal = [i for i in self.workspaces if i > 0]
        top = max([MIN_WORKSPACES, *normal])
        ids = list(range(1, top + 1))
        specials = sorted(i for i, w in self.workspaces.items() if i < 0 and w.get("windows"))
        for child in self.flow.get_children():
            self.flow.remove(child)
        self.cards = []
        for ws_id in ids + specials:
            card = self.build_card(ws_id)
            self.flow.add(card)
            self.cards.append(card)
        self.flow.show_all()
        self.apply_search()

    def monitor_for(self, ws_id):
        ws = self.workspaces.get(ws_id)
        name = ws.get("monitor") if ws else None
        monitor = next((m for m in self.monitors if m["name"] == name), None)
        return monitor or next((m for m in self.monitors if m.get("focused")), self.monitors[0])

    def windows_on(self, ws_id):
        wins = [c for c in self.clients if c["workspace"]["id"] == ws_id]
        # draw tiled first, then floating; most recently focused last (on top)
        return sorted(wins, key=lambda c: (c.get("floating", False), -c.get("focusHistoryID", 0)))

    # ---- cards ------------------------------------------------------------- #

    def build_card(self, ws_id):
        monitor = self.monitor_for(ws_id)
        ws = self.workspaces.get(ws_id, {})
        name = ws.get("name") or str(ws_id)
        if ws_id < 0:
            name = name.replace("special:", "★ ")
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        ctx = box.get_style_context()
        ctx.add_class("ws-card")
        if ws_id == self.current_ws:
            ctx.add_class("current")

        head = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        label = Gtk.Label(label=f"Workspace {name}" if ws_id > 0 else name, xalign=0)
        label.get_style_context().add_class("ws-name")
        head.pack_start(label, False, False, 0)
        count = len(self.windows_on(ws_id))
        meta = Gtk.Label(label=f"{count} window{'s' if count != 1 else ''}" if count else "empty", xalign=0)
        meta.get_style_context().add_class("ws-meta")
        head.pack_start(meta, False, False, 0)
        if ws_id in self.visible:
            badge = Gtk.Label(label=self.visible[ws_id]["name"])
            badge.get_style_context().add_class("badge")
            badge.get_style_context().add_class("mon")
            head.pack_end(badge, False, False, 0)
        if ws_id == self.current_ws:
            badge = Gtk.Label(label="CURRENT")
            badge.get_style_context().add_class("badge")
            head.pack_end(badge, False, False, 0)
        box.pack_start(head, False, False, 0)

        area = Gtk.DrawingArea()
        logical_w = monitor["width"] / monitor.get("scale", 1)
        logical_h = monitor["height"] / monitor.get("scale", 1)
        if monitor.get("transform", 0) % 2:
            logical_w, logical_h = logical_h, logical_w
        scale = CARD_WIDTH / logical_w
        area.set_size_request(CARD_WIDTH, int(logical_h * scale))
        area.add_events(Gdk.EventMask.BUTTON_PRESS_MASK | Gdk.EventMask.BUTTON_RELEASE_MASK
                        | Gdk.EventMask.POINTER_MOTION_MASK | Gdk.EventMask.LEAVE_NOTIFY_MASK)
        area.ws_id, area.monitor, area.hover = ws_id, monitor, None
        area.logical = (logical_w, logical_h)
        area.scale, area.offset = scale, (0.0, 0.0)
        area.connect("draw", self.on_draw)
        area.connect("button-press-event", self.on_press)
        area.connect("motion-notify-event", self.on_motion)
        area.connect("button-release-event", self.on_release)
        area.connect("leave-notify-event", lambda a, _e: (setattr(a, "hover", None), a.queue_draw()))
        box.pack_start(area, False, False, 0)
        box.area, box.ws_id = area, ws_id
        return box

    def window_rect(self, area, client):
        m, s = area.monitor, area.scale
        ox, oy = area.offset
        x = ox + (client["at"][0] - m["x"]) * s
        y = oy + (client["at"][1] - m["y"]) * s
        return x, y, client["size"][0] * s, client["size"][1] * s

    def hit(self, area, x, y):
        for client in reversed(self.windows_on(area.ws_id)):
            wx, wy, ww, wh = self.window_rect(area, client)
            if wx <= x <= wx + ww and wy <= y <= wy + wh:
                return client
        return None

    def matches(self, client):
        q = self.query
        return not q or q in client.get("title", "").lower() or q in client.get("class", "").lower()

    def on_draw(self, area, cr):
        alloc_w, alloc_h = area.get_allocated_width(), area.get_allocated_height()
        logical_w, logical_h = area.logical
        area.scale = min(alloc_w / logical_w, alloc_h / logical_h)
        width, height = logical_w * area.scale, logical_h * area.scale
        area.offset = ((alloc_w - width) / 2, (alloc_h - height) / 2)
        cr.translate(*area.offset)
        rounded(cr, 0, 0, width, height, 9)
        cr.clip()
        cr.translate(-area.offset[0], -area.offset[1])
        ox, oy = area.offset
        live = area.ws_id in self.visible and self.visible[area.ws_id]["name"] == area.monitor["name"]
        background = self.snapshots.get(area.monitor["name"]) if live else self.wallpaper
        if background:
            scaled = background.scale_simple(int(width), int(height), GdkPixbuf.InterpType.BILINEAR)
            Gdk.cairo_set_source_pixbuf(cr, scaled, ox, oy)
            cr.paint()
            if not live:
                cr.set_source_rgba(0.03, 0.04, 0.09, 0.55)
                cr.paint()
        else:
            cr.set_source_rgb(0.05, 0.07, 0.13)
            cr.paint()

        dragging = self.press and self.press.get("dragging")
        for client in self.windows_on(area.ws_id):
            x, y, w, h = self.window_rect(area, client)
            is_dragged = dragging and self.press["client"]["address"] == client["address"]
            dim = (self.query and not self.matches(client)) or is_dragged
            if not live:
                rounded(cr, x + 1, y + 1, w - 2, h - 2, 5)
                cr.set_source_rgba(0.09, 0.12, 0.2, 0.92)
                cr.fill()
            if dim:
                rounded(cr, x + 1, y + 1, w - 2, h - 2, 5)
                cr.set_source_rgba(0.02, 0.03, 0.07, 0.7)
                cr.fill()
            icon_size = int(max(16, min(40, w * 0.35, h * 0.45)))
            if not live or w > 60:
                icon = self.icons.get(client.get("class", ""), icon_size)
                if icon and h > icon_size + 4 and not live:
                    Gdk.cairo_set_source_pixbuf(cr, icon, x + (w - icon_size) / 2, y + (h - icon_size) / 2 - (6 if h > 60 else 0))
                    cr.paint_with_alpha(0.35 if dim else 1)
            if not live and h > 60 and w > 70:
                cr.select_font_face("Noto Sans")
                cr.set_font_size(9)
                title = client.get("title") or client.get("class", "")
                while title and cr.text_extents(title).width > w - 12:
                    title = title[:-2]
                cr.move_to(x + 6, y + h - 8)
                cr.set_source_rgba(0.9, 0.93, 1, 0.45 if dim else 0.9)
                cr.show_text(title)
            highlighted = client["address"] == area.hover or (self.query and self.matches(client))
            active = client["address"] == self.active_address
            if highlighted or active:
                rounded(cr, x + 1, y + 1, w - 2, h - 2, 5)
                cr.set_line_width(2.2)
                if highlighted:
                    cr.set_source_rgb(0.72, 0.57, 1.0)
                else:
                    cr.set_source_rgb(0.37, 0.9, 0.97)
                cr.stroke()
            elif not live:
                rounded(cr, x + 1, y + 1, w - 2, h - 2, 5)
                cr.set_line_width(1)
                cr.set_source_rgba(0.6, 0.68, 0.85, 0.35)
                cr.stroke()
        if not self.windows_on(area.ws_id):
            cr.select_font_face("Noto Sans")
            cr.set_font_size(11)
            text = "empty  •  click to open"
            ext = cr.text_extents(text)
            cr.move_to(ox + (width - ext.width) / 2, oy + (height + ext.height) / 2)
            cr.set_source_rgba(0.53, 0.58, 0.7, 0.9)
            cr.show_text(text)
        return False

    # ---- mouse ------------------------------------------------------------- #

    def on_press(self, area, event):
        client = self.hit(area, event.x, event.y)
        if event.button == 3 and client:
            self.window_menu(client, event)
            return True
        if event.button == 2 and client:
            dispatch("closewindow", f"address:{client['address']}")
            GLib.timeout_add(350, lambda: (self.reload(), False)[1])
            return True
        if event.button == 1:
            self.press = {"area": area, "client": client, "x": event.x, "y": event.y, "dragging": False}
        return True

    def on_motion(self, area, event):
        if self.press and self.press["client"] and self.press["area"] is area:
            if not self.press["dragging"] and abs(event.x - self.press["x"]) + abs(event.y - self.press["y"]) > 8:
                self.press["dragging"] = True
                area.get_window().set_cursor(Gdk.Cursor.new_from_name(area.get_display(), "grabbing"))
            if self.press["dragging"]:
                self.set_drop_card(self.card_at(area, event.x, event.y))
                for card in self.cards:
                    card.area.queue_draw()
            return True
        client = self.hit(area, event.x, event.y)
        address = client["address"] if client else None
        if address != area.hover:
            area.hover = address
            area.set_tooltip_text(f"{client['title']}\n{client['class']}" if client else None)
            area.queue_draw()
        return False

    def on_release(self, area, event):
        press, self.press = self.press, None
        if not press or event.button != 1:
            return False
        area.get_window().set_cursor(None)
        self.set_drop_card(None)
        if press["dragging"]:
            target = self.card_at(area, event.x, event.y)
            client = press["client"]
            if target and target.ws_id != client["workspace"]["id"]:
                ws = target.ws_id if target.ws_id > 0 else self.workspaces[target.ws_id]["name"]
                dispatch("movetoworkspacesilent", f"{ws},address:{client['address']}")
                GLib.timeout_add(150, lambda: (self.reload(), False)[1])
            else:
                for card in self.cards:
                    card.area.queue_draw()
            return True
        if press["client"]:
            self.focus(press["client"])
        else:
            self.goto(area.ws_id)
        return True

    def card_at(self, source, x, y):
        top = self.get_toplevel()
        tx, ty = source.translate_coordinates(top, int(x), int(y))
        for card in self.cards:
            coords = top.translate_coordinates(card, tx, ty)
            if coords:
                cx, cy = coords
                alloc = card.get_allocation()
                if 0 <= cx < alloc.width and 0 <= cy < alloc.height:
                    return card
        return None

    def set_drop_card(self, card):
        if self.drop_card is card:
            return
        if self.drop_card:
            self.drop_card.get_style_context().remove_class("drop")
        self.drop_card = card
        if card and self.press and card.ws_id != self.press["client"]["workspace"]["id"]:
            card.get_style_context().add_class("drop")

    def window_menu(self, client, event):
        menu = Gtk.Menu()

        def item(text, callback):
            entry = Gtk.MenuItem(label=text)
            entry.connect("activate", lambda *_: callback())
            menu.append(entry)
            return entry

        item("Focus", lambda: self.focus(client))
        move = Gtk.MenuItem(label="Move to workspace")
        sub = Gtk.Menu()
        for card in self.cards:
            if card.ws_id == client["workspace"]["id"]:
                continue
            ws = card.ws_id if card.ws_id > 0 else self.workspaces[card.ws_id]["name"]
            label = str(card.ws_id) if card.ws_id > 0 else str(ws).replace("special:", "★ ")
            entry = Gtk.MenuItem(label=label)
            entry.connect("activate", lambda _e, w=ws: (dispatch("movetoworkspacesilent", f"{w},address:{client['address']}"),
                                                        GLib.timeout_add(150, lambda: (self.reload(), False)[1])))
            sub.append(entry)
        new = Gtk.MenuItem(label="New empty workspace")
        new.connect("activate", lambda *_: (dispatch("movetoworkspacesilent", f"emptynm,address:{client['address']}"),
                                            GLib.timeout_add(150, lambda: (self.reload(), False)[1])))
        sub.append(new)
        move.set_submenu(sub)
        menu.append(move)
        item("Toggle floating", lambda: (dispatch("togglefloating", f"address:{client['address']}"),
                                         GLib.timeout_add(150, lambda: (self.reload(), False)[1])))
        menu.append(Gtk.SeparatorMenuItem())
        item("Close window", lambda: (dispatch("closewindow", f"address:{client['address']}"),
                                      GLib.timeout_add(350, lambda: (self.reload(), False)[1])))
        menu.show_all()
        menu.popup_at_pointer(event)

    # ---- actions ----------------------------------------------------------- #

    def close_then(self, batch):
        """Exit first, act after. When the overview process ends, Hyprland hands focus
        back to the previously focused window; dispatching only after we are gone
        keeps the user's choice from being overridden."""
        script = ('for i in $(seq 60); do kill -0 "$PARENT" 2>/dev/null || break; sleep 0.05; done; '
                  'sleep 0.1; exec hyprctl --batch "$1"')
        env = dict(os.environ, PARENT=str(os.getpid()))
        subprocess.Popen(["sh", "-c", script, "overview-dispatch", batch],
                         env=env, start_new_session=True,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.destroy()

    def focus(self, client):
        # focus follows the mouse here, so also park the cursor on the chosen window;
        # otherwise the next tiny mouse movement re-focuses whatever was under it.
        cx = client["at"][0] + client["size"][0] // 2
        cy = client["at"][1] + client["size"][1] // 2
        self.close_then(f"dispatch focuswindow address:{client['address']}; dispatch movecursor {cx} {cy}")

    def goto(self, ws_id):
        if ws_id > 0:
            self.close_then(f"dispatch workspace {ws_id}")
        else:
            self.close_then(f"dispatch togglespecialworkspace {self.workspaces[ws_id]['name'].replace('special:', '')}")

    def on_search(self, entry):
        self.query = entry.get_text().strip().lower()
        self.apply_search()

    def apply_search(self):
        for card in self.cards:
            wins = self.windows_on(card.ws_id)
            ctx = card.get_style_context()
            if self.query and not any(self.matches(c) for c in wins):
                ctx.add_class("dim")
            else:
                ctx.remove_class("dim")
            card.area.queue_draw()

    def on_search_activate(self, _entry):
        if not self.query:
            return
        for card in self.cards:
            for client in reversed(self.windows_on(card.ws_id)):
                if self.matches(client):
                    self.focus(client)
                    return

    def on_key(self, _widget, event):
        if event.keyval == Gdk.KEY_Escape:
            if self.search.get_text():
                self.search.set_text("")
            else:
                self.destroy()
            return True
        if not self.search.get_text() and Gdk.KEY_1 <= event.keyval <= Gdk.KEY_9:
            self.goto(event.keyval - Gdk.KEY_0)
            return True
        return False


def main():
    provider = Gtk.CssProvider()
    provider.load_from_data(CSS)
    Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), provider,
                                             Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
    Overview()
    Gtk.main()


if __name__ == "__main__":
    main()
