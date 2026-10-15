#!/usr/bin/env python3
"""A visual, searchable library for cliphist on Hyprland."""

import re
import subprocess
import sys

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Gdk, GdkPixbuf, Gio, GLib, Gtk, Pango  # noqa: E402


APP_ID = "dev.eftear.hyprland.ClipboardLibrary"

CATEGORIES = (
    ("All", "󰅌"),
    ("Text", "󰦨"),
    ("Images", ""),
    ("Links", "󰌹"),
    ("Code", "󰅩"),
    ("Commands", ""),
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
@define-color red #ff6b81;

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
  min-width: 190px;
  padding: 18px 12px;
  background: @panel;
  border-right: 1px solid @border;
}
.sidebar-title { margin: 2px 10px 12px; color: @muted; font-size: 10px; font-weight: 800; }
button.category {
  min-height: 40px;
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

#library { background: @bg; border-right: 1px solid @border; }
#library-header { min-height: 74px; padding: 0 18px; background: @bg; }
.section-title { color: @text; font-size: 15px; font-weight: 800; }
.section-copy { margin-top: 3px; color: @muted; font-size: 10px; }
.live-dot { color: @green; font-size: 14px; }
.live-label { color: @green; font-size: 9px; font-weight: 800; }

button.icon-button {
  min-width: 34px;
  min-height: 34px;
  padding: 0;
  color: @muted;
  background: @panel2;
  border: 1px solid @border;
  border-radius: 9px;
  box-shadow: none;
}
button.icon-button:hover { color: @cyan; background: @hover; border-color: alpha(@cyan, .45); }
button.icon-button.danger:hover { color: @red; border-color: alpha(@red, .55); }

list { padding: 3px 10px 14px; background: @bg; }
row.clip-row {
  margin: 2px 0;
  padding: 0;
  color: @text;
  background: @card;
  border: 1px solid @border;
  border-radius: 11px;
}
row.clip-row:hover { background: @hover; border-color: alpha(@cyan, .35); }
row.clip-row:selected {
  color: @text;
  background-color: #132a38;
  background-image: none;
  border-color: @cyan;
  box-shadow: none;
}
.clip-inner { min-height: 46px; padding: 4px 9px; }
.type-icon-box {
  min-width: 30px;
  min-height: 30px;
  color: @violet;
  background: alpha(@violet, .10);
  border: 1px solid alpha(@violet, .24);
  border-radius: 8px;
  font-size: 13px;
}
.clip-title { color: @text; font-size: 11px; font-weight: 700; }
.clip-meta { margin-top: 2px; color: @muted; font-size: 8px; }
.clip-index { color: #5d6a86; font-size: 9px; }

#preview { min-width: 390px; padding: 0; background: @panel; }
#preview-header { min-height: 74px; padding: 0 18px; border-bottom: 1px solid @border; }
.type-pill { color: @violet; font-size: 9px; font-weight: 800; }
.preview-meta { margin-top: 3px; color: @muted; font-size: 9px; }

#preview-card {
  margin: 18px;
  padding: 14px;
  background: #0a0f1d;
  border: 1px solid @border;
  border-radius: 12px;
}
textview, textview text {
  color: #cbd7f4;
  background: transparent;
  font-family: "JetBrainsMono Nerd Font Mono", monospace;
  font-size: 11px;
}
.image-frame { padding: 10px; background: #060912; border-radius: 10px; }
.image-label { margin-top: 10px; color: @muted; font-size: 10px; }

#empty { margin: 55px 28px; }
.empty-icon { color: @violet; font-size: 42px; }
.empty-title { margin-top: 12px; color: @text; font-size: 15px; font-weight: 800; }
.empty-copy { margin-top: 6px; color: @muted; font-size: 10px; }

#actions { min-height: 64px; padding: 0 18px; border-top: 1px solid @border; }
button.action {
  min-height: 35px;
  padding: 0 14px;
  color: @text;
  background: @panel2;
  border: 1px solid @border;
  border-radius: 9px;
  box-shadow: none;
  font-size: 10px;
  font-weight: 800;
}
button.action:hover { background: @hover; border-color: alpha(@cyan, .45); }
button.action.primary { color: #061014; background: @cyan; border-color: @cyan; }
button.action.primary:hover { background: #93f2fb; }
button.action.danger { color: @red; }
button.action.danger:hover { background: alpha(@red, .10); border-color: alpha(@red, .55); }
button:disabled { opacity: .38; }

#statusbar {
  min-height: 34px;
  padding: 0 18px;
  color: @muted;
  background: @panel;
  border-top: 1px solid @border;
  font-size: 9px;
}
.status-accent { color: @cyan; font-weight: 800; }
scrollbar slider { min-width: 6px; min-height: 32px; background: #34415d; border-radius: 9px; }
scrollbar trough { background: transparent; }
"""


COMMAND_RE = re.compile(
    r"^(sudo\s+|apt\s+|apt-get\s+|dnf\s+|pacman\s+|systemctl\s+|journalctl\s+|"
    r"git\s+|docker\s+|podman\s+|kubectl\s+|npm\s+|pnpm\s+|yarn\s+|pip\s+|"
    r"python\s+|python3\s+|ssh\s+|scp\s+|rsync\s+|curl\s+|wget\s+|chmod\s+|chown\s+)",
    re.IGNORECASE,
)
CODE_RE = re.compile(
    r"(^|\s)(SELECT|INSERT|UPDATE|DELETE|CREATE|ALTER|DROP|FROM|WHERE|JOIN|"
    r"def|class|function|const|let|var|import|export|return|if|else)\b|"
    r"[{};]\s*$|```|=>|</?[a-z][^>]*>",
    re.IGNORECASE,
)
URL_RE = re.compile(r"^(https?://|www\.)\S+", re.IGNORECASE)


def run_checked(command, **kwargs):
    return subprocess.run(command, check=True, timeout=5, **kwargs)


def load_entries():
    try:
        result = run_checked(["cliphist", "list"], capture_output=True)
    except (OSError, subprocess.SubprocessError) as error:
        raise RuntimeError("Could not read clipboard history from cliphist") from error

    entries = []
    output = result.stdout.decode("utf-8", errors="replace")
    for position, line in enumerate(output.splitlines(), start=1):
        clip_id, separator, summary = line.partition("\t")
        if not separator or not clip_id.isdigit():
            continue
        summary = summary.strip()
        kind = classify(summary)
        entries.append(
            {
                "id": clip_id,
                "raw": line,
                "summary": summary,
                "kind": kind,
                "position": position,
                "mime": image_mime(summary),
            }
        )
    return entries


def classify(summary):
    lowered = summary.lower()
    if lowered.startswith("binary data "):
        return "Images" if "image/" in lowered else "Text"
    if URL_RE.search(summary):
        return "Links"
    if COMMAND_RE.search(summary):
        return "Commands"
    if CODE_RE.search(summary):
        return "Code"
    return "Text"


def image_mime(summary):
    match = re.search(r"binary data (image/[a-z0-9.+-]+)", summary, re.IGNORECASE)
    return match.group(1).lower() if match else None


def display_summary(item):
    if item["kind"] == "Images":
        return item["mime"] or "Clipboard image"
    text = re.sub(r"\s+", " ", item["summary"]).strip()
    return text or "Empty text"


def decode_item(item):
    try:
        result = run_checked(
            ["cliphist", "decode"], input=(item["raw"] + "\n").encode(), capture_output=True
        )
        return result.stdout
    except (OSError, subprocess.SubprocessError) as error:
        raise RuntimeError("Could not decode this clipboard item") from error


class ClipboardLibrary(Gtk.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.FLAGS_NONE)
        self.window = None
        self.entries = []
        self.category = "All"
        self.query = ""
        self.selected = None
        self.category_buttons = {}
        self.category_counts = {}

    def do_startup(self):
        Gtk.Application.do_startup(self)
        provider = Gtk.CssProvider()
        provider.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

    def do_activate(self):
        if self.window:
            self.reload_entries(select_first=False)
            self.window.present()
            return

        self.window = Gtk.ApplicationWindow(application=self)
        self.window.set_title("Clipboard Library")
        self.window.set_default_size(1240, 780)
        self.window.set_size_request(980, 620)
        self.window.set_position(Gtk.WindowPosition.CENTER)
        self.window.connect("key-press-event", self.on_key_press)

        header = Gtk.HeaderBar()
        header.set_show_close_button(True)
        header.props.title = "CLIPBOARD LIBRARY"
        header.props.subtitle = "Search, preview, and reuse your recent clips"
        self.search = Gtk.SearchEntry()
        self.search.get_style_context().add_class("search")
        self.search.set_placeholder_text("Search clipboard history…   Ctrl+F")
        self.search.connect("search-changed", self.on_search)
        header.pack_end(self.search)
        self.window.set_titlebar(header)

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        root.set_name("root")
        body = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        root.pack_start(body, True, True, 0)

        self.sidebar = self.build_sidebar()
        body.pack_start(self.sidebar, False, False, 0)

        library = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        library.set_name("library")
        library.set_size_request(535, -1)
        library.pack_start(self.build_library_header(), False, False, 0)

        list_scroll = Gtk.ScrolledWindow()
        list_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.listbox = Gtk.ListBox()
        self.listbox.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.listbox.set_activate_on_single_click(False)
        self.listbox.connect("row-selected", self.on_row_selected)
        self.listbox.connect("row-activated", self.on_row_activated)
        list_scroll.add(self.listbox)
        library.pack_start(list_scroll, True, True, 0)
        body.pack_start(library, True, True, 0)

        preview = self.build_preview()
        body.pack_end(preview, False, False, 0)

        status = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        status.set_name("statusbar")
        self.status_label = Gtk.Label(label="Select an item to preview it", xalign=0)
        hint = Gtk.Label(label="ENTER  copy & close     DEL  remove     ESC  close", xalign=1)
        hint.get_style_context().add_class("status-accent")
        status.pack_start(self.status_label, True, True, 0)
        status.pack_end(hint, False, False, 0)
        root.pack_end(status, False, False, 0)

        self.window.add(root)
        self.window.show_all()
        self.reload_entries(select_first=True)

    def build_sidebar(self):
        sidebar = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        sidebar.set_name("sidebar")
        title = Gtk.Label(label="COLLECTIONS", xalign=0)
        title.get_style_context().add_class("sidebar-title")
        sidebar.pack_start(title, False, False, 0)

        for name, icon in CATEGORIES:
            button = Gtk.Button()
            button.get_style_context().add_class("category")
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=7)
            icon_label = Gtk.Label(label=icon)
            icon_label.get_style_context().add_class("category-icon")
            name_label = Gtk.Label(label=name, xalign=0)
            name_label.get_style_context().add_class("category-name")
            count_label = Gtk.Label(label="0", xalign=1)
            count_label.get_style_context().add_class("category-count")
            row.pack_start(icon_label, False, False, 0)
            row.pack_start(name_label, True, True, 0)
            row.pack_end(count_label, False, False, 0)
            button.add(row)
            button.connect("clicked", self.on_category, name)
            sidebar.pack_start(button, False, False, 0)
            self.category_buttons[name] = button
            self.category_counts[name] = count_label

        self.category_buttons["All"].get_style_context().add_class("active")
        return sidebar

    def build_library_header(self):
        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        header.set_name("library-header")
        copy = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.collection_title = Gtk.Label(label="All clips", xalign=0)
        self.collection_title.get_style_context().add_class("section-title")
        self.collection_copy = Gtk.Label(label="Your most recent items appear first", xalign=0)
        self.collection_copy.get_style_context().add_class("section-copy")
        copy.pack_start(self.collection_title, False, False, 0)
        copy.pack_start(self.collection_copy, False, False, 0)

        refresh = Gtk.Button(label="󰑐")
        refresh.get_style_context().add_class("icon-button")
        refresh.set_size_request(36, 36)
        refresh.set_valign(Gtk.Align.CENTER)
        refresh.set_tooltip_text("Refresh history  ·  F5")
        refresh.connect("clicked", lambda *_: self.reload_entries(select_first=True))
        clear = Gtk.Button(label="󰆴")
        clear.get_style_context().add_class("icon-button")
        clear.get_style_context().add_class("danger")
        clear.set_size_request(36, 36)
        clear.set_valign(Gtk.Align.CENTER)
        clear.set_tooltip_text("Clear all clipboard history")
        clear.connect("clicked", self.confirm_clear)
        header.pack_start(copy, True, True, 0)
        header.pack_end(clear, False, False, 0)
        header.pack_end(refresh, False, False, 0)
        return header

    def build_preview(self):
        preview = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        preview.set_name("preview")
        preview.set_size_request(435, -1)

        header = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        header.set_name("preview-header")
        header.set_valign(Gtk.Align.CENTER)
        self.preview_type = Gtk.Label(label="NO SELECTION", xalign=0)
        self.preview_type.get_style_context().add_class("type-pill")
        self.preview_title = Gtk.Label(label="Preview", xalign=0)
        self.preview_title.get_style_context().add_class("section-title")
        self.preview_meta = Gtk.Label(label="Choose a clip from the library", xalign=0)
        self.preview_meta.get_style_context().add_class("preview-meta")
        header.pack_start(self.preview_type, False, False, 0)
        header.pack_start(self.preview_title, False, False, 2)
        header.pack_start(self.preview_meta, False, False, 0)
        preview.pack_start(header, False, False, 0)

        self.preview_stack = Gtk.Stack()
        self.preview_stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self.preview_stack.set_transition_duration(130)

        empty = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        empty.set_name("empty")
        empty.set_valign(Gtk.Align.CENTER)
        empty_icon = Gtk.Label(label="󰅌")
        empty_icon.get_style_context().add_class("empty-icon")
        empty_title = Gtk.Label(label="Ready when you are")
        empty_title.get_style_context().add_class("empty-title")
        empty_copy = Gtk.Label(label="Select a clip to inspect its full contents.")
        empty_copy.get_style_context().add_class("empty-copy")
        empty.pack_start(empty_icon, False, False, 0)
        empty.pack_start(empty_title, False, False, 0)
        empty.pack_start(empty_copy, False, False, 0)
        self.preview_stack.add_named(empty, "empty")

        text_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        text_card.set_name("preview-card")
        text_scroll = Gtk.ScrolledWindow()
        text_scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        self.text_preview = Gtk.TextView()
        self.text_preview.set_editable(False)
        self.text_preview.set_cursor_visible(True)
        self.text_preview.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self.text_preview.set_left_margin(3)
        self.text_preview.set_right_margin(3)
        text_scroll.add(self.text_preview)
        text_card.pack_start(text_scroll, True, True, 0)
        self.preview_stack.add_named(text_card, "text")

        image_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        image_card.set_name("preview-card")
        image_card.set_valign(Gtk.Align.CENTER)
        image_card.set_halign(Gtk.Align.CENTER)
        self.image_preview = Gtk.Image()
        self.image_preview.get_style_context().add_class("image-frame")
        self.image_info = Gtk.Label()
        self.image_info.get_style_context().add_class("image-label")
        image_card.pack_start(self.image_preview, False, False, 0)
        image_card.pack_start(self.image_info, False, False, 0)
        self.preview_stack.add_named(image_card, "image")
        preview.pack_start(self.preview_stack, True, True, 0)

        actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=7)
        actions.set_name("actions")
        self.delete_button = Gtk.Button(label="󰆴  Delete")
        self.delete_button.get_style_context().add_class("action")
        self.delete_button.get_style_context().add_class("danger")
        self.delete_button.connect("clicked", self.delete_selected)
        self.copy_button = Gtk.Button(label="󰆏  Copy")
        self.copy_button.get_style_context().add_class("action")
        self.copy_button.connect("clicked", lambda *_: self.copy_selected(close=False))
        self.copy_close_button = Gtk.Button(label="󰅌  Copy & close")
        self.copy_close_button.get_style_context().add_class("action")
        self.copy_close_button.get_style_context().add_class("primary")
        self.copy_close_button.connect("clicked", lambda *_: self.copy_selected(close=True))
        actions.pack_start(self.delete_button, False, False, 0)
        actions.pack_end(self.copy_close_button, False, False, 0)
        actions.pack_end(self.copy_button, False, False, 0)
        preview.pack_end(actions, False, False, 0)
        self.set_actions_sensitive(False)
        return preview

    def reload_entries(self, select_first=True):
        try:
            self.entries = load_entries()
        except RuntimeError as error:
            self.entries = []
            self.show_error(str(error))
        self.update_counts()
        self.refresh_list(select_first=select_first)

    def update_counts(self):
        self.category_counts["All"].set_text(str(len(self.entries)))
        for category, _icon in CATEGORIES[1:]:
            count = sum(item["kind"] == category for item in self.entries)
            self.category_counts[category].set_text(str(count))

    def matching_entries(self):
        results = []
        for item in self.entries:
            category_match = self.category == "All" or item["kind"] == self.category
            haystack = f"{item['kind']} {item['summary']}".lower()
            if category_match and (not self.query or self.query in haystack):
                results.append(item)
        return results

    def refresh_list(self, select_first=True):
        for child in self.listbox.get_children():
            self.listbox.remove(child)

        results = self.matching_entries()
        self.collection_title.set_text("Search results" if self.query else f"{self.category} clips")
        self.collection_copy.set_text(f"{len(results)} items  ·  newest first")
        for item in results:
            self.listbox.add(self.build_row(item))
        self.listbox.show_all()

        if results and select_first:
            first = self.listbox.get_row_at_index(0)
            self.listbox.select_row(first)
            first.grab_focus()
        elif not results:
            self.clear_preview("No matching clips", "Try another search or collection.")

    def build_row(self, item):
        row = Gtk.ListBoxRow()
        row.item = item
        row.get_style_context().add_class("clip-row")
        inner = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=11)
        inner.get_style_context().add_class("clip-inner")
        icon = Gtk.Label(label=CATEGORY_ICONS[item["kind"]])
        icon.get_style_context().add_class("type-icon-box")

        copy = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        title = Gtk.Label(label=display_summary(item), xalign=0)
        title.set_ellipsize(Pango.EllipsizeMode.END)
        title.set_max_width_chars(58)
        title.get_style_context().add_class("clip-title")
        recency = "LATEST" if item["position"] == 1 else f"RECENT  #{item['position']}"
        meta = Gtk.Label(label=f"{item['kind'].upper()}   ·   {recency}", xalign=0)
        meta.get_style_context().add_class("clip-meta")
        copy.pack_start(title, False, False, 0)
        copy.pack_start(meta, False, False, 0)
        index = Gtk.Label(label=f"#{item['id']}")
        index.get_style_context().add_class("clip-index")
        inner.pack_start(icon, False, False, 0)
        inner.pack_start(copy, True, True, 0)
        inner.pack_end(index, False, False, 0)
        row.add(inner)
        return row

    def on_category(self, _button, category):
        self.category = category
        for name, button in self.category_buttons.items():
            context = button.get_style_context()
            (context.add_class if name == category else context.remove_class)("active")
        self.refresh_list(select_first=True)

    def on_search(self, entry):
        self.query = entry.get_text().strip().lower()
        self.refresh_list(select_first=True)

    def on_row_selected(self, _listbox, row):
        if not row:
            self.selected = None
            self.set_actions_sensitive(False)
            return
        self.selected = row.item
        self.render_preview(self.selected)

    def on_row_activated(self, _listbox, _row):
        self.copy_selected(close=True)

    def render_preview(self, item):
        try:
            data = decode_item(item)
        except RuntimeError as error:
            self.show_error(str(error))
            return

        self.preview_type.set_text(f"{CATEGORY_ICONS[item['kind']]}  {item['kind'].upper()}")
        self.preview_title.set_text("Image preview" if item["kind"] == "Images" else "Full contents")
        self.set_actions_sensitive(True)

        if item["kind"] == "Images":
            try:
                loader = GdkPixbuf.PixbufLoader.new_with_type((item["mime"] or "image/png").split("/")[-1])
                loader.write(data)
                loader.close()
                pixbuf = loader.get_pixbuf()
                original_width, original_height = pixbuf.get_width(), pixbuf.get_height()
                scale = min(385 / original_width, 430 / original_height, 1.0)
                width = max(1, int(original_width * scale))
                height = max(1, int(original_height * scale))
                if scale < 1:
                    pixbuf = pixbuf.scale_simple(width, height, GdkPixbuf.InterpType.BILINEAR)
                self.image_preview.set_from_pixbuf(pixbuf)
                self.image_info.set_text(f"{original_width} × {original_height} px   ·   {len(data) / 1024:.1f} KB")
                self.preview_meta.set_text(f"{item['mime'] or 'image'}  ·  clipboard item #{item['id']}")
                self.preview_stack.set_visible_child_name("image")
            except GLib.Error:
                self.clear_preview("Preview unavailable", "The image can still be copied or deleted.")
                self.set_actions_sensitive(True)
        else:
            text = data.decode("utf-8", errors="replace")
            self.text_preview.get_buffer().set_text(text)
            lines = text.count("\n") + 1
            self.preview_meta.set_text(f"{len(text):,} characters  ·  {lines:,} lines  ·  item #{item['id']}")
            self.preview_stack.set_visible_child_name("text")

    def clear_preview(self, title="Preview", copy="Choose a clip from the library"):
        self.selected = None
        self.preview_type.set_text("NO SELECTION")
        self.preview_title.set_text(title)
        self.preview_meta.set_text(copy)
        self.preview_stack.set_visible_child_name("empty")
        self.set_actions_sensitive(False)

    def set_actions_sensitive(self, enabled):
        self.copy_button.set_sensitive(enabled)
        self.copy_close_button.set_sensitive(enabled)
        self.delete_button.set_sensitive(enabled)

    def copy_selected(self, close=False):
        if not self.selected:
            return
        try:
            data = decode_item(self.selected)
            command = ["wl-copy"]
            if self.selected["mime"]:
                command.extend(["--type", self.selected["mime"]])
            run_checked(command, input=data)
        except (RuntimeError, OSError, subprocess.SubprocessError):
            self.show_error("Could not copy this item back to the clipboard")
            return

        self.status_label.set_markup(
            f"<span foreground='#78f0c2'><b>Copied</b></span>  {GLib.markup_escape_text(display_summary(self.selected)[:65])}"
        )
        if close:
            self.window.close()

    def delete_selected(self, *_args):
        if not self.selected:
            return
        deleted_id = self.selected["id"]
        try:
            run_checked(["cliphist", "delete"], input=(self.selected["raw"] + "\n").encode())
        except (OSError, subprocess.SubprocessError):
            self.show_error("Could not delete this clipboard item")
            return
        self.status_label.set_markup(f"<span foreground='#ffcc66'><b>Removed</b></span>  item #{deleted_id}")
        self.reload_entries(select_first=True)

    def confirm_clear(self, *_args):
        if not self.entries:
            return
        dialog = Gtk.MessageDialog(
            transient_for=self.window,
            flags=Gtk.DialogFlags.MODAL,
            message_type=Gtk.MessageType.WARNING,
            buttons=Gtk.ButtonsType.NONE,
            text="Clear all clipboard history?",
        )
        dialog.format_secondary_text("This permanently removes every item stored by cliphist.")
        dialog.add_button("Cancel", Gtk.ResponseType.CANCEL)
        dialog.add_button("Clear history", Gtk.ResponseType.ACCEPT)
        response = dialog.run()
        dialog.destroy()
        if response != Gtk.ResponseType.ACCEPT:
            return
        try:
            run_checked(["cliphist", "wipe"])
        except (OSError, subprocess.SubprocessError):
            self.show_error("Could not clear clipboard history")
            return
        self.status_label.set_markup("<span foreground='#ffcc66'><b>Clipboard history cleared</b></span>")
        self.reload_entries(select_first=False)

    def on_key_press(self, _window, event):
        control = bool(event.state & Gdk.ModifierType.CONTROL_MASK)
        shift = bool(event.state & Gdk.ModifierType.SHIFT_MASK)
        if event.keyval == Gdk.KEY_Escape:
            self.window.close()
            return True
        if control and event.keyval in (Gdk.KEY_f, Gdk.KEY_F):
            self.search.grab_focus()
            return True
        if event.keyval == Gdk.KEY_F5:
            self.reload_entries(select_first=True)
            return True
        if not self.search.is_focus() and event.keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            self.copy_selected(close=not control)
            return True
        if not self.search.is_focus() and event.keyval == Gdk.KEY_Delete:
            if control and shift:
                self.confirm_clear()
            else:
                self.delete_selected()
            return True
        if not self.search.is_focus() and control and event.keyval in (Gdk.KEY_c, Gdk.KEY_C):
            self.copy_selected(close=False)
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


if __name__ == "__main__":
    app = ClipboardLibrary()
    sys.exit(app.run(sys.argv))
