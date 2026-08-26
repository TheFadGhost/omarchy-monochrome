"""Sill Screenshots tab — the ported ghost-shotshelf, plus click-to-rename.

Detection is a Gio.FileMonitor on the screenshot directory keyed on
CHANGES_DONE_HINT (not CREATED, which fires while grim is still writing).
WATCH_MOVES also delivers RENAMED for the click-to-rename flow: the tab
renames the file on disk and lets the monitor's RENAMED event reconcile the
in-memory list, so captures renamed by anything else stay correct too.
"""

import os
import sys
import time

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Gdk, GdkPixbuf, Gio, GLib, Gtk  # noqa: E402

import providers  # noqa: E402

HOME = os.path.expanduser("~")
# Mirror omarchy-capture-screenshot's own fallback chain exactly:
#   ${OMARCHY_SCREENSHOT_DIR:-${XDG_PICTURES_DIR:-$HOME/Pictures}}
SHOT_DIR = (
    os.environ.get("OMARCHY_SCREENSHOT_DIR")
    or os.environ.get("XDG_PICTURES_DIR")
    or os.path.join(HOME, "Pictures")
)
EDITOR = os.environ.get("OMARCHY_SCREENSHOT_EDITOR", "tensaku-edit")

_THUMBS = {}


def thumb(path, w, h):
    """Scaled-on-load texture. Gtk.Picture's NATURAL size is the paintable's
    real size and outranks set_size_request — a full-res texture silently
    inflates the whole card, and holding 1920px textures for 58px thumbnails
    is not acceptable on an 8 GB machine. Load at exactly the display size."""
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


def forget_thumbs(path):
    """Drop every cached size of `path`. A deleted file must not keep painting."""
    for key in [k for k in _THUMBS if k[0] == path]:
        _THUMBS.pop(key, None)


def drop_paintables(widget):
    """Unset every Gtk.Picture paintable in `widget`'s tree.

    MUST be called before run_dispose() on anything that may contain a
    picture. run_dispose() is itself required (it breaks the
    widget->controller->closure->widget cycle Python's GC cannot see), but
    GObject runs dispose a SECOND time on the final unref, and a Gtk.Picture
    torn down while it holds the LAST reference to its Gdk.Texture faults
    there in gdk_paintable_get_flags() on freed memory -- a reliable SIGSEGV,
    not a rare race. It is reached whenever the cache stops holding the
    texture too: forget_thumbs() on a deleted or renamed screenshot, or the
    64-entry LRU eviction in thumb(). Clearing the paintable first releases
    the texture through the normal path while the widget is still whole.
    """
    if isinstance(widget, Gtk.Picture):
        widget.set_paintable(None)
        return
    kid = widget.get_first_child()
    while kid:
        drop_paintables(kid)
        kid = kid.get_next_sibling()


def pin_size(widget, w, h):
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


class ScreenshotsTab:
    """Owns the Screenshots page. The app owns expand/collapse and the input
    region; this tab reports events up through the `app` reference."""

    def __init__(self, app):
        self.app = app
        self.shots = []
        self.selected = 0
        self.latest_at = 0.0  # monotonic-ish arrival stamp for tab pick
        self.monitor = None
        self.widget = self._build()
        self._start_watch()
        # Ingest anything already on disk this session? No — the shelf has
        # always started empty; a login shouldn't resurrect old captures.

    # ---------------- config ----------------
    @property
    def max_history(self):
        return int(self.app.settings.get("sill.screenshots.max_history", 10))

    def _action_on(self, key):
        return bool(self.app.settings.get(f"sill.screenshots.{key}", True))

    # ---------------- widgets ----------------
    def _drag_source_for(self, widget, path_getter):
        """Attach a real cross-application drag to `widget`."""
        src = Gtk.DragSource()
        src.set_actions(Gdk.DragAction.COPY)

        def prepare(_s, _x, _y):
            if not self._action_on("drag"):
                return None
            path = path_getter()
            if not path or not os.path.exists(path):
                return None
            # Union: uri-list + image/* + path text — the target chooses.
            return providers.for_image_file(path)

        def begin(s, _drag):
            # s.get_widget(), NOT the captured `widget` — a controller
            # closure referencing its own widget creates an uncollectable
            # cross-C ref cycle (leak; see clipboard_tab.render()).
            paintable = Gtk.WidgetPaintable.new(s.get_widget())
            s.set_icon(paintable, 32, 24)
            self.app.drag_began()

        # drag-begin freezes the collapse timer and blocks hover-expand
        # (via the app's drag counter); re-arm on both outcomes or the
        # panel stays expanded forever after one drag.
        def end(_s, _drag, _delete):
            self.app.drag_ended()

        def cancelled(_s, _drag, _reason):
            self.app.drag_ended()
            return False  # let GTK run its drag-cancel animation

        src.connect("prepare", prepare)
        src.connect("drag-begin", begin)
        src.connect("drag-end", end)
        src.connect("drag-cancel", cancelled)
        widget.add_controller(src)
        return src

    def _build(self):
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)

        head = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        lbl = Gtk.Label(label="SCREENSHOT", xalign=0)
        lbl.add_css_class("heading")
        lbl.set_hexpand(True)
        head.append(lbl)
        self.stamp_lbl = Gtk.Label(label="")
        self.stamp_lbl.add_css_class("stamp")
        head.append(self.stamp_lbl)
        page.append(head)

        self.empty_lbl = Gtk.Label(
            label="No screenshots this session.\nPRINT captures one.")
        self.empty_lbl.add_css_class("hint")
        self.empty_lbl.set_margin_top(18)
        self.empty_lbl.set_margin_bottom(18)
        page.append(self.empty_lbl)

        self.body = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        self.preview = Gtk.Picture()
        self.preview.set_content_fit(Gtk.ContentFit.COVER)
        pin_size(self.preview, 150, 86)
        self.preview.add_css_class("thumb")
        self.preview.set_tooltip_text("Drag me into another window")
        self._drag_source_for(self.preview, lambda: self.current())
        self.body.append(self.preview)

        meta = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4,
                       valign=Gtk.Align.CENTER)
        # Click-to-rename: a Stack flips the filename label to an entry.
        self.name_stack = Gtk.Stack()
        self.name_lbl = Gtk.Label(label="", xalign=0, wrap=False,
                                  ellipsize=3, max_width_chars=26)
        self.name_lbl.add_css_class("filename")
        self.name_lbl.set_tooltip_text("Click to rename")
        click = Gtk.GestureClick()
        click.connect("released", lambda *_: self.start_rename())
        self.name_lbl.add_controller(click)
        self.name_entry = Gtk.Entry()
        self.name_entry.add_css_class("rename")
        self.name_entry.set_max_width_chars(26)
        self.name_entry.connect("activate", self._commit_rename)
        esc = Gtk.EventControllerKey()
        esc.connect("key-pressed", self._rename_key)
        self.name_entry.add_controller(esc)
        focus = Gtk.EventControllerFocus()
        focus.connect("leave", lambda *_: self._end_rename())
        self.name_entry.add_controller(focus)
        self.name_stack.add_named(self.name_lbl, "label")
        self.name_stack.add_named(self.name_entry, "entry")
        meta.append(self.name_stack)
        hint = Gtk.Label(label="Drag the image out, click the name to rename.",
                         xalign=0, wrap=True, max_width_chars=28)
        hint.add_css_class("hint")
        meta.append(hint)
        self.body.append(meta)
        page.append(self.body)

        self.acts = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        # "Clear" lives here because the collapsed floating pill it used to
        # hang off is gone. Without it a single held screenshot could never
        # be dismissed (the fan's right-click only appears from two up), and
        # the bar module's pending count would stick.
        for label, gate, tip, cb in (
            ("Copy path", "copy", None, self.copy_path),
            ("Copy image", "copy", None, self.copy_image),
            ("Edit", "edit", None, self.open_editor),
            ("Clear", "trash", "Dismiss every screenshot in the shelf"
                               " (files on disk are untouched)",
             self.clear_all),
        ):
            b = Gtk.Button(label=label)
            b.add_css_class("act")
            if tip:
                b.set_tooltip_text(tip)
            b.connect("clicked", lambda _w, f=cb: f())
            b._gate = gate
            self.acts.append(b)
        page.append(self.acts)

        # The fan — one draggable thumbnail per recent shot.
        self.fan = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        page.append(self.fan)
        self.render()
        return page

    # ---------------- rename ----------------
    def start_rename(self):
        cur = self.current()
        if not cur:
            return
        self.name_entry.set_text(os.path.basename(cur))
        self.name_stack.set_visible_child_name("entry")
        self.name_entry.grab_focus()
        self.app.cancel_collapse()

    def _rename_key(self, _c, keyval, _code, _state):
        if keyval == Gdk.KEY_Escape:
            self._end_rename()
            return True
        return False

    def _end_rename(self):
        self.name_stack.set_visible_child_name("label")
        self.app.schedule_collapse()

    def _commit_rename(self, _entry):
        cur = self.current()
        new_name = self.name_entry.get_text().strip()
        self._end_rename()
        if not cur or not new_name or "/" in new_name:
            return
        if not new_name.endswith(".png"):
            new_name += ".png"
        if new_name == os.path.basename(cur):
            return
        dest = os.path.join(os.path.dirname(cur), new_name)
        if os.path.exists(dest):
            self.name_lbl.set_text("name taken")
            GLib.timeout_add(1200, lambda: (self.render(), False)[1])
            return
        try:
            os.rename(cur, dest)
        except OSError as e:
            print(f"sill: rename: {e}", file=sys.stderr)
            return
        # The directory monitor's RENAMED event reconciles self.shots; update
        # eagerly too so the label never shows the old name in between.
        self._replace_path(cur, dest)

    def _replace_path(self, old, new):
        forget_thumbs(old)
        self.shots = [new if p == old else p for p in self.shots]
        self.render()

    # ---------------- state ----------------
    def current(self):
        if 0 <= self.selected < len(self.shots):
            return self.shots[self.selected]
        return None

    def has_content(self):
        return bool(self.shots)

    def add_shot(self, path):
        base = os.path.basename(path)
        if not base.endswith(".png"):
            return
        # New captures match screenshot-*.png; renamed files re-enter via
        # RENAMED and may carry any name, so only gate NEW arrivals.
        if not base.startswith("screenshot-"):
            return
        if path in self.shots:
            self.shots.remove(path)
        self.shots.insert(0, path)
        del self.shots[self.max_history:]
        self.selected = 0
        self.latest_at = time.time()
        self.render()
        self.app.on_screenshot_arrived()

    def clear_all(self):
        self.shots = []
        self.selected = 0
        self.render()
        self.app.on_tab_content_changed()

    def drop_shot(self, path):
        forget_thumbs(path)
        if path in self.shots:
            self.shots.remove(path)
        self.selected = min(self.selected, max(0, len(self.shots) - 1))
        self.render()
        self.app.on_tab_content_changed()

    def trim_history(self, *_a):
        del self.shots[self.max_history:]
        self.selected = min(self.selected, max(0, len(self.shots) - 1))
        self.render()

    # ---------------- render ----------------
    def render(self):
        has = bool(self.shots)
        cur = self.current()
        self.empty_lbl.set_visible(not has)
        self.body.set_visible(has)
        self.acts.set_visible(has)
        b = self.acts.get_first_child()
        while b:
            b.set_visible(self._action_on(b._gate))
            b = b.get_next_sibling()
        self.fan.set_visible(len(self.shots) > 1)
        if not has:
            self.stamp_lbl.set_text("")
            self.app.content_changed()
            return

        self.name_lbl.set_text(os.path.basename(cur))
        self.stamp_lbl.set_text(self.stamp_of(cur))
        self.preview.set_paintable(thumb(cur, 150, 86))

        child = self.fan.get_first_child()
        while child:
            nxt = child.get_next_sibling()
            self.fan.remove(child)
            # CRASH: paintables first, then dispose -- see drop_paintables().
            drop_paintables(child)
            # MEMORY: break the widget->controller->closure->widget cycle
            # that Python's GC cannot see (see clipboard_tab.render()).
            child.run_dispose()
            child = nxt
        if len(self.shots) > 1:
            for i, path in enumerate(self.shots):
                pic = Gtk.Picture()
                pic.set_content_fit(Gtk.ContentFit.COVER)
                pin_size(pic, 58, 34)
                pic.set_paintable(thumb(path, 58, 34))
                pic.add_css_class("thumb")
                if i == self.selected:
                    pic.add_css_class("sel")
                pic.set_tooltip_text(os.path.basename(path))
                self._drag_source_for(pic, lambda p=path: p)

                g = Gtk.GestureClick()
                g.set_button(0)

                def clicked(gesture, n, x, y, idx=i, p=path):
                    if (gesture.get_current_button() == 3
                            and self._action_on("trash")):
                        self.drop_shot(p)
                    else:
                        self.selected = idx
                        self.render()
                    self.app.schedule_collapse()

                g.connect("released", clicked)
                pic.add_controller(g)
                self.fan.append(pic)
        self.app.content_changed()

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
    def _start_watch(self):
        gdir = Gio.File.new_for_path(SHOT_DIR)
        self.monitor = gdir.monitor_directory(Gio.FileMonitorFlags.WATCH_MOVES,
                                              None)
        self.monitor.set_rate_limit(200)
        self.monitor.connect("changed", self._on_dir_changed)

    def _on_dir_changed(self, _m, gfile, other, event):
        # CHANGES_DONE_HINT rather than CREATED: grim writes the PNG in
        # stages and CREATED fires while the file is still a stub.
        if event in (Gio.FileMonitorEvent.CHANGES_DONE_HINT,
                     Gio.FileMonitorEvent.MOVED_IN):
            path = gfile.get_path()
            if path:
                self.add_shot(path)
            return
        if event == Gio.FileMonitorEvent.RENAMED:
            old = gfile.get_path()
            new = other.get_path() if other else None
            if old and new and old in self.shots:
                self._replace_path(old, new)
            return
        # A file removed behind our back otherwise lingers as a ghost
        # thumbnail that silently fails to drag.
        if event in (Gio.FileMonitorEvent.DELETED,
                     Gio.FileMonitorEvent.MOVED_OUT):
            path = gfile.get_path()
            if path and path in self.shots:
                self.drop_shot(path)
