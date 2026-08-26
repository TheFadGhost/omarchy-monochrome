"""Sill Clipboard tab — newest-first renderer of Omarchy's clipboard store.

Interaction contract (sill-plan §1 Phase 2):
  click a row  = copy to the clipboard and close the panel
  drag a row   = union provider, the drop target chooses its format
  pin button   = copy the content into Sill's own pin store (survives
                 clipboard eviction, TTL and purges)

Type-aware rendering, kept deliberately cheap and OFFLINE:
  * a hex colour renders as a swatch — the one sanctioned exception to the
    greyscale design system, because the colour IS the content;
  * a single-line URL renders domain-bold / path-dim (parsed locally;
    NOTHING is ever fetched from the network);
  * images render as pre-scaled thumbnails (8 GB rule — never full-res).

The schema-guard banner is the anti-goal guard: if Omarchy's private store
changes shape, this tab says so in one line instead of showing a silently
empty list (plan §7, risk 1).
"""

import os
import re

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, GLib, Gtk  # noqa: E402

import providers  # noqa: E402
import store_clipboard  # noqa: E402
from screenshots_tab import drop_paintables, pin_size, thumb  # noqa: E402

HEX_RE = re.compile(r"#(?:[0-9a-fA-F]{3,4}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})\Z")
URL_RE = re.compile(r"(https?://)([^/\s]+)(\S*)\Z")

BANNERS = {
    "missing": "clipboard store missing",
    "unreadable": "clipboard store unreadable — Omarchy update? "
                  "showing session cache",
    "drift": "clipboard store format changed — Omarchy update? "
             "showing session cache",
}


class ClipboardTab:
    def __init__(self, app):
        self.app = app
        self.store = store_clipboard.ClipStore(
            denylist=app.settings.get("sill.privacy.denylist", ()))
        self.store.on_change = self._on_store_change
        self.widget = self._build()
        self.store.load(initial=True)
        self.store.watch()
        self.store.ttl_prune(self._max_age_days)
        self.render()

    # ---------------- config ----------------
    @property
    def _max_items(self):
        return max(1, int(self.app.settings.get("sill.max_items", 200)))

    @property
    def _max_age_days(self):
        return max(0, int(self.app.settings.get("sill.max_age_days", 7)))

    def set_denylist(self, values):
        self.store.denylist = list(values or ())

    def daily_prune(self):
        self.store.ttl_prune(self._max_age_days)
        self.render()

    # ---------------- store events ----------------
    def _on_store_change(self):
        self.render()
        self.app.content_changed()

    def visible_entries(self):
        """Display filter: newest `max_items` within `max_age_days`. The
        store itself is pruned separately (startup + daily tick); this
        filter is what the eye sees in between."""
        import time
        cutoff = (time.time() - self._max_age_days * 86400
                  if self._max_age_days > 0 else None)
        out = []
        for e in self.store.entries:
            if e.kind == "image" and not os.path.exists(e.payload):
                continue        # dead image: nothing to copy or drag
            if cutoff is not None and e.when and e.when < cutoff:
                continue
            out.append(e)
            if len(out) >= self._max_items:
                break
        return out

    def has_content(self):
        return bool(self.store.entries)

    # ---------------- widgets ----------------
    def _build(self):
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)

        head = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        lbl = Gtk.Label(label="CLIPBOARD", xalign=0)
        lbl.add_css_class("heading")
        lbl.set_hexpand(True)
        head.append(lbl)
        self.count_lbl = Gtk.Label(label="")
        self.count_lbl.add_css_class("stamp")
        head.append(self.count_lbl)
        purge = Gtk.Button(label="Purge")
        purge.add_css_class("act")
        purge.set_margin_start(8)
        purge.set_tooltip_text("Wipe clipboard history (pins survive)")
        purge.connect("clicked", self._on_purge)
        head.append(purge)
        page.append(head)

        self.banner = Gtk.Label(label="", xalign=0, wrap=True,
                                max_width_chars=40)
        self.banner.add_css_class("banner")
        self.banner.set_visible(False)
        page.append(self.banner)

        self.empty_lbl = Gtk.Label(
            label="Clipboard history is empty.\nCopy something.")
        self.empty_lbl.add_css_class("hint")
        self.empty_lbl.set_margin_top(18)
        self.empty_lbl.set_margin_bottom(18)
        page.append(self.empty_lbl)

        self.listbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL,
                               spacing=6)
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_max_content_height(520)
        scroll.set_propagate_natural_height(True)
        scroll.set_child(self.listbox)
        page.append(scroll)
        return page

    def _on_purge(self, *_a):
        store_clipboard.purge()
        # The file monitor also fires, but render eagerly so the purge
        # feels instant.
        self.store.load(initial=True)
        self.render()
        self.app.content_changed()

    # ---------------- render ----------------
    def render(self):
        state = self.store.state
        self.banner.set_visible(state != "ok")
        if state != "ok":
            self.banner.set_text(BANNERS.get(state, state))

        child = self.listbox.get_first_child()
        while child:
            nxt = child.get_next_sibling()
            self.listbox.remove(child)
            # MEMORY: run_dispose() is required, not optional. A row's
            # event-controller closures reference Python objects while the
            # widget (C side) holds the controller — a ref cycle crossing
            # the C boundary that Python's GC cannot traverse. Without
            # disposing, every render leaked every row (~1.7 MB/render,
            # found at 1.4 GB peak). run_dispose drops the controllers and
            # breaks the cycle deterministically.
            # CRASH: paintables first, then dispose -- see drop_paintables().
            drop_paintables(child)
            child.run_dispose()
            child = nxt

        entries = self.visible_entries()
        self.empty_lbl.set_visible(not entries and state == "ok")
        n = len(entries)
        self.count_lbl.set_text(f"{n} item" + ("" if n == 1 else "s")
                                if n else "")
        for e in entries:
            self.listbox.append(self._row_for(e))
        self.app.sync_input_region_soon()

    def _row_for(self, entry):
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        row.add_css_class("pinrow")

        # `body` (icon + labels) is the click-to-copy / drag surface; the
        # pin button sits OUTSIDE it so its click can never double as a copy.
        body = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8,
                       hexpand=True)

        if entry.kind == "image":
            self._fill_image_row(body, entry)
        else:
            self._fill_text_row(body, entry)

        row.append(body)

        pin = Gtk.Button(label="+")
        pin.add_css_class("closebtn")
        pin.set_valign(Gtk.Align.CENTER)
        pin.set_tooltip_text("Pin (survives clipboard eviction and purges)")
        pin.connect("clicked", lambda _w, e=entry: self._pin(e))
        row.append(pin)

        click = Gtk.GestureClick()
        click.connect("released",
                      lambda *_a, e=entry: self._copy_and_close(e))
        body.add_controller(click)
        self._drag_source_for(body, entry)
        row.set_tooltip_text("Click copies · drag into another window")
        return row

    def _fill_image_row(self, body, entry):
        pic = Gtk.Picture()
        pic.set_content_fit(Gtk.ContentFit.COVER)
        pin_size(pic, 58, 34)
        pic.add_css_class("thumb")
        pic.set_paintable(thumb(entry.payload, 58, 34))
        body.append(pic)

        col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1,
                      valign=Gtk.Align.CENTER, hexpand=True)
        kind = ("Screenshot" if entry.get("mime") == "image/png"
                else "Image")
        title = Gtk.Label(label=kind, xalign=0)
        title.add_css_class("filename")
        col.append(title)
        # capturedAt is display-only upstream; display is exactly what a
        # subtitle needs.
        sub_bits = [b for b in (entry.get("display_at"),
                                entry.get("mime")) if b]
        if sub_bits:
            sub = Gtk.Label(label=" · ".join(sub_bits), xalign=0,
                            ellipsize=3, max_width_chars=34)
            sub.add_css_class("hint")
            col.append(sub)
        body.append(col)

    def _fill_text_row(self, body, entry):
        text = entry.payload
        stripped = text.strip()

        if HEX_RE.fullmatch(stripped):
            body.append(self._swatch(stripped))
            lbl = Gtk.Label(label=stripped, xalign=0, hexpand=True,
                            valign=Gtk.Align.CENTER)
            lbl.add_css_class("filename")
            body.append(lbl)
            return

        m = URL_RE.fullmatch(stripped) if "\n" not in stripped else None
        if m:
            g = Gtk.Label(label="🔗")
            g.add_css_class("pintext")
            g.set_size_request(24, -1)
            body.append(g)
            col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1,
                          valign=Gtk.Align.CENTER, hexpand=True)
            dom = Gtk.Label(label=m.group(2), xalign=0, ellipsize=3,
                            max_width_chars=32)
            dom.add_css_class("filename")
            dom.add_css_class("urldomain")
            col.append(dom)
            if m.group(3):
                path = Gtk.Label(label=m.group(3), xalign=0, ellipsize=3,
                                 max_width_chars=34)
                path.add_css_class("hint")
                col.append(path)
            body.append(col)
            return

        g = Gtk.Label(label="❝")
        g.add_css_class("pintext")
        g.set_size_request(24, -1)
        body.append(g)
        col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1,
                      valign=Gtk.Align.CENTER, hexpand=True)
        lines = stripped.splitlines() or [""]
        title = Gtk.Label(label=lines[0][:200], xalign=0, ellipsize=3,
                          max_width_chars=32)
        title.add_css_class("filename")
        col.append(title)
        if len(lines) > 1 or len(text) > 80:
            sub = Gtk.Label(
                label=f"{len(text)} chars · {len(lines)} lines"
                if len(lines) > 1 else f"{len(text)} chars",
                xalign=0)
            sub.add_css_class("hint")
            col.append(sub)
        body.append(col)

    @staticmethod
    def _swatch(hex_code):
        """The colour exception: the swatch shows the copied colour itself.
        Everything around it stays greyscale."""
        area = Gtk.DrawingArea()
        area.set_content_width(36)
        area.set_content_height(24)
        area.add_css_class("thumb")
        rgba = Gdk.RGBA()
        if not rgba.parse(hex_code):
            rgba.parse("#808080")

        def draw(_area, cr, w, h):
            cr.set_source_rgba(rgba.red, rgba.green, rgba.blue, rgba.alpha)
            cr.rectangle(0, 0, w, h)
            cr.fill()

        area.set_draw_func(draw)
        area.set_valign(Gtk.Align.CENTER)
        return area

    # ---------------- actions ----------------
    def _copy_and_close(self, entry):
        clipboard = Gdk.Display.get_default().get_clipboard()
        if entry.kind == "image":
            try:
                clipboard.set(Gdk.Texture.new_from_filename(entry.payload))
            except GLib.Error:
                return
        else:
            clipboard.set(entry.payload)
        # Omarchy's watcher re-captures our copy and dedupes it to the top
        # of the store — that reordering is normal clipboard-manager
        # behaviour, not a bug.
        self.app.set_expanded(False)

    def _pin(self, entry):
        if entry.kind == "image":
            try:
                with open(entry.payload, "rb") as f:
                    self.app.pinned_tab.store.add_image_bytes(f.read())
            except OSError:
                return
        else:
            self.app.pinned_tab.store.add_text(entry.payload)
        self.app.pinned_tab.render()
        self.app.content_changed()

    # ---------------- drag-out ----------------
    def _drag_source_for(self, widget, entry):
        src = Gtk.DragSource()
        src.set_actions(Gdk.DragAction.COPY)

        def prepare(_s, _x, _y):
            try:
                if entry.kind == "image":
                    # Union: uri-list + portal + image/* + path text.
                    return providers.for_image_file(entry.payload)
                return providers.for_text(entry.payload)
            except Exception:
                return None

        def begin(s, _drag):
            # s.get_widget(), NOT a captured `widget`: capturing the widget
            # in a controller closure recreates the uncollectable
            # widget->controller->closure->widget cycle (see render()).
            s.set_icon(Gtk.WidgetPaintable.new(s.get_widget()), 24, 12)
            self.app.drag_began()

        src.connect("prepare", prepare)
        src.connect("drag-begin", begin)
        src.connect("drag-end", lambda *_: self.app.drag_ended())
        src.connect("drag-cancel", lambda *_: (self.app.drag_ended(),
                                               False)[1])
        widget.add_controller(src)
