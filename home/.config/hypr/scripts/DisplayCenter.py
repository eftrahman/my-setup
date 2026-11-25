#!/usr/bin/env python3
"""Display Center: arrange, scale, rotate, mirror and switch monitors on Hyprland.

Layouts are saved to ~/.config/hypr-local/displays.conf, which is machine-local
and never touched by dotfiles updates. Changes are tried first and revert by
themselves after 15 seconds unless confirmed (a detached watchdog does the
revert, so it works even if this window dies or ends up on a blank screen).
"""

import json
import math
import os
import re
import subprocess
import sys
import tempfile
import time

HYPR_LOCAL = os.path.expanduser("~/.config/hypr-local")
CONF = os.path.join(HYPR_LOCAL, "displays.conf")
TRIAL_SECONDS = 15
INTERNAL = ("eDP", "LVDS", "DSI")
ROTATIONS = (("0", "Normal"), ("1", "90°"), ("2", "180°"), ("3", "270°"))
HEADER = """# Display layout for THIS machine, written by Display Center (Super+Shift+P).
# Not part of the dotfiles repository, so updates never overwrite it.
"""


# ---- model (no GTK, so it can be tested on its own) -------------------------- #


def hyprctl(*args):
    try:
        result = subprocess.run(["hyprctl", *args], capture_output=True, text=True, timeout=5)
        return result.stdout
    except (OSError, subprocess.SubprocessError) as error:
        return f"error: {error}"


def scales_for(width, height):
    """Scales Hyprland accepts: multiples of 1/120 giving whole logical pixels."""
    return [k / 120 for k in range(60, 361)
            if width * 120 % k == 0 and height * 120 % k == 0]


class Mon:
    def __init__(self, data):
        self.name = data["name"]
        self.desc = data.get("description", "")
        self.model = data.get("model") or self.name
        self.enabled = not data.get("disabled", False)
        mirror = str(data.get("mirrorOf", "none"))
        self.mirror = None if mirror == "none" else mirror
        self.modes = list(dict.fromkeys(m.removesuffix("Hz") for m in data.get("availableModes", [])))
        self.width, self.height = data.get("width", 0), data.get("height", 0)
        self.mode = f"{self.width}x{self.height}@{data.get('refreshRate', 60):.2f}"
        if self.width <= 0 or self.height <= 0:  # disabled outputs may report no size
            self.mode = self.modes[0] if self.modes else "1920x1080@60.00"
            self.set_mode(self.mode)
        elif self.mode not in self.modes:
            self.modes.insert(0, self.mode)
        self.scale = self.exact_scale(data.get("scale", 1) or 1)
        self.transform = data.get("transform", 0)
        self.x, self.y = data.get("x", 0), data.get("y", 0)

    @property
    def internal(self):
        return self.name.startswith(INTERNAL)

    @property
    def title(self):
        return "Laptop screen" if self.internal else f"{self.model} ({self.name})"

    @property
    def active(self):
        return self.enabled and not self.mirror

    def set_mode(self, mode):
        self.mode = mode
        self.width, self.height = map(int, mode.split("@")[0].split("x"))

    def exact_scale(self, reported):
        """hyprctl rounds the scale to two decimals; recover the exact value."""
        return min(scales_for(self.width, self.height), key=lambda s: abs(s - reported))

    def size(self):
        w, h = round(self.width / self.scale), round(self.height / self.scale)
        return (h, w) if self.transform % 2 else (w, h)

    def rect(self):
        return (self.x, self.y, *self.size())

    def rule(self, ident):
        if not self.enabled:
            return f"{ident},disable"
        if self.mirror:
            return f"{ident},{self.mode},auto,1,mirror,{self.mirror}"
        scale = f"{self.scale:.6f}".rstrip("0").rstrip(".")
        return f"{ident},{self.mode},{self.x}x{self.y},{scale},transform,{self.transform}"


def read_monitors():
    try:
        data = json.loads(hyprctl("-j", "monitors", "all"))
    except ValueError:
        return []
    mons = [Mon(d) for d in data if d["name"] not in ("FALLBACK",)]
    by_id = {str(d["id"]): d["name"] for d in data}
    for mon in mons:
        if mon.mirror:
            mon.mirror = by_id.get(mon.mirror, mon.mirror)
    return mons


def overlaps(a, b):
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    return ax < bx + bw and bx < ax + aw and ay < by + bh and by < ay + ah


def any_overlap(mons):
    act = [m for m in mons if m.active]
    return any(overlaps(a.rect(), b.rect()) for i, a in enumerate(act) for b in act[i + 1:])


def place(mon, anchor, side, ratio=0.5):
    """Put `mon` against a side of `anchor`; ratio .5 centres it on that side."""
    ax, ay, aw, ah = anchor.rect()
    w, h = mon.size()
    if side in ("above", "below"):
        mon.x = round(ax + (aw - w) * ratio)
        mon.y = ay - h if side == "above" else ay + ah
    else:
        mon.y = round(ay + (ah - h) * ratio)
        mon.x = ax - w if side == "left" else ax + aw


def side_of(mon, anchor):
    x, y, w, h = mon.rect()
    ax, ay, aw, ah = anchor.rect()
    gaps = {"above": ay - (y + h), "below": y - (ay + ah), "left": ax - (x + w), "right": x - (ax + aw)}
    return max(gaps, key=gaps.get)


def snap(mon, others, tolerance=90):
    """Attach a dropped monitor to the closest free edge, aligning nearby edges."""
    x, y, w, h = mon.rect()
    best = None
    for other in others:
        ox, oy, ow, oh = other.rect()
        for side in ("above", "below", "left", "right"):
            horizontal = side in ("above", "below")
            pos, size, opos, osize = (x, w, ox, ow) if horizontal else (y, h, oy, oh)
            keep = min(size, osize) // 4  # always share enough edge for the cursor
            pos = max(opos - size + keep, min(pos, opos + osize - keep))
            for target in (opos, round(opos + (osize - size) / 2), opos + osize - size):
                if abs(pos - target) <= tolerance:
                    pos = target
                    break
            if horizontal:
                cand = (pos, oy - h if side == "above" else oy + oh)
            else:
                cand = (ox - w if side == "left" else ox + ow, pos)
            if any(overlaps((*cand, w, h), o.rect()) for o in others):
                continue
            distance = math.hypot(cand[0] - x, cand[1] - y)
            if best is None or distance < best[0]:
                best = (distance, cand)
    if best:
        mon.x, mon.y = best[1]


def normalize(mons):
    act = [m for m in mons if m.active]
    if act:
        dx, dy = min(m.x for m in act), min(m.y for m in act)
        for m in act:
            m.x, m.y = m.x - dx, m.y - dy


def batch(mons):
    # enabled outputs first, mirrors next, disables last: never zero screens
    ordered = sorted(mons, key=lambda m: (not m.enabled, bool(m.mirror)))
    return " ; ".join(f"keyword monitor {m.rule(m.name)}" for m in ordered)


def config_ident(mon, mons):
    """Match by description so the layout survives a different port."""
    usable = mon.desc and not re.search(r"[,#$]", mon.desc)
    if mon.internal or not usable or sum(m.desc == mon.desc for m in mons) > 1:
        return mon.name
    return f"desc:{mon.desc}"


def save(mons):
    os.makedirs(HYPR_LOCAL, exist_ok=True)
    saved = [m for m in mons if m.enabled or not m.internal]  # a panel that is off keeps its old rule
    idents = {m.name for m in saved} | {f"desc:{m.desc}" for m in saved}
    kept = []
    try:
        with open(CONF, encoding="utf-8") as handle:
            for line in handle:
                match = re.match(r"\s*monitor\s*=\s*([^,]*),", line)
                # remember rules of monitors that are not plugged in right now
                if match and match.group(1).strip() and match.group(1).strip() not in idents:
                    kept.append(line.strip())
    except OSError:
        pass
    lines = []
    for mon in sorted(mons, key=lambda m: (not m.enabled, bool(m.mirror))):
        if mon.internal and not mon.enabled:
            continue  # never saved: unplugging would leave the laptop with no screen
        lines.append(f"monitor = {mon.rule(config_ident(mon, mons))}")
    handle, path = tempfile.mkstemp(dir=HYPR_LOCAL)
    with os.fdopen(handle, "w", encoding="utf-8") as out:
        out.write(HEADER + "\n".join(kept + lines) + "\n")
    os.chmod(path, 0o644)
    os.replace(path, CONF)


def guard():
    """While the laptop panel is off, bring it back if every external goes away."""
    time.sleep(3)
    while True:
        try:
            data = json.loads(hyprctl("-j", "monitors", "all"))
        except ValueError:
            return 0
        panels = [m for m in data if m["name"].startswith(INTERNAL)]
        if not panels or not any(m.get("disabled") for m in panels):
            return 0
        if not any(not m.get("disabled") and m["name"] != "FALLBACK" for m in data):
            for panel in panels:
                hyprctl("keyword", "monitor", f"{panel['name']},preferred,auto,1")
            return 0
        time.sleep(2)


if "--guard" in sys.argv[1:]:
    sys.exit(guard())

import gi  # noqa: E402

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_foreign("cairo")
from gi.repository import Gdk, Gio, GLib, Gtk, Pango  # noqa: E402

CSS = b"""
* { font-family: "JetBrainsMono Nerd Font", "Noto Sans"; outline: none; }
window, dialog, dialog box, #root { background: #080b16; color: #e5ecff; }
headerbar { min-height: 58px; padding: 6px 12px; background: #0d1220; border: 0; border-bottom: 1px solid #26334f; box-shadow: none; }
headerbar .title { color: #e5ecff; font-size: 17px; font-weight: 800; }
headerbar .subtitle { color: #8794b3; font-size: 11px; }
#bar, #bottom { padding: 10px 18px; background: #0d1220; }
#bar { border-bottom: 1px solid #26334f; }
#bottom { border-top: 1px solid #26334f; }
#panel { padding: 14px 18px; background: #0d1220; border-top: 1px solid #26334f; }
.caption { color: #8794b3; font-size: 10px; font-weight: 800; }
.name { font-size: 14px; font-weight: 800; }
.hint { color: #8794b3; font-size: 10px; }
.count { color: #5ee7f7; font-size: 26px; font-weight: 800; }
button { min-height: 34px; padding: 0 13px; color: #e5ecff; background: #111827; border: 1px solid #26334f; border-radius: 9px; box-shadow: none; text-shadow: none; font-size: 11px; font-weight: 700; }
button:hover { background: #18243a; border-color: #5ee7f7; }
button.primary { color: #061014; background: #5ee7f7; border-color: #5ee7f7; }
button:disabled { opacity: .38; }
checkbutton { color: #e5ecff; font-size: 11px; }
"""


def label(text, css="", wrap=False):
    widget = Gtk.Label(label=text, xalign=0)
    widget.set_line_wrap(wrap)
    if not wrap:
        widget.set_ellipsize(Pango.EllipsizeMode.END)
    if css:
        widget.get_style_context().add_class(css)
    return widget


def button(text, callback, primary=False, tooltip=None):
    widget = Gtk.Button(label=text)
    if primary:
        widget.get_style_context().add_class("primary")
    widget.set_tooltip_text(tooltip)
    widget.connect("clicked", lambda *_: callback())
    return widget


class DisplayCenter(Gtk.Application):
    def __init__(self):
        super().__init__(application_id="dev.eftear.hyprland.DisplayCenter", flags=Gio.ApplicationFlags.FLAGS_NONE)
        self.window = None
        self.mons, self.selected, self.drag = [], None, None
        self.loading = self.trial = self.dirty = False
        self.view = (1, 0, 0)

    def do_startup(self):
        Gtk.Application.do_startup(self)
        provider = Gtk.CssProvider()
        provider.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

    def do_activate(self):
        if self.window:
            self.window.present()
            return
        self.build()
        self.load()
        self.window.show_all()
        GLib.timeout_add_seconds(2, self.poll)

    def build(self):
        self.window = Gtk.ApplicationWindow(application=self, title="Display Center")
        self.window.set_default_size(980, 680)
        self.window.connect("key-press-event", self.on_key)
        header = Gtk.HeaderBar(show_close_button=True)
        header.props.title = "DISPLAY CENTER"
        self.header = header
        self.window.set_titlebar(header)
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        root.set_name("root")

        bar = Gtk.Box(spacing=8)
        bar.set_name("bar")
        bar.pack_start(label("QUICK MODE", "caption"), False, False, 4)
        self.mode_buttons = []
        for text, mode in (("󰍺  Extend", "extend"), ("󰍹  Mirror", "mirror"),
                           ("󰌢  Laptop only", "internal"), ("󰍹  External only", "external")):
            widget = button(text, lambda m=mode: self.quick(m))
            self.mode_buttons.append((mode, widget))
            bar.pack_start(widget, False, False, 0)
        self.place_box = Gtk.Box(spacing=8)
        self.place_label = label("", "caption")
        self.place_box.pack_start(self.place_label, False, False, 0)
        for text, side in (("󰁝 Above", "above"), ("󰁅 Below", "below"), ("󰁍 Left", "left"), ("󰁔 Right", "right")):
            self.place_box.pack_start(button(text, lambda s=side: self.place_selected(s)), False, False, 0)
        root.pack_start(bar, False, False, 0)

        self.canvas = Gtk.DrawingArea()
        self.canvas.add_events(Gdk.EventMask.BUTTON_PRESS_MASK | Gdk.EventMask.BUTTON_RELEASE_MASK
                               | Gdk.EventMask.POINTER_MOTION_MASK)
        for signal, handler in (("draw", self.on_draw), ("button-press-event", self.on_press),
                                ("motion-notify-event", self.on_motion), ("button-release-event", self.on_release)):
            self.canvas.connect(signal, handler)
        root.pack_start(self.canvas, True, True, 0)

        panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        panel.set_name("panel")
        top = Gtk.Box(spacing=10)
        self.name_label = label("", "name")
        top.pack_start(self.name_label, True, True, 0)
        top.pack_end(self.place_box, False, False, 0)
        panel.pack_start(top, False, False, 0)
        row = Gtk.Box(spacing=10)
        self.enabled = Gtk.CheckButton(label="On")
        self.enabled.connect("toggled", self.on_enabled)
        row.pack_start(self.enabled, False, False, 0)
        self.combos = {}
        for key, text in (("mode", "Resolution"), ("scale", "Scale"), ("transform", "Rotation")):
            row.pack_start(label(text, "caption"), False, False, 0)
            combo = Gtk.ComboBoxText()
            combo.connect("changed", self.on_combo, key)
            self.combos[key] = combo
            row.pack_start(combo, False, False, 0)
        panel.pack_start(row, False, False, 0)
        root.pack_start(panel, False, False, 0)

        bottom = Gtk.Box(spacing=10)
        bottom.set_name("bottom")
        self.status = label("", "hint")
        bottom.pack_start(self.status, True, True, 0)
        self.apply_button = button("Apply", self.apply, primary=True, tooltip="Ctrl+Enter")
        bottom.pack_end(self.apply_button, False, False, 0)
        bottom.pack_end(button("Reset", self.load, tooltip="Discard changes (F5)"), False, False, 0)
        root.pack_start(bottom, False, False, 0)
        self.window.add(root)

    # ---- state ------------------------------------------------------------- #

    def load(self):
        keep = self.selected.name if self.selected else None
        self.mons = read_monitors()
        self.dirty = False
        self.drag = None
        external = [m for m in self.mons if not m.internal]
        self.selected = next((m for m in self.mons if m.name == keep), None) or \
            (external or self.mons or [None])[0]
        self.refresh()

    def poll(self):
        if not self.window:
            return False
        if not self.trial and not self.drag:
            names = {m.name for m in read_monitors()}
            if names and names != {m.name for m in self.mons}:
                self.load()
        return True

    def anchor_for(self, mon):
        others = [m for m in self.mons if m.active and m is not mon]
        return next((m for m in others if m.internal), others[0] if others else None)

    def changed(self):
        self.dirty = True
        self.refresh()

    def refresh(self):
        self.loading = True
        mon = self.selected
        has_panel = any(m.internal for m in self.mons)
        external = any(not m.internal for m in self.mons)
        for mode, widget in self.mode_buttons:
            widget.set_visible(True)
            widget.set_no_show_all(False)
            widget.set_sensitive({"extend": len(self.mons) > 1, "mirror": len(self.mons) > 1,
                                  "internal": has_panel and external, "external": has_panel and external}[mode])
        if mon:
            state = "" if mon.active else ("  •  off" if not mon.enabled else f"  •  mirrors {mon.mirror}")
            self.name_label.set_text(f"{mon.title}{state}")
            self.enabled.set_active(mon.enabled)
            choices = {
                "mode": [(m, f"{m.split('@')[0].replace('x', ' × ')}  {float(m.split('@')[1]):.0f} Hz") for m in mon.modes],
                "scale": [(f"{s:.6f}", f"{s * 100:.0f}%") for s in scales_for(mon.width, mon.height)],
                "transform": [*ROTATIONS, *([(str(mon.transform), "Flipped")] if mon.transform > 3 else [])],
            }
            active = {"mode": mon.mode, "scale": f"{mon.scale:.6f}", "transform": str(mon.transform)}
            for key, combo in self.combos.items():
                combo.remove_all()
                for ident, text in choices[key]:
                    combo.append(ident, text)
                combo.set_active_id(active[key])
                combo.set_sensitive(mon.active)
            anchor = self.anchor_for(mon)
            self.place_box.set_sensitive(bool(anchor) and mon.active)
            self.place_label.set_text(f"Place relative to {anchor.title}" if anchor else "")
        bad = any_overlap(self.mons)
        usable = any(m.active for m in self.mons)
        self.apply_button.set_sensitive(self.dirty and usable and not bad and not self.trial)
        self.header.props.subtitle = "  •  ".join(
            f"{m.name} {m.width}×{m.height}" + ("" if m.enabled else " off") for m in self.mons) or "No displays"
        if bad:
            self.status.set_text("Screens overlap — move them apart")
        elif not usable:
            self.status.set_text("At least one screen must stay on")
        elif self.dirty:
            self.status.set_text(f"Not applied yet — Apply tries it for {TRIAL_SECONDS} seconds first")
        else:
            self.status.set_text("Drag screens to match your desk  •  F5 reset  •  Esc close")
        self.canvas.queue_draw()
        self.loading = False

    # ---- edits ------------------------------------------------------------- #

    def resize(self, mon, change):
        """Run a size-changing edit, then re-attach screens to the same sides."""
        anchor = self.anchor_for(mon)
        moving = []
        if anchor and mon.active:
            if mon.internal or anchor.internal is False and mon.x == 0 and mon.y == 0:
                moving = [(o, mon, side_of(o, mon)) for o in self.mons if o.active and o is not mon]
            else:
                moving = [(mon, anchor, side_of(mon, anchor))]
        change()
        for item, ref, side in moving:
            place(item, ref, side)
            others = [m for m in self.mons if m.active and m is not item]
            if any(overlaps(item.rect(), o.rect()) for o in others):
                snap(item, others)
        self.changed()

    def on_combo(self, combo, key):
        value, mon = combo.get_active_id(), self.selected
        if self.loading or not value or not mon:
            return

        def change():
            if key == "mode":
                mon.set_mode(value)
                mon.scale = mon.exact_scale(mon.scale)
            elif key == "scale":
                mon.scale = float(value)
                mon.scale = mon.exact_scale(mon.scale)
            else:
                mon.transform = int(value)

        self.resize(mon, change)

    def turn_on(self, mon):
        mon.enabled, mon.mirror = True, None
        others = [m for m in self.mons if m.active and m is not mon]
        if any(overlaps(mon.rect(), o.rect()) for o in others):
            place(mon, self.anchor_for(mon), "above" if not mon.internal else "below")
            snap(mon, others)

    def on_enabled(self, check):
        if self.loading or not self.selected:
            return
        mon = self.selected
        if check.get_active():
            self.turn_on(mon)
        else:
            mon.enabled = False
            for other in self.mons:
                if other.mirror == mon.name:
                    self.turn_on(other)
        self.changed()

    def place_selected(self, side):
        mon = self.selected
        anchor = self.anchor_for(mon) if mon else None
        if anchor:
            place(mon, anchor, side)
            self.changed()

    def quick(self, mode):
        panel = next((m for m in self.mons if m.internal), None)
        if mode == "extend":
            for mon in sorted(self.mons, key=lambda m: not m.internal):
                if not mon.active:
                    self.turn_on(mon)
        elif mode == "mirror":
            source = panel or self.mons[0]
            source.enabled, source.mirror = True, None
            for mon in self.mons:
                if mon is not source:
                    mon.enabled, mon.mirror = True, source.name
        elif mode in ("internal", "external"):
            want = mode == "internal"
            for mon in self.mons:
                mon.mirror = None
                mon.enabled = mon.internal == want
            for mon in self.mons:
                if mon.enabled:
                    self.turn_on(mon)
        self.changed()

    # ---- canvas ------------------------------------------------------------ #

    def on_draw(self, area, cr):
        width, height = area.get_allocated_width(), area.get_allocated_height()
        act = [m for m in self.mons if m.active]
        if act and not self.drag:
            left, top = min(m.x for m in act), min(m.y for m in act)
            right = max(m.x + m.size()[0] for m in act)
            low = max(m.y + m.size()[1] for m in act)
            zoom = min((width - 120) / (right - left), (height - 80) / (low - top), 0.22)
            zoom = max(zoom, 0.02)
            self.view = (zoom, (width - (right - left) * zoom) / 2 - left * zoom,
                         (height - (low - top) * zoom) / 2 - top * zoom)
        zoom, ox, oy = self.view
        for mon in act:
            x, y, w, h = mon.rect()
            x, y, w, h = x * zoom + ox, y * zoom + oy, w * zoom, h * zoom
            chosen = mon is self.selected
            cr.rectangle(x + 1, y + 1, w - 2, h - 2)
            cr.set_source_rgb(*((0.07, 0.17, 0.22) if chosen else (0.07, 0.1, 0.165)))
            cr.fill_preserve()
            cr.set_source_rgb(*((0.37, 0.91, 0.97) if chosen else (0.35, 0.43, 0.6)))
            cr.set_line_width(2)
            cr.stroke()
            for index, (text, size) in enumerate(((mon.title, 13), (f"{mon.width}×{mon.height}", 11),
                                                  (f"{mon.scale * 100:.0f}%  at {mon.x},{mon.y}", 10))):
                cr.select_font_face("Noto Sans")
                cr.set_font_size(size)
                while len(text) > 3 and cr.text_extents(text).width > w - 12:
                    text = text[:-1]
                extents = cr.text_extents(text)
                cr.move_to(x + (w - extents.width) / 2, y + h / 2 - 12 + index * 18)
                cr.set_source_rgb(0.9, 0.93, 1)
                cr.show_text(text)
        idle = [m for m in self.mons if not m.active]
        cr.set_font_size(11)
        for index, mon in enumerate(idle):
            cr.move_to(16, height - 16 - index * 18)
            cr.set_source_rgb(0.53, 0.58, 0.7)
            cr.show_text(f"{mon.title}: " + ("off" if not mon.enabled else f"mirrors {mon.mirror}") + "  (click to select)")
        return False

    def on_press(self, area, event):
        zoom, ox, oy = self.view
        x, y = (event.x - ox) / zoom, (event.y - oy) / zoom
        for mon in reversed([m for m in self.mons if m.active]):
            mx, my, mw, mh = mon.rect()
            if mx <= x < mx + mw and my <= y < my + mh:
                self.selected = mon
                if event.button == 1 and sum(m.active for m in self.mons) > 1:
                    self.drag = (mon, x - mx, y - my, mx, my)
                self.refresh()
                return True
        idle = [m for m in self.mons if not m.active]
        index = int((area.get_allocated_height() - event.y - 8) // 18)
        if 0 <= index < len(idle):
            self.selected = idle[index]
            self.refresh()
        return True

    def on_motion(self, _area, event):
        if self.drag:
            zoom, ox, oy = self.view
            mon, dx, dy, *_ = self.drag
            mon.x, mon.y = round((event.x - ox) / zoom - dx), round((event.y - oy) / zoom - dy)
            self.canvas.queue_draw()
        return False

    def on_release(self, _area, _event):
        if self.drag:
            mon, _dx, _dy, x, y = self.drag
            self.drag = None
            if (mon.x, mon.y) != (x, y):
                snap(mon, [m for m in self.mons if m.active and m is not mon])
                self.dirty = True
            self.refresh()
        return False

    def on_key(self, _window, event):
        if event.keyval == Gdk.KEY_Escape:
            self.window.close()
        elif event.keyval == Gdk.KEY_F5:
            self.load()
        elif event.keyval == Gdk.KEY_Return and event.state & Gdk.ModifierType.CONTROL_MASK:
            if self.apply_button.get_sensitive():
                self.apply()
        else:
            return False
        return True

    # ---- apply / revert ----------------------------------------------------- #


    def apply(self):
        previous = batch(read_monitors())
        normalize(self.mons)
        wanted = batch(self.mons)
        handle, marker = tempfile.mkstemp(prefix="display-trial-", dir=os.environ.get("XDG_RUNTIME_DIR"))
        os.close(handle)
        # detached: reverts even if this process dies
        subprocess.Popen(
            ["sh", "-c", f'sleep {TRIAL_SECONDS + 1}; [ -e "$1" ] || exit 0; rm -f "$1"; hyprctl --batch "$2"',
             "display-revert", marker, previous],
            start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.trial = True
        out = hyprctl("--batch", wanted)
        errors = [line for line in out.splitlines() if line.strip() and line.strip() != "ok"]
        if errors:
            self.finish(marker, previous, False, f"Hyprland refused it: {errors[0]}")
            return
        GLib.timeout_add(700, lambda: self.ask(marker, previous))

    def ask(self, marker, previous):
        dialog = Gtk.Dialog(transient_for=self.window, modal=True, title="Keep this layout?")
        dialog.add_button("Revert", Gtk.ResponseType.CANCEL)
        keep = dialog.add_button("Keep layout", Gtk.ResponseType.OK)
        keep.get_style_context().add_class("primary")
        dialog.set_default_response(Gtk.ResponseType.CANCEL)
        box = dialog.get_content_area()
        box.set_spacing(10)
        box.set_border_width(18)
        box.pack_start(label("Keep this display layout?", "name"), False, False, 0)
        count = label("", "count")
        box.pack_start(count, False, False, 0)
        box.pack_start(label("It goes back by itself if you do nothing.", "hint"), False, False, 0)
        deadline = time.monotonic() + TRIAL_SECONDS - 1
        alive = [True]

        def tick():
            if not alive[0]:
                return False
            left = deadline - time.monotonic()
            if left <= 0:
                dialog.response(Gtk.ResponseType.CANCEL)
                return False
            count.set_text(f"{math.ceil(left)} s")
            return True

        tick()
        GLib.timeout_add(250, tick)
        dialog.show_all()
        response = dialog.run()
        alive[0] = False
        dialog.destroy()
        self.finish(marker, previous, response == Gtk.ResponseType.OK)
        return False

    def finish(self, marker, previous, keep, message=None):
        # If the watchdog already fired, the old layout is back: do not save.
        try:
            os.unlink(marker)
        except FileNotFoundError:
            keep = False
        if keep:
            panel_off = any(m.internal and not m.enabled for m in self.mons)
            # Saving makes Hyprland reload, which re-enables a panel that is
            # (deliberately) not saved as off, so re-apply that part afterwards.
            wanted = batch(self.mons)
            try:
                save(self.mons)
                message = "Layout saved for this machine"
            except OSError as error:
                message = f"Applied, but saving failed: {error}"
            if panel_off:
                hyprctl("reload")
                hyprctl("--batch", wanted)
                subprocess.Popen([sys.executable, os.path.abspath(__file__), "--guard"], start_new_session=True)
                message = "External only until you log out, reload, or unplug it"
        else:
            hyprctl("--batch", previous)
            message = message or "Reverted to the previous layout"
        self.trial = False
        GLib.timeout_add(600, lambda: self.after(message))

    def after(self, message):
        if self.window:
            self.load()
            self.status.set_text(message)
        return False


if __name__ == "__main__":
    sys.exit(DisplayCenter().run(sys.argv))
