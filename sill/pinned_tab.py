"""Sill Pinned tab — the drag-in stash.

Drop targets are built with the verified pattern:

    Gtk.DropTarget.new(GObject.TYPE_NONE, Gdk.DragAction.COPY)
    dt.set_gtypes([Gdk.FileList, Gdk.Texture, GObject.TYPE_STRING])

NOTE: on such a target get_formats().get_mime_types() is EMPTY BY DESIGN
(gtypes, not mimes) — do not treat that as a failure.

Order matters: FileList first, so a browser image drag that offers both a
URL string and image data lands as the richest type it can. Text is last.

INPUT-REGION POLICY (the R9-independent design): the drop zone never grows
mid-drag. While the panel is open, the app keeps the input region at the
panel's full expanded size; while collapsed the input region is EMPTY, Sill
takes no input at all, and there is therefore NO collapsed drop target --
open the panel first. Trade-off: no drop area when collapsed, in exchange
for not depending on undefined compositor behaviour (whether
set_input_region applies to an in-flight drag).
"""

import os

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, GLib, GObject, Gtk  # noqa: E402

import providers  # noqa: E402
from screenshots_tab import drop_paintables, pin_size, thumb  # noqa: E402
from store_pins import PinStore  # noqa: E402


class PinnedTab:
    def __init__(self, app):
        self.app = app
        self.store = PinStore()
        self.widget = self._build()
        self.render()

    # ---------------- drop-in ----------------
    def make_drop_target(self, on_armed=None):
        """A DropTarget accepting files, images and text; attach anywhere."""
        dt = Gtk.DropTarget.new(GObject.TYPE_NONE, Gdk.DragAction.COPY)
        dt.set_gtypes([Gdk.FileList, Gdk.Texture, GObject.TYPE_STRING])
        dt.connect("drop", self._on_drop)
        if on_armed:
            dt.connect("enter", lambda *_: (on_armed(True),
                                            Gdk.DragAction.COPY)[1])
            dt.connect("leave", lambda *_: on_armed(False))
        return dt

    def _on_drop(self, _dt, value, _x, _y):
        added = None
        if isinstance(value, Gdk.FileList):
            for gfile in value.get_files():
                path = gfile.get_path()
                if path:
                    added = self.store.add_file(path) or added
        elif isinstance(value, Gdk.Texture):
            try:
                png = value.save_to_png_bytes().get_data()
            except Exception:
                return False
            added = self.store.add_image_bytes(bytes(png))
        elif isinstance(value, str):
            added = self.store.add_text(value)
        else:
            return False
        self.render()
        self.app.on_pin_dropped()
        return added is not None

    # ---------------- drag-out ----------------
    def _provider_for(self, pin):
        if pin.kind == "image":
            # Union: uri-list + portal + image/* + text — target chooses.
            return providers.for_image_file(pin.payload)
        if pin.kind == "file":
            if pin.alive():
                if pin.payload.lower().endswith(
                        (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif")):
                    return providers.for_image_file(pin.payload)
                return providers.union([providers.for_file(pin.payload),
                                        providers.for_text(pin.payload)])
            # Dead path: still draggable, as text.
            return providers.for_text(pin.payload)
        content = pin.text_content()
        return providers.for_text(content if content is not None else pin.title)

    def _drag_source_for(self, widget, pin):
        src = Gtk.DragSource()
        src.set_actions(Gdk.DragAction.COPY)

        def prepare(_s, _x, _y):
            try:
                return self._provider_for(pin)
            except Exception:
                return None

        def begin(s, _drag):
            # s.get_widget(), NOT a captured `widget` — a controller closure
            # must never reference the widget it is attached to (leak; see
            # clipboard_tab.render()).
            s.set_icon(Gtk.WidgetPaintable.new(s.get_widget()), 24, 12)
            self.app.drag_began()

        src.connect("prepare", prepare)
        src.connect("drag-begin", begin)
        src.connect("drag-end", lambda *_: self.app.drag_ended())
        src.connect("drag-cancel", lambda *_: (self.app.drag_ended(),
                                               False)[1])
        widget.add_controller(src)

    # ---------------- widgets ----------------
    def _build(self):
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)

        head = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        lbl = Gtk.Label(label="PINNED", xalign=0)
        lbl.add_css_class("heading")
        lbl.set_hexpand(True)
        head.append(lbl)
        self.count_lbl = Gtk.Label(label="")
        self.count_lbl.add_css_class("stamp")
        head.append(self.count_lbl)
        page.append(head)

        self.dropzone = Gtk.Label(
            label="Drop files, images or text here to pin them")
        self.dropzone.add_css_class("dropzone")

        def armed(on):
            (self.dropzone.add_css_class if on
             else self.dropzone.remove_css_class)("armed")

        self.dropzone.add_controller(self.make_drop_target(armed))
        page.append(self.dropzone)

        self.listbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_max_content_height(320)
        scroll.set_propagate_natural_height(True)
        scroll.set_child(self.listbox)
        page.append(scroll)
        return page

    def has_content(self):
        return bool(self.store.pins)

    def render(self):
        child = self.listbox.get_first_child()
        while child:
            nxt = child.get_next_sibling()
            self.listbox.remove(child)
            # MEMORY: break the widget->controller->closure->widget cycle
            # that Python's GC cannot see (see clipboard_tab.render()).
            # CRASH: paintables first, then dispose -- see drop_paintables().
            drop_paintables(child)
            child.run_dispose()
            child = nxt
        n = len(self.store.pins)
        self.count_lbl.set_text(f"{n} pinned" if n else "")
        for pin in self.store.pins:
            self.listbox.append(self._row_for(pin))
        self.app.sync_input_region_soon()

    def _row_for(self, pin):
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        row.add_css_class("pinrow")
        alive = pin.alive()
        if not alive:
            row.add_css_class("dead")

        if pin.kind == "image" or (
                pin.kind == "file" and alive and pin.payload.lower().endswith(
                    (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"))):
            ic = Gtk.Picture()
            ic.set_content_fit(Gtk.ContentFit.COVER)
            pin_size(ic, 44, 26)
            ic.add_css_class("thumb")
            ic.set_paintable(thumb(pin.payload, 44, 26))
            row.append(ic)
        else:
            glyph = {"text": "❝", "file": "🗎"}.get(pin.kind, "•")
            g = Gtk.Label(label=glyph)
            g.add_css_class("pintext")
            g.set_size_request(24, -1)
            row.append(g)

        col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1,
                      valign=Gtk.Align.CENTER, hexpand=True)
        title = Gtk.Label(label=pin.title, xalign=0, ellipsize=3,
                          max_width_chars=30)
        title.add_css_class("filename")
        col.append(title)
        if pin.kind == "file":
            sub = Gtk.Label(label=pin.payload if alive
                            else f"{pin.payload} · missing",
                            xalign=0, ellipsize=1, max_width_chars=34)
            sub.add_css_class("hint")
            col.append(sub)
        elif pin.kind == "text":
            content = pin.text_content() or ""
            lines = content.strip().splitlines()
            if len(lines) > 1 or len(content) > 60:
                sub = Gtk.Label(label=f"{len(content)} chars", xalign=0)
                sub.add_css_class("hint")
                col.append(sub)
        row.append(col)

        unpin = Gtk.Button(label="✕")
        unpin.add_css_class("closebtn")
        unpin.set_valign(Gtk.Align.CENTER)
        unpin.set_tooltip_text("Unpin")
        unpin.connect("clicked", lambda _w, p=pin: self._unpin(p))
        row.append(unpin)

        row.set_tooltip_text("Drag out · ✕ unpins")
        self._drag_source_for(row, pin)
        return row

    def _unpin(self, pin):
        self.store.remove(pin)
        self.render()
        self.app.on_tab_content_changed()
