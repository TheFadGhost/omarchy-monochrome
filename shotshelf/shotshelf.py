#!/usr/bin/env python3
"""Screenshot shelf — a persistent, draggable replacement for Omarchy's
five-second screenshot toast.

WHY THIS IS A GTK4 APP AND NOT A QUICKSHELL PLUGIN
--------------------------------------------------
The whole point is dragging the image out into another window. That cannot be
done from Quickshell:

  * QtQuick's `Drag` is scene-local. Its DragType enum is None/Automatic/
    Internal — there is no External — and Quickshell registers no drag types
    at all. Cross-app drag needs C++ calling QDrag::exec().
  * Even in a toolkit that can do it, the drag must not originate from a
    wlr-layer-shell surface. wlroots validates the drag against the seat's
    last pointer-button serial AND requires the origin surface to hold pointer
    focus; layer surfaces configured without focus fail that check. KWin has a
    filed crash for exactly this pattern (bug 502497), and every application
    that successfully drags files out on Wayland — Flameshot, Nautilus — does
    so from an ordinary xdg_toplevel.

So this is a normal toplevel window, made to behave like an overlay with
Hyprland window rules (float, pin, no initial focus) plus a Wayland input
region so its transparent area stays click-through.

THE CONTENT PROVIDER DETAIL THAT ACTUALLY MATTERS
-------------------------------------------------
`Gdk.ContentProvider.new_for_value(Gio.File(...))` looks like the obvious
answer and is what most tutorials show. It is wrong here: the GValue carries
the *concrete* type GLocalFile, GDK registers its serialisers against the
GFile *interface*, so nothing matches and the drag offers ZERO mime types.
Measured on this machine:

    new_for_value(GFile)      -> ON THE WIRE: []
    new_for_value(GdkFileList)-> ['text/uri-list', 'text/plain;charset=utf-8',
                                  'application/vnd.portal.filetransfer', ...]

`Gdk.FileList` is the one that works. A drag built on the first would look
completely correct and silently fail on every drop.
"""

import os
import subprocess
import sys
import time

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Adw, Gdk, GdkPixbuf, Gio, GLib, Gtk  # noqa: E402

import cairo  # noqa: E402

APP_ID = "dev.ghost.shotshelf"
MAX_SHOTS = 6
COLLAPSE_DELAY = 6.0
WIN_W, WIN_H = 1000, 300

HOME = os.path.expanduser("~")
SHOT_DIR = os.environ.get("OMARCHY_SCREENSHOT_DIR") or os.path.join(HOME, "Pictures")
EDITOR = os.environ.get("OMARCHY_SCREENSHOT_EDITOR", "tensaku-edit")
THEME_DIR = os.path.join(HOME, ".config/omarchy/current/theme")

FALLBACK = {
    "background": "#0a0a0b",
    "foreground": "#dfe3e6",
    "accent": "#8f979c",
    "lighter_background": "#16181a",
    "dark_foreground": "#565c60",
}


def read_theme():
    """Parse the *current* theme's colors.toml so the shelf follows
    `omarchy theme set` instead of pinning one palette."""
    colors = dict(FALLBACK)
    path = os.path.join(THEME_DIR, "colors.toml")
    try:
        with open(path) as fh:
            for line in fh:
                line = line.split("#")[0].strip()
                if "=" not in line:
                    continue
                k, _, v = line.partition("=")
                v = v.strip().strip('"').strip("'")
                if v.startswith("#"):
                    colors[k.strip()] = v
    except OSError:
        pass
    return colors


def current_font():
    """Follow `omarchy font set` rather than pinning a family."""
    try:
        out = subprocess.run(["omarchy-font-current"], capture_output=True,
                             text=True, timeout=2).stdout.strip()
        if out:
            return out
    except Exception:
        pass
    return "monospace"


def css_for(c):
    fg, bg = c["foreground"], c["background"]
    font = current_font()
    return f"""
    window {{ background: transparent; }}
    * {{ font-family: "{font}", monospace; }}
    .card, .chip {{
        background: {bg};
        border: 1px solid alpha({fg}, 0.20);
        border-radius: 12px;
    }}
    .card {{ padding: 14px; }}
    .chip {{ padding: 6px 12px; }}
    /* The expand/collapse motion. GTK4 CSS animates transform, so the card can
       actually shrink toward the chip instead of cutting to it. */
    .card, .chip {{
        transition: opacity 200ms cubic-bezier(0.22, 1, 0.36, 1),
                    transform 260ms cubic-bezier(0.22, 1, 0.36, 1);
        opacity: 1;
        transform: scale(1);
    }}
    .card.off {{ opacity: 0; transform: scale(0.90); }}
    .chip.off {{ opacity: 0; transform: scale(1.14); }}
    .heading {{
        color: alpha({fg}, 0.55);
        font-size: 10px;
        font-weight: bold;
        letter-spacing: 1.2px;
    }}
    .filename {{ color: {fg}; font-size: 11px; }}
    .hint     {{ color: alpha({fg}, 0.50); font-size: 10px; }}
    .stamp    {{ color: alpha({fg}, 0.45); font-size: 10px; }}
    .act {{
        background: transparent;
        color: alpha({fg}, 0.85);
        border: 1px solid alpha({fg}, 0.22);
        border-radius: 9px;
        padding: 4px 10px;
        font-size: 11px;
        min-height: 0;
    }}
    .act:hover {{ background: alpha({fg}, 0.10); color: {fg}; }}
    .closebtn {{
        background: transparent; border: none; color: alpha({fg}, 0.45);
        padding: 0 4px; min-height: 0; min-width: 0; font-size: 11px;
    }}
    .closebtn:hover {{ color: {fg}; }}
    .thumb {{
        border: 1px solid alpha({fg}, 0.18);
        border-radius: 8px;
        background: alpha({fg}, 0.05);
    }}
    .thumb:hover {{ border-color: alpha({fg}, 0.55); }}
    .thumb.sel  {{ border-color: alpha({fg}, 0.70); }}
    """


_THUMBS = {}


def thumb(path, w, h):
    """Scaled-on-load texture.

    Gtk.Picture.set_filename keeps the full-resolution image, and its NATURAL
    size becomes the image's real size — 1920px — which inflates the whole card
    to fill the window no matter what size_request says. Loading a pre-scaled
    pixbuf fixes the layout and avoids holding 1920x1080 textures for a 58px
    thumbnail, which matters on a machine with 8 GB of RAM.
    """
    # NOTE: load at exactly the display size. A Picture's natural size comes
    # from its paintable and outranks set_size_request, so an oversized texture
    # silently inflates the card.
    key = (path, w, h)
    if key not in _THUMBS:
        try:
            pb = GdkPixbuf.Pixbuf.new_from_file_at_scale(path, w, h, True)
            _THUMBS[key] = Gdk.Texture.new_for_pixbuf(pb)
        except GLib.Error:
            return None
        if len(_THUMBS) > 64:
            _THUMBS.pop(next(iter(_THUMBS)))
    return _THUMBS[key]


def pin(widget, w, h):
    """Pin both axes so a thumbnail stays a thumbnail."""
    widget.set_size_request(w, h)
    widget.set_hexpand(False)
    widget.set_vexpand(False)
    widget.set_halign(Gtk.Align.CENTER)
    widget.set_valign(Gtk.Align.CENTER)
    widget.set_can_shrink(True)
    return widget


def run_detached(argv):
    try:
        GLib.spawn_async(
            argv,
            flags=GLib.SpawnFlags.SEARCH_PATH | GLib.SpawnFlags.DO_NOT_REAP_CHILD,
        )
    except GLib.Error as exc:
        print(f"spawn failed: {exc}", file=sys.stderr)


class Shelf(Adw.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID)
        self.shots = []
        self.selected = 0
        self.expanded = False
        self.win = None
        self._collapse_id = 0
        self._hovering = False

    # ---------------- lifecycle ----------------
    def do_activate(self):
        if self.win:
            self.win.present()
            return

        self.colors = read_theme()
        provider = Gtk.CssProvider()
        provider.load_from_data(css_for(self.colors).encode())
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

        self.win = Gtk.ApplicationWindow(application=self)
        self.win.set_decorated(False)
        self.win.set_default_size(WIN_W, WIN_H)
        self.win.set_resizable(False)

        # Everything lives in a fixed-size transparent canvas, centred at the
        # top. Keeping the WINDOW a constant size means Hyprland never has to
        # re-position it as the card grows and shrinks; only the input region
        # changes, so the empty space stays click-through.
        # An Overlay, not a Box: the card and the chip occupy the SAME spot so
        # one can scale into the other. Both stay mapped (a hidden widget is out
        # of the layout and cannot transition), and the inactive one is made
        # non-targetable so it never eats a click.
        self.holder = Gtk.Overlay()
        self.holder.set_halign(Gtk.Align.CENTER)
        self.holder.set_valign(Gtk.Align.START)
        self.win.set_child(self.holder)

        self.card = self.build_card()
        self.chip = self.build_chip()
        self.holder.set_child(self.card)
        self.holder.add_overlay(self.chip)
        self.card.add_css_class("off")
        self.chip.add_css_class("off")
        self.card.set_can_target(False)
        self.chip.set_can_target(False)

        motion = Gtk.EventControllerMotion()
        motion.connect("enter", self.on_enter)
        motion.connect("leave", self.on_leave)
        self.win.add_controller(motion)

        self.win.connect("notify::default-width", lambda *_: self.sync_input_region())
        self.win.present()
        GLib.timeout_add(150, self.sync_input_region_once)

        self.start_watch()
        self.render()

    # ---------------- input region ----------------
    def sync_input_region_once(self):
        self.sync_input_region()
        return False

    def sync_input_region(self):
        """Confine clicks to the visible card/chip. Without this the whole
        1000x300 transparent window would swallow clicks meant for the app
        underneath."""
        surface = self.win.get_surface() if self.win else None
        if not surface:
            return
        target = self.card if self.expanded else self.chip
        ok, rect = target.compute_bounds(self.win)
        region = cairo.Region()
        if ok and self.shots:
            region = cairo.Region(
                cairo.RectangleInt(
                    int(rect.origin.x), int(rect.origin.y),
                    max(1, int(rect.size.width)), max(1, int(rect.size.height)),
                )
            )
        try:
            surface.set_input_region(region)
        except Exception:
            pass

    # ---------------- widgets ----------------
    def drag_source_for(self, widget, path_getter):
        """Attach a real cross-application file drag to `widget`."""
        src = Gtk.DragSource()
        src.set_actions(Gdk.DragAction.COPY)

        def prepare(_s, _x, _y):
            path = path_getter()
            if not path or not os.path.exists(path):
                return None
            gfile = Gio.File.new_for_path(path)
            # Gdk.FileList, NOT Gio.File — see the module docstring.
            return Gdk.ContentProvider.new_for_value(Gdk.FileList.new_from_list([gfile]))

        def begin(s, _drag):
            # Drag under the cursor as a picture of the thumbnail itself.
            paintable = Gtk.WidgetPaintable.new(widget)
            s.set_icon(paintable, 32, 24)
            self.cancel_collapse()

        src.connect("prepare", prepare)
        src.connect("drag-begin", begin)
        widget.add_controller(src)
        return src

    def build_card(self):
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        card.add_css_class("card")
        card.set_size_request(430, -1)
        card.set_halign(Gtk.Align.CENTER)
        card.set_valign(Gtk.Align.START)

        head = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        lbl = Gtk.Label(label="SCREENSHOT", xalign=0)
        lbl.add_css_class("heading")
        lbl.set_hexpand(True)
        head.append(lbl)
        self.stamp_lbl = Gtk.Label(label="")
        self.stamp_lbl.add_css_class("stamp")
        head.append(self.stamp_lbl)
        close = Gtk.Button(label="✕")
        close.add_css_class("closebtn")
        close.connect("clicked", lambda *_: self.clear_all())
        head.append(close)
        card.append(head)

        body = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        self.preview = Gtk.Picture()
        self.preview.set_content_fit(Gtk.ContentFit.COVER)
        pin(self.preview, 150, 86)
        self.preview.add_css_class("thumb")
        self.preview.set_tooltip_text("Drag me into another window")
        self.drag_source_for(self.preview, lambda: self.current())
        body.append(self.preview)

        meta = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4, valign=Gtk.Align.CENTER)
        self.name_lbl = Gtk.Label(label="", xalign=0, wrap=False,
                                  ellipsize=3, max_width_chars=28)
        self.name_lbl.add_css_class("filename")
        meta.append(self.name_lbl)
        hint = Gtk.Label(label="Drag the image out, or use the buttons.",
                         xalign=0, wrap=True, max_width_chars=30)
        hint.add_css_class("hint")
        meta.append(hint)
        body.append(meta)
        card.append(body)

        acts = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        for label, cb in (
            ("Copy path", self.copy_path),
            ("Copy image", self.copy_image),
            ("Edit", self.open_editor),
        ):
            b = Gtk.Button(label=label)
            b.add_css_class("act")
            b.connect("clicked", lambda _w, f=cb: f())
            acts.append(b)
        card.append(acts)

        # The fan — one draggable thumbnail per recent shot.
        self.fan = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        card.append(self.fan)
        return card

    def build_chip(self):
        chip = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        chip.add_css_class("chip")
        chip.set_halign(Gtk.Align.CENTER)
        chip.set_valign(Gtk.Align.START)
        self.chip_thumb = Gtk.Picture()
        self.chip_thumb.set_content_fit(Gtk.ContentFit.COVER)
        pin(self.chip_thumb, 34, 20)
        self.chip_thumb.add_css_class("thumb")
        self.drag_source_for(self.chip_thumb, lambda: self.current())
        chip.append(self.chip_thumb)
        self.chip_lbl = Gtk.Label(label="Screenshot")
        self.chip_lbl.add_css_class("filename")
        chip.append(self.chip_lbl)

        click = Gtk.GestureClick()
        click.set_button(0)
        click.connect("released", self.on_chip_click)
        chip.add_controller(click)
        return chip

    # ---------------- state ----------------
    def current(self):
        if 0 <= self.selected < len(self.shots):
            return self.shots[self.selected]
        return None

    def add_shot(self, path):
        if not os.path.basename(path).startswith("screenshot-"):
            return
        if not path.endswith(".png"):
            return
        if path in self.shots:
            self.shots.remove(path)
        self.shots.insert(0, path)
        del self.shots[MAX_SHOTS:]
        self.selected = 0
        self.set_expanded(True)
        self.render()

    def clear_all(self):
        self.shots = []
        self.selected = 0
        self.set_expanded(False)
        self.render()

    def drop_shot(self, path):
        if path in self.shots:
            self.shots.remove(path)
        self.selected = min(self.selected, max(0, len(self.shots) - 1))
        if not self.shots:
            self.set_expanded(False)
        self.render()

    # ---------------- animation ----------------
    def set_expanded(self, want):
        if want == self.expanded:
            if want:
                self.schedule_collapse()
            return
        self.expanded = want
        self.apply_state()
        if want:
            self.schedule_collapse()

    def apply_state(self):
        """Drive the transition by toggling one CSS class per surface."""
        showing, hiding = (self.card, self.chip) if self.expanded else (self.chip, self.card)
        showing.remove_css_class("off")
        hiding.add_css_class("off")
        showing.set_can_target(bool(self.shots))
        hiding.set_can_target(False)
        # Re-cut the input region once the motion has settled on its new size.
        GLib.timeout_add(280, self.sync_input_region_once)
        self.sync_input_region()

    def schedule_collapse(self):
        self.cancel_collapse()
        self._collapse_id = GLib.timeout_add(
            int(COLLAPSE_DELAY * 1000), self._collapse_now
        )

    def cancel_collapse(self):
        if self._collapse_id:
            GLib.source_remove(self._collapse_id)
            self._collapse_id = 0

    def _collapse_now(self):
        self._collapse_id = 0
        if not self._hovering and self.shots:
            self.set_expanded(False)
        return False

    def on_enter(self, *_a):
        self._hovering = True
        self.cancel_collapse()

    def on_leave(self, *_a):
        self._hovering = False
        if self.expanded:
            self.schedule_collapse()

    def on_chip_click(self, gesture, n_press, x, y):
        if gesture.get_current_button() == 3:
            self.clear_all()
        else:
            self.set_expanded(True)

    # ---------------- render ----------------
    def render(self):
        has = bool(self.shots)
        cur = self.current()

        if self.win:
            self.win.set_visible(has)
        self.apply_state()
        if not has:
            self.sync_input_region()
            return

        self.name_lbl.set_text(os.path.basename(cur))
        self.stamp_lbl.set_text(self.stamp_of(cur))
        self.preview.set_paintable(thumb(cur, 150, 86))
        self.chip_thumb.set_paintable(thumb(cur, 34, 20))
        self.chip_lbl.set_text(
            f"Screenshots · {len(self.shots)}" if len(self.shots) > 1 else "Screenshot"
        )

        child = self.fan.get_first_child()
        while child:
            nxt = child.get_next_sibling()
            self.fan.remove(child)
            child = nxt

        # Fan the recent shots out so each one can be grabbed individually.
        self.fan.set_visible(len(self.shots) > 1)
        if len(self.shots) > 1:
            for i, path in enumerate(self.shots):
                pic = Gtk.Picture()
                pic.set_content_fit(Gtk.ContentFit.COVER)
                pin(pic, 58, 34)
                pic.set_paintable(thumb(path, 58, 34))
                pic.add_css_class("thumb")
                if i == self.selected:
                    pic.add_css_class("sel")
                pic.set_tooltip_text(os.path.basename(path))
                self.drag_source_for(pic, lambda p=path: p)

                g = Gtk.GestureClick()
                g.set_button(0)

                def clicked(gesture, n, x, y, idx=i, p=path):
                    if gesture.get_current_button() == 3:
                        self.drop_shot(p)
                    else:
                        self.selected = idx
                        self.render()
                    self.schedule_collapse()

                g.connect("released", clicked)
                pic.add_controller(g)
                self.fan.append(pic)

        GLib.timeout_add(60, self.sync_input_region_once)

    @staticmethod
    def stamp_of(path):
        base = os.path.basename(path)
        part = base.rsplit("_", 1)[-1].replace(".png", "")
        bits = part.split("-")
        return ":".join(bits) if len(bits) == 3 else time.strftime("%H:%M:%S")

    # ---------------- actions ----------------
    def copy_path(self):
        cur = self.current()
        if cur:
            Gdk.Display.get_default().get_clipboard().set(cur)

    def copy_image(self):
        cur = self.current()
        if not cur:
            return
        try:
            texture = Gdk.Texture.new_from_filename(cur)
            Gdk.Display.get_default().get_clipboard().set(texture)
        except GLib.Error:
            pass

    def open_editor(self):
        cur = self.current()
        if cur:
            run_detached([EDITOR, cur])

    # ---------------- watching ----------------
    def start_watch(self):
        gdir = Gio.File.new_for_path(SHOT_DIR)
        self.monitor = gdir.monitor_directory(Gio.FileMonitorFlags.WATCH_MOVES, None)
        self.monitor.set_rate_limit(200)
        self.monitor.connect("changed", self.on_dir_changed)

    def on_dir_changed(self, _m, gfile, _other, event):
        # CHANGES_DONE_HINT rather than CREATED: grim writes the PNG in stages
        # and a CREATED event fires while the file is still a stub.
        if event in (
            Gio.FileMonitorEvent.CHANGES_DONE_HINT,
            Gio.FileMonitorEvent.MOVED_IN,
        ):
            path = gfile.get_path()
            if path:
                self.add_shot(path)


if __name__ == "__main__":
    app = Shelf()
    app.run(None)
