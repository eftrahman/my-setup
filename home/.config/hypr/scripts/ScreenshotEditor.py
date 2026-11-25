#!/usr/bin/env python3
"""Screenshot Editor: annotate, crop, copy, and save screenshots on Hyprland.

Usage: ScreenshotEditor.py IMAGE.png

Tools: pen, highlighter, arrow, line, rectangle, ellipse, text, numbered
steps, pixelate (hide secrets), crop. Everything is undoable. "Done" copies
the result to the clipboard, saves it over the screenshot, and closes.

If the Python cairo bindings are missing, swappy is opened instead.
"""

import io
import math
import os
import shutil
import subprocess
import sys

TOOLS = (
    ("pen", "󰏫", "Pen", "P"),
    ("highlight", "󰸱", "Highlighter", "H"),
    ("arrow", "󰁜", "Arrow", "A"),
    ("line", "󰕞", "Line", "L"),
    ("rect", "󰝤", "Rectangle", "R"),
    ("ellipse", "󰺡", "Ellipse", "E"),
    ("text", "󰊄", "Text", "T"),
    ("step", "󰲠", "Numbered step", "N"),
    ("blur", "󰂵", "Pixelate (hide secrets)", "B"),
    ("crop", "󰆞", "Crop", "C"),
)
COLORS = ("#ff4d6d", "#ffb020", "#3ddc84", "#2fb6ff", "#b991ff", "#ffffff", "#111111")
SIZES = (("S", 3), ("M", 6), ("L", 11))


def fallback(path, reason):
    print(f"ScreenshotEditor: {reason}; opening swappy", file=sys.stderr)
    swappy = shutil.which("swappy")
    if swappy and path:
        os.execv(swappy, [swappy, "-f", path])
    sys.exit(1)


IMAGE_PATH = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else None
if not IMAGE_PATH or not os.path.isfile(IMAGE_PATH):
    print("usage: ScreenshotEditor.py IMAGE.png", file=sys.stderr)
    sys.exit(2)

try:
    import cairo
    import gi

    gi.require_version("Gtk", "3.0")
    gi.require_version("Gdk", "3.0")
    gi.require_foreign("cairo")
    from gi.repository import Gdk, GLib, Gtk
except (ImportError, ValueError) as error:
    fallback(IMAGE_PATH, f"missing dependency ({error})")


CSS = b"""
@define-color bg #080b16;
@define-color panel #0d1220;
@define-color panel2 #111827;
@define-color hover #18243a;
@define-color border #26334f;
@define-color text #e5ecff;
@define-color muted #8794b3;
@define-color cyan #5ee7f7;
@define-color green #78f0c2;

* { font-family: "JetBrainsMono Nerd Font", "Noto Sans"; outline: none; }
window, #root { background: @bg; color: @text; }
headerbar { min-height: 52px; padding: 4px 12px; background: @panel; border: 0; border-bottom: 1px solid @border; box-shadow: none; }
headerbar .title { color: @text; font-size: 15px; font-weight: 800; }
headerbar .subtitle { color: @muted; font-size: 10px; }

#toolbar { padding: 8px 14px; background: @panel; border-bottom: 1px solid @border; }
.group-label { margin: 0 6px 0 12px; color: @muted; font-size: 9px; font-weight: 800; }
button.tool, button.size, button.action {
  min-height: 34px; min-width: 34px; padding: 0 8px; margin: 0 2px;
  color: @muted; background: @panel2; border: 1px solid @border; border-radius: 9px; box-shadow: none;
  font-size: 15px;
}
button.size, button.action { font-size: 11px; font-weight: 800; }
button.tool:hover, button.size:hover, button.action:hover { color: @text; background: @hover; border-color: alpha(@cyan, .45); }
button.tool:checked, button.size:checked { color: @cyan; background: alpha(@cyan, .13); border-color: @cyan; }
button.swatch { min-width: 22px; min-height: 22px; padding: 0; margin: 0 2px; border: 2px solid @border; border-radius: 12px; box-shadow: none; }
button.swatch:checked { border-color: @text; box-shadow: 0 0 0 2px alpha(@cyan, .6); }
button.action.primary { color: #061014; background: @cyan; border-color: @cyan; }
button.action.primary:hover { background: #93f2fb; }
button:disabled { opacity: .35; }

#canvas-wrap { background: #05070f; }
#statusbar { min-height: 30px; padding: 0 16px; color: @muted; background: @panel; border-top: 1px solid @border; font-size: 9px; }
popover, popover entry { background: @panel; color: @text; }
popover entry { min-height: 34px; min-width: 260px; border: 1px solid @cyan; border-radius: 8px; padding: 0 10px; background: #151d30; }
"""


def hex_rgb(color):
    color = color.lstrip("#")
    return tuple(int(color[i:i + 2], 16) / 255 for i in (0, 2, 4))


def normalized(p1, p2):
    x1, y1 = p1
    x2, y2 = p2
    return min(x1, x2), min(y1, y2), abs(x2 - x1), abs(y2 - y1)


def contrast(color):
    r, g, b = hex_rgb(color)
    return (0.05, 0.06, 0.1) if (0.299 * r + 0.587 * g + 0.114 * b) > 0.6 else (1, 1, 1)


class Editor(Gtk.Window):
    def __init__(self, path):
        super().__init__(title="Screenshot Editor")
        self.path = path
        self.base = cairo.ImageSurface.create_from_png(path)
        self.img_w, self.img_h = self.base.get_width(), self.base.get_height()
        self.shapes = []
        self.crop = (0, 0, self.img_w, self.img_h)
        self.undo_stack, self.redo_stack = [], []
        self.tool, self.color, self.size = "arrow", COLORS[0], SIZES[1][1]
        self.drag = None
        self.view = (1.0, 0.0, 0.0)  # scale, offset x, offset y
        self.dirty = False
        self.tool_buttons = {}

        self.set_default_size(1280, 820)
        self.connect("delete-event", self.on_delete)
        self.connect("key-press-event", self.on_key)

        header = Gtk.HeaderBar()
        header.set_show_close_button(True)
        header.props.title = "SCREENSHOT EDITOR"
        header.props.subtitle = f"{os.path.basename(path)}  •  {self.img_w}×{self.img_h}"
        self.header = header
        done = self.action_button("󰄬  Done", "Copy to clipboard, save, and close (Enter)", self.on_done, primary=True)
        save = self.action_button("󰆓  Save", "Save over the screenshot (Ctrl+S)", lambda *_: self.save())
        save_as = self.action_button("Save as…", "Save a copy elsewhere (Ctrl+Shift+S)", lambda *_: self.save_as())
        copy = self.action_button("󰆏  Copy", "Copy image to clipboard (Ctrl+C)", lambda *_: self.copy())
        for widget in (done, save, save_as, copy):
            header.pack_end(widget)
        self.set_titlebar(header)

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        root.set_name("root")
        root.pack_start(self.build_toolbar(), False, False, 0)

        self.canvas = Gtk.DrawingArea()
        self.canvas.set_name("canvas-wrap")
        self.canvas.set_can_focus(True)
        self.canvas.add_events(
            Gdk.EventMask.BUTTON_PRESS_MASK | Gdk.EventMask.BUTTON_RELEASE_MASK
            | Gdk.EventMask.POINTER_MOTION_MASK
        )
        self.canvas.connect("draw", self.on_draw)
        self.canvas.connect("button-press-event", self.on_press)
        self.canvas.connect("motion-notify-event", self.on_motion)
        self.canvas.connect("button-release-event", self.on_release)
        self.canvas.connect("realize", lambda w: w.get_window().set_cursor(
            Gdk.Cursor.new_from_name(w.get_display(), "crosshair")))
        root.pack_start(self.canvas, True, True, 0)

        status = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        status.set_name("statusbar")
        self.status_label = Gtk.Label(xalign=0)
        status.pack_start(self.status_label, True, True, 0)
        status.pack_end(Gtk.Label(label="Ctrl+Z undo  •  Ctrl+Shift+Z redo  •  Shift = straight / square  •  Esc close"), False, False, 0)
        root.pack_start(status, False, False, 0)
        self.add(root)

        self.text_popover = Gtk.Popover(relative_to=self.canvas)
        self.text_entry = Gtk.Entry(placeholder_text="Type, then Enter")
        self.text_entry.connect("activate", self.on_text_entered)
        self.text_popover.add(self.text_entry)
        self.text_point = None

        self.select_tool("arrow")
        self.update_buttons()
        self.show_all()
        self.canvas.grab_focus()

    # ---- toolbar ---------------------------------------------------------- #

    def action_button(self, text, tooltip, callback, primary=False):
        button = Gtk.Button(label=text)
        button.get_style_context().add_class("action")
        if primary:
            button.get_style_context().add_class("primary")
        button.set_tooltip_text(tooltip)
        button.set_valign(Gtk.Align.CENTER)
        button.connect("clicked", callback)
        return button

    def build_toolbar(self):
        bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        bar.set_name("toolbar")
        bar.pack_start(self.group_label("TOOLS"), False, False, 0)
        group = None
        for key, icon, name, shortcut in TOOLS:
            button = Gtk.RadioButton.new_with_label_from_widget(group, icon)
            group = group or button
            button.set_mode(False)
            button.get_style_context().add_class("tool")
            button.set_tooltip_text(f"{name}  ({shortcut})")
            button.connect("toggled", lambda b, k=key: b.get_active() and self.select_tool(k))
            bar.pack_start(button, False, False, 0)
            self.tool_buttons[key] = button

        bar.pack_start(self.group_label("COLOR"), False, False, 0)
        group = None
        provider = Gtk.CssProvider()
        provider.load_from_data("".join(
            f"button.swatch.c{i} {{ background: {c}; }}" for i, c in enumerate(COLORS)).encode())
        for index, color in enumerate(COLORS):
            button = Gtk.RadioButton.new_from_widget(group)
            group = group or button
            button.set_mode(False)
            ctx = button.get_style_context()
            ctx.add_provider(provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 1)
            for name in ("swatch", f"c{index}"):
                ctx.add_class(name)
            button.set_valign(Gtk.Align.CENTER)
            button.set_tooltip_text(f"{color}  ({index + 1})")
            button.connect("toggled", lambda b, c=color: b.get_active() and self.set_color(c))
            bar.pack_start(button, False, False, 0)
            if index == 0:
                self.first_swatch = button
        self.swatches = group.get_group()[::-1]

        bar.pack_start(self.group_label("SIZE"), False, False, 0)
        group = None
        self.size_buttons = []
        for name, value in SIZES:
            button = Gtk.RadioButton.new_with_label_from_widget(group, name)
            group = group or button
            button.set_mode(False)
            button.get_style_context().add_class("size")
            button.set_tooltip_text(f"Stroke / text size {name}  ([ and ])")
            button.connect("toggled", lambda b, v=value: b.get_active() and self.set_size(v))
            bar.pack_start(button, False, False, 0)
            self.size_buttons.append(button)
        self.size_buttons[1].set_active(True)

        self.redo_button = self.action_button("󰑏", "Redo (Ctrl+Shift+Z)", lambda *_: self.redo())
        self.undo_button = self.action_button("󰕌", "Undo (Ctrl+Z)", lambda *_: self.undo())
        self.reset_button = self.action_button("Reset", "Remove all edits", lambda *_: self.reset())
        for widget in (self.redo_button, self.undo_button, self.reset_button):
            bar.pack_end(widget, False, False, 0)
        return bar

    @staticmethod
    def group_label(text):
        widget = Gtk.Label(label=text)
        widget.get_style_context().add_class("group-label")
        return widget

    def select_tool(self, key):
        self.tool = key
        if not self.tool_buttons[key].get_active():
            self.tool_buttons[key].set_active(True)
        hints = {
            "pen": "Draw freehand",
            "highlight": "Drag across text to highlight it",
            "arrow": "Drag from tail to tip  •  Shift snaps to 45°",
            "line": "Drag a straight line  •  Shift snaps to 45°",
            "rect": "Drag a box  •  Shift for a square",
            "ellipse": "Drag an ellipse  •  Shift for a circle",
            "text": "Click where the text should start",
            "step": f"Click to drop step {self.next_step()}",
            "blur": "Drag over passwords, emails, or anything private",
            "crop": "Drag the area to keep (undo restores it)",
        }
        self.set_status(hints.get(key, ""))

    def set_color(self, color):
        self.color = color

    def set_size(self, value):
        self.size = value

    def set_status(self, text, color=None):
        if color:
            self.status_label.set_markup(f"<span foreground='{color}'><b>{GLib.markup_escape_text(text)}</b></span>")
        else:
            self.status_label.set_text(text)

    def update_buttons(self):
        self.undo_button.set_sensitive(bool(self.undo_stack))
        self.redo_button.set_sensitive(bool(self.redo_stack))
        self.reset_button.set_sensitive(bool(self.shapes) or self.crop != (0, 0, self.img_w, self.img_h))
        name = os.path.basename(self.path)
        self.header.props.subtitle = f"{name}{'  •  edited' if self.dirty else ''}  •  {self.crop[2]}×{self.crop[3]}"

    # ---- history ---------------------------------------------------------- #

    def snapshot(self):
        self.undo_stack.append((list(self.shapes), self.crop))
        self.redo_stack.clear()
        self.dirty = True

    def undo(self):
        if not self.undo_stack:
            return
        self.redo_stack.append((list(self.shapes), self.crop))
        self.shapes, self.crop = self.undo_stack.pop()
        self.dirty = True
        self.after_change()

    def redo(self):
        if not self.redo_stack:
            return
        self.undo_stack.append((list(self.shapes), self.crop))
        self.shapes, self.crop = self.redo_stack.pop()
        self.dirty = True
        self.after_change()

    def reset(self):
        self.snapshot()
        self.shapes, self.crop = [], (0, 0, self.img_w, self.img_h)
        self.after_change()

    def add_shape(self, shape):
        self.snapshot()
        self.shapes.append(shape)
        self.after_change()

    def after_change(self):
        self.update_buttons()
        if self.tool == "step":
            self.select_tool("step")
        self.canvas.queue_draw()

    def next_step(self):
        return 1 + sum(1 for s in self.shapes if s["kind"] == "step")

    # ---- geometry --------------------------------------------------------- #

    def to_image(self, wx, wy):
        scale, ox, oy = self.view
        cx, cy, cw, ch = self.crop
        x = (wx - ox) / scale + cx
        y = (wy - oy) / scale + cy
        return (min(max(x, cx), cx + cw), min(max(y, cy), cy + ch))

    def to_widget(self, ix, iy):
        scale, ox, oy = self.view
        cx, cy, _, _ = self.crop
        return (ix - cx) * scale + ox, (iy - cy) * scale + oy

    @staticmethod
    def constrain(kind, p1, p2):
        """Shift modifier: 45° snapping for lines, squares/circles for boxes."""
        dx, dy = p2[0] - p1[0], p2[1] - p1[1]
        if kind in ("arrow", "line"):
            angle = round(math.atan2(dy, dx) / (math.pi / 4)) * (math.pi / 4)
            length = math.hypot(dx, dy)
            return (p1[0] + length * math.cos(angle), p1[1] + length * math.sin(angle))
        side = max(abs(dx), abs(dy))
        return (p1[0] + math.copysign(side, dx or 1), p1[1] + math.copysign(side, dy or 1))

    # ---- input ------------------------------------------------------------ #

    def on_press(self, _widget, event):
        if event.button != 1:
            return False
        self.canvas.grab_focus()
        point = self.to_image(event.x, event.y)
        if self.tool == "text":
            self.text_point = point
            rect = Gdk.Rectangle()
            rect.x, rect.y, rect.width, rect.height = int(event.x), int(event.y), 1, 1
            self.text_popover.set_pointing_to(rect)
            self.text_entry.set_text("")
            self.text_popover.show_all()
            self.text_entry.grab_focus()
            return True
        if self.tool == "step":
            self.add_shape({"kind": "step", "p": point, "n": self.next_step(), "color": self.color, "size": self.size})
            return True
        self.drag = {"kind": self.tool, "p1": point, "p2": point, "points": [point],
                     "color": self.color, "size": self.size}
        return True

    def on_motion(self, _widget, event):
        if not self.drag:
            return False
        point = self.to_image(event.x, event.y)
        if self.drag["kind"] in ("pen", "highlight"):
            last = self.drag["points"][-1]
            if math.hypot(point[0] - last[0], point[1] - last[1]) >= 1.5:
                self.drag["points"].append(point)
        elif event.state & Gdk.ModifierType.SHIFT_MASK and self.drag["kind"] in ("arrow", "line", "rect", "ellipse"):
            point = self.constrain(self.drag["kind"], self.drag["p1"], point)
        self.drag["p2"] = point
        self.canvas.queue_draw()
        return True

    def on_release(self, _widget, event):
        if event.button != 1 or not self.drag:
            return False
        shape, self.drag = self.drag, None
        x, y, w, h = normalized(shape["p1"], shape["p2"])
        kind = shape["kind"]
        if kind in ("pen", "highlight"):
            if len(shape["points"]) == 1:
                shape["points"].append((shape["points"][0][0] + 0.5, shape["points"][0][1] + 0.5))
            self.add_shape(shape)
        elif kind == "crop":
            if w >= 8 and h >= 8:
                self.snapshot()
                self.crop = (int(x), int(y), int(round(w)), int(round(h)))
                self.after_change()
                self.set_status(f"Cropped to {self.crop[2]}×{self.crop[3]}  •  Ctrl+Z to undo", "#78f0c2")
            else:
                self.canvas.queue_draw()
        elif w >= 3 or h >= 3:
            self.add_shape(shape)
        else:
            self.canvas.queue_draw()
        return True

    def on_text_entered(self, entry):
        text = entry.get_text().strip()
        self.text_popover.popdown()
        if text and self.text_point:
            self.add_shape({"kind": "text", "p": self.text_point, "text": text, "color": self.color, "size": self.size})
        self.canvas.grab_focus()

    def on_key(self, _widget, event):
        if self.text_popover.get_visible():
            if event.keyval == Gdk.KEY_Escape:
                self.text_popover.popdown()
                return True
            return False
        ctrl = bool(event.state & Gdk.ModifierType.CONTROL_MASK)
        shift = bool(event.state & Gdk.ModifierType.SHIFT_MASK)
        key = Gdk.keyval_to_lower(event.keyval)
        if ctrl:
            if key == Gdk.KEY_z:
                self.redo() if shift else self.undo()
            elif key == Gdk.KEY_y:
                self.redo()
            elif key == Gdk.KEY_c:
                self.copy()
            elif key == Gdk.KEY_s:
                self.save_as() if shift else self.save()
            else:
                return False
            return True
        if event.keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            self.on_done()
            return True
        if event.keyval == Gdk.KEY_Escape:
            self.close()
            return True
        if Gdk.KEY_1 <= event.keyval <= Gdk.KEY_7:
            self.swatches[event.keyval - Gdk.KEY_1].set_active(True)
            return True
        if event.keyval in (Gdk.KEY_bracketleft, Gdk.KEY_bracketright):
            index = next(i for i, b in enumerate(self.size_buttons) if b.get_active())
            index = max(0, min(len(SIZES) - 1, index + (1 if event.keyval == Gdk.KEY_bracketright else -1)))
            self.size_buttons[index].set_active(True)
            return True
        for tool, _icon, _name, shortcut in TOOLS:
            if key == Gdk.unicode_to_keyval(ord(shortcut.lower())):
                self.select_tool(tool)
                return True
        return False

    # ---- rendering -------------------------------------------------------- #

    def on_draw(self, widget, cr):
        width, height = widget.get_allocated_width(), widget.get_allocated_height()
        cr.set_source_rgb(0.02, 0.027, 0.06)
        cr.paint()
        cx, cy, cw, ch = self.crop
        pad = 28
        scale = min(1.0, (width - 2 * pad) / cw, (height - 2 * pad) / ch)
        scale = max(scale, 0.05)
        ox, oy = (width - cw * scale) / 2, (height - ch * scale) / 2
        self.view = (scale, ox, oy)

        # drop shadow + image frame
        cr.set_source_rgba(0, 0, 0, 0.45)
        cr.rectangle(ox + 6, oy + 8, cw * scale, ch * scale)
        cr.fill()
        cr.save()
        cr.translate(ox, oy)
        cr.scale(scale, scale)
        cr.translate(-cx, -cy)
        cr.rectangle(cx, cy, cw, ch)
        cr.clip()
        self.render(cr)
        if self.drag and self.drag["kind"] != "crop":
            self.draw_shape(cr, self.drag)
        cr.restore()

        if self.drag and self.drag["kind"] == "crop":
            x, y, w, h = normalized(self.drag["p1"], self.drag["p2"])
            x1, y1 = self.to_widget(x, y)
            x2, y2 = self.to_widget(x + w, y + h)
            cr.set_source_rgba(0, 0, 0, 0.55)
            cr.rectangle(ox, oy, cw * scale, ch * scale)
            cr.rectangle(x1, y1, x2 - x1, y2 - y1)
            cr.set_fill_rule(cairo.FILL_RULE_EVEN_ODD)
            cr.fill()
            cr.set_source_rgb(0.37, 0.9, 0.97)
            cr.set_line_width(1.5)
            cr.set_dash([6, 4])
            cr.rectangle(x1, y1, x2 - x1, y2 - y1)
            cr.stroke()
            cr.set_dash([])
            cr.move_to(x1 + 6, y1 - 8 if y1 > oy + 20 else y1 + 18)
            cr.set_font_size(12)
            cr.show_text(f"{int(w)}×{int(h)}")
        return False

    def render(self, cr):
        cr.set_source_surface(self.base, 0, 0)
        cr.paint()
        for shape in self.shapes:
            self.draw_shape(cr, shape)

    def draw_shape(self, cr, shape):
        kind = shape["kind"]
        r, g, b = hex_rgb(shape["color"])
        size = shape["size"]
        cr.save()
        cr.set_line_cap(cairo.LINE_CAP_ROUND)
        cr.set_line_join(cairo.LINE_JOIN_ROUND)
        if kind in ("pen", "highlight"):
            points = shape["points"]
            if kind == "highlight":
                cr.set_source_rgba(r, g, b, 0.38)
                cr.set_line_width(size * 4 + 8)
                cr.set_line_cap(cairo.LINE_CAP_SQUARE)
            else:
                cr.set_source_rgb(r, g, b)
                cr.set_line_width(size)
            cr.move_to(*points[0])
            for point in points[1:]:
                cr.line_to(*point)
            cr.stroke()
        elif kind in ("arrow", "line"):
            (x1, y1), (x2, y2) = shape["p1"], shape["p2"]
            cr.set_source_rgb(r, g, b)
            cr.set_line_width(size)
            if kind == "arrow":
                angle = math.atan2(y2 - y1, x2 - x1)
                head = max(14, size * 4.2)
                length = math.hypot(x2 - x1, y2 - y1)
                head = min(head, length * 0.6) if length else head
                bx, by = x2 - head * 0.8 * math.cos(angle), y2 - head * 0.8 * math.sin(angle)
                cr.move_to(x1, y1)
                cr.line_to(bx, by)
                cr.stroke()
                spread = math.radians(26)
                cr.move_to(x2, y2)
                cr.line_to(x2 - head * math.cos(angle - spread), y2 - head * math.sin(angle - spread))
                cr.line_to(x2 - head * math.cos(angle + spread), y2 - head * math.sin(angle + spread))
                cr.close_path()
                cr.fill()
            else:
                cr.move_to(x1, y1)
                cr.line_to(x2, y2)
                cr.stroke()
        elif kind == "rect":
            x, y, w, h = normalized(shape["p1"], shape["p2"])
            cr.set_source_rgb(r, g, b)
            cr.set_line_width(size)
            radius = min(6, w / 2, h / 2)
            cr.new_sub_path()
            cr.arc(x + w - radius, y + radius, radius, -math.pi / 2, 0)
            cr.arc(x + w - radius, y + h - radius, radius, 0, math.pi / 2)
            cr.arc(x + radius, y + h - radius, radius, math.pi / 2, math.pi)
            cr.arc(x + radius, y + radius, radius, math.pi, 3 * math.pi / 2)
            cr.close_path()
            cr.stroke()
        elif kind == "ellipse":
            x, y, w, h = normalized(shape["p1"], shape["p2"])
            if w > 0 and h > 0:
                cr.set_source_rgb(r, g, b)
                cr.save()
                cr.translate(x + w / 2, y + h / 2)
                cr.scale(w / 2, h / 2)
                cr.arc(0, 0, 1, 0, 2 * math.pi)
                cr.restore()
                cr.set_line_width(size)
                cr.stroke()
        elif kind == "text":
            font_size = 12 + size * 2.6
            cr.select_font_face("Noto Sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
            cr.set_font_size(font_size)
            x, y = shape["p"]
            for index, line in enumerate(shape["text"].split("\n")):
                cr.move_to(x, y + font_size * (index + 0.85))
                cr.text_path(line)
            cr.set_source_rgb(*contrast(shape["color"]))
            cr.set_line_width(max(3, font_size / 6))
            cr.stroke_preserve()
            cr.set_source_rgb(r, g, b)
            cr.fill()
        elif kind == "step":
            x, y = shape["p"]
            radius = 11 + size * 1.6
            cr.arc(x, y, radius + 2, 0, 2 * math.pi)
            cr.set_source_rgb(*contrast(shape["color"]))
            cr.fill()
            cr.arc(x, y, radius, 0, 2 * math.pi)
            cr.set_source_rgb(r, g, b)
            cr.fill()
            label = str(shape["n"])
            cr.select_font_face("JetBrainsMono Nerd Font", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
            cr.set_font_size(radius * 1.15)
            extents = cr.text_extents(label)
            cr.move_to(x - extents.width / 2 - extents.x_bearing, y - extents.height / 2 - extents.y_bearing)
            cr.set_source_rgb(*contrast(shape["color"]))
            cr.show_text(label)
        elif kind == "blur":
            x, y, w, h = normalized(shape["p1"], shape["p2"])
            self.pixelate(cr, x, y, w, h)
        elif kind == "crop":
            pass
        cr.restore()

    def pixelate(self, cr, x, y, w, h):
        x, y, w, h = int(x), int(y), max(1, int(w)), max(1, int(h))
        block = max(8, min(w, h) // 6)
        sw, sh = max(1, w // block), max(1, h // block)
        small = cairo.ImageSurface(cairo.FORMAT_ARGB32, sw, sh)
        sctx = cairo.Context(small)
        sctx.scale(sw / w, sh / h)
        sctx.set_source_surface(self.base, -x, -y)
        sctx.get_source().set_filter(cairo.FILTER_GOOD)
        sctx.paint()
        cr.save()
        cr.rectangle(x, y, w, h)
        cr.clip()
        cr.translate(x, y)
        cr.scale(w / sw, h / sh)
        cr.set_source_surface(small, 0, 0)
        cr.get_source().set_filter(cairo.FILTER_NEAREST)
        cr.paint()
        cr.restore()

    # ---- output ----------------------------------------------------------- #

    def export(self):
        cx, cy, cw, ch = self.crop
        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, cw, ch)
        cr = cairo.Context(surface)
        cr.translate(-cx, -cy)
        self.render(cr)
        surface.flush()
        return surface

    def png_bytes(self):
        buffer = io.BytesIO()
        self.export().write_to_png(buffer)
        return buffer.getvalue()

    def copy(self, quiet=False):
        try:
            subprocess.run(["wl-copy", "--type", "image/png"], input=self.png_bytes(), timeout=5, check=True)
        except (OSError, subprocess.SubprocessError) as error:
            self.set_status(f"Copy failed: {error}", "#ff6b81")
            return False
        if not quiet:
            self.set_status("Copied to clipboard", "#78f0c2")
        return True

    def save(self, path=None, quiet=False):
        target = path or self.path
        try:
            self.export().write_to_png(target)
        except (OSError, cairo.Error) as error:
            self.set_status(f"Save failed: {error}", "#ff6b81")
            return False
        if target == self.path:
            self.dirty = False
            self.update_buttons()
        if not quiet:
            self.set_status(f"Saved {target}", "#78f0c2")
        return True

    def save_as(self):
        dialog = Gtk.FileChooserDialog(title="Save screenshot as", transient_for=self,
                                       action=Gtk.FileChooserAction.SAVE)
        dialog.add_buttons("Cancel", Gtk.ResponseType.CANCEL, "Save", Gtk.ResponseType.OK)
        dialog.set_do_overwrite_confirmation(True)
        dialog.set_current_folder(os.path.dirname(self.path))
        stem = os.path.splitext(os.path.basename(self.path))[0]
        dialog.set_current_name(f"{stem}-edited.png")
        if dialog.run() == Gtk.ResponseType.OK:
            target = dialog.get_filename()
            if not target.lower().endswith(".png"):
                target += ".png"
            self.save(target)
        dialog.destroy()

    def on_done(self, *_args):
        if self.copy(quiet=True) and self.save(quiet=True):
            self.notify_saved()
            self.destroy()

    def notify_saved(self):
        try:
            subprocess.Popen(["notify-send", "-u", "low", "-i", self.path, "Screenshot edited",
                              "Saved and copied to clipboard"])
        except OSError:
            pass

    def on_delete(self, *_args):
        if not self.dirty:
            return False
        dialog = Gtk.MessageDialog(transient_for=self, modal=True, message_type=Gtk.MessageType.QUESTION,
                                   buttons=Gtk.ButtonsType.NONE, text="Keep your edits?")
        dialog.format_secondary_text("Save copies the result to the clipboard and saves it over the screenshot.")
        dialog.add_buttons("Discard", Gtk.ResponseType.REJECT, "Cancel", Gtk.ResponseType.CANCEL,
                           "Save", Gtk.ResponseType.ACCEPT)
        response = dialog.run()
        dialog.destroy()
        if response == Gtk.ResponseType.ACCEPT:
            return not (self.copy(quiet=True) and self.save(quiet=True))
        return response != Gtk.ResponseType.REJECT


def main():
    provider = Gtk.CssProvider()
    provider.load_from_data(CSS)
    Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), provider,
                                             Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
    try:
        editor = Editor(IMAGE_PATH)
    except (cairo.Error, MemoryError) as error:
        fallback(IMAGE_PATH, f"cannot open image ({error})")
    editor.connect("destroy", Gtk.main_quit)
    Gtk.main()


if __name__ == "__main__":
    main()
