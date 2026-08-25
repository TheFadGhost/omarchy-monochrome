#!/usr/bin/env python3
"""Sill — one panel merging screenshot history and a pinned drag-stash
(clipboard history lands in Phase 2). GTK4/Adwaita, single instance
(dev.ghost.sill), faked bar attachment below y=44.

WHY A GTK4 TOPLEVEL AND NOT A QUICKSHELL PLUGIN / LAYER SURFACE
---------------------------------------------------------------
The whole point is dragging content in and out. QtQuick's Drag is
scene-local (no External type), and a drag must not originate from a
wlr-layer-shell surface (wlroots validates against pointer-button serial +
pointer focus; KWin bug 502497). omarchy-bar is layer-shell at level `top`
and stacks above all toplevels, so Sill is an ordinary xdg_toplevel pinned
just below the bar line by Hyprland rules in ~/.config/hypr/windows.lua,
with a Wayland input region cutting clicks to the visible chip/panel.

The window is a fixed 560x720 transparent canvas at the top-right; Hyprland
never has to reposition it as the panel expands and collapses — only the
input region changes.
"""

import os
import sys
import time

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gio, GLib, Gtk  # noqa: E402

import cairo  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config as sill_config  # noqa: E402
import theme as sill_theme  # noqa: E402
from pinned_tab import PinnedTab  # noqa: E402
from screenshots_tab import ScreenshotsTab, pin_size, thumb  # noqa: E402

APP_ID = "dev.ghost.sill"
WIN_W, WIN_H = 560, 720  # panel footprint; the canvas itself is full-screen

# Nine-point placement. The window is a full-screen transparent canvas and the
# panel is aligned inside it, because Hyprland cannot move an unfocused window:
# `hl.dsp.window.move` acts on the FOCUSED window and ignores a window selector,
# and Sill deliberately never takes focus. Aligning GTK-side also makes a
# position change instant instead of needing a remap.
POSITIONS = {
    "top-left":      (Gtk.Align.START,  Gtk.Align.START),
    "top":           (Gtk.Align.CENTER, Gtk.Align.START),
    "top-right":     (Gtk.Align.END,    Gtk.Align.START),
    "left":          (Gtk.Align.START,  Gtk.Align.CENTER),
    "center":        (Gtk.Align.CENTER, Gtk.Align.CENTER),
    "right":         (Gtk.Align.END,    Gtk.Align.CENTER),
    "bottom-left":   (Gtk.Align.START,  Gtk.Align.END),
    "bottom":        (Gtk.Align.CENTER, Gtk.Align.END),
    "bottom-right":  (Gtk.Align.END,    Gtk.Align.END),
}
BAR_CLEARANCE = 46  # reserved top (44) + 2; only applied to the top row
def _spawn(argv):
    """Fire-and-forget. GLib.spawn_async keeps this off the GTK main loop; a
    blocking subprocess here would stall the UI on every settings change."""
    try:
        GLib.spawn_async(argv, flags=GLib.SpawnFlags.SEARCH_PATH
                         | GLib.SpawnFlags.DO_NOT_REAP_CHILD)
    except GLib.Error as exc:
        print("sill: spawn failed: %s" % exc, file=sys.stderr)


RULE_FILE = os.path.expanduser("~/.config/hypr/sill-position.lua")

# Hyprland move expressions per position. The canvas is fixed-size and the
# window is non-resizable, so a size rule would be refused by the client and
# Hyprland drops the paired move with it -- the window then lands centred.
# Placement therefore has to come from the rule, regenerated on change.
def _move_expr(pos, m):
    x = {"left": str(m), "center": "(monitor_w-%d)/2" % WIN_W,
         "right": "(monitor_w-%d-%d)" % (WIN_W, m)}
    y = {"top": str(BAR_CLEARANCE), "middle": "(monitor_h-%d)/2" % WIN_H,
         "bottom": "(monitor_h-%d-%d)" % (WIN_H, m)}
    col = "left" if pos.endswith("left") else "right" if pos.endswith("right") else "center"
    if pos in ("left", "center", "right"):
        col, row = pos, "middle"
    else:
        row = "top" if pos.startswith("top") else "bottom" if pos.startswith("bottom") else "middle"
    return x[col], y[row]


class Sill(Adw.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID,
                         flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE)
        self.win = None
        self.expanded = False
        self._auto_expanded = False
        self._collapse_id = 0
        self._region_id = 0
        self._hovering = False
        self._last_tab = "screenshots"
        self.settings = None
        self.themer = None
        self.shots_tab = None
        self.pinned_tab = None

    # ---------------- lifecycle ----------------
    def do_command_line(self, cmdline):
        args = cmdline.get_arguments()[1:]
        self.activate()
        if "toggle" in args:
            self.toggle_panel()
        elif "show" in args:
            # `sill show [clipboard|screenshots|pinned]` — open on a tab.
            i = args.index("show")
            tab = args[i + 1] if i + 1 < len(args) else self._last_tab
            if tab in self._tab_buttons:
                self.select_tab(tab)
            self.set_expanded(True, auto=False)
        return 0

    def do_activate(self):
        if self.win:
            return

        sill_config.ensure_config_file()
        self.settings = sill_config.Settings()
        for w in self.settings.warnings:
            print(f"sill: config: {w}", file=sys.stderr)

        self.themer = sill_theme.ThemeWatch(
            animations=bool(self.settings.get("general.animations", True)))
        self.themer.apply()
        self.themer.start()

        self._write_pidfile()

        self.win = Gtk.ApplicationWindow(application=self)
        self.win.set_decorated(False)
        self.win.set_default_size(WIN_W, WIN_H)
        self.win.set_resizable(False)

        # Overlay, not Box: panel and chip occupy the SAME spot so one can
        # scale into the other; both stay mapped (a hidden widget is out of
        # the layout and cannot transition) and the inactive one is made
        # non-targetable so it never eats a click.
        self.holder = Gtk.Overlay()
        self.apply_position()
        self.win.set_child(self.holder)

        self.shots_tab = ScreenshotsTab(self)
        self.pinned_tab = PinnedTab(self)

        self.panel = self._build_panel()
        self.chip = self._build_chip()
        self.holder.set_child(self.panel)
        self.holder.add_overlay(self.chip)
        self.panel.add_css_class("off")
        self.panel.set_can_target(False)
        self.chip.set_can_target(True)

        motion = Gtk.EventControllerMotion()
        motion.connect("enter", self._on_enter)
        motion.connect("leave", self._on_leave)
        self.win.add_controller(motion)

        self.win.connect("notify::default-width",
                         lambda *_: self.sync_input_region())
        self.win.present()
        GLib.timeout_add(150, self._sync_region_once)

        self._wire_settings()
        self.update_chip()

    def _write_pidfile(self):
        run = os.environ.get("XDG_RUNTIME_DIR", "/tmp")
        d = os.path.join(run, "ghost")
        try:
            os.makedirs(d, mode=0o700, exist_ok=True)
            with open(os.path.join(d, "sill.pid"), "w") as f:
                f.write(str(os.getpid()))
        except OSError:
            pass

    def _wire_settings(self):
        s = self.settings
        s.on("sill.margin", lambda *_: self.apply_position())
        s.on("sill.position", lambda *_: self.apply_position())
        s.on("sill.collapse_s", lambda v: self.schedule_collapse())
        s.on("sill.screenshots.max_history", self.shots_tab.trim_history)
        s.on("general.animations", self._set_animations)
        s.on_any(lambda keys: self._rerender())
        s.watch()

    def _set_animations(self, v):
        self.themer.animations = bool(v)
        self.themer.apply()

    def _rerender(self):
        self.shots_tab.render()
        self.pinned_tab.render()
        self.update_chip()

    # ---------------- panel ----------------
    def _build_panel(self):
        panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        panel.add_css_class("panel")
        panel.set_size_request(430, -1)
        panel.set_halign(Gtk.Align.END)
        panel.set_valign(Gtk.Align.START)

        bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self.stack.set_transition_duration(120)
        self._tab_buttons = {}
        group = None
        for name, label in (("clipboard", "Clipboard"),
                            ("screenshots", "Screenshots"),
                            ("pinned", "Pinned")):
            b = Gtk.ToggleButton(label=label)
            b.add_css_class("tabbtn")
            if group:
                b.set_group(group)
            else:
                group = b
            b.connect("toggled", self._on_tab_toggled, name)
            self._tab_buttons[name] = b
            bar.append(b)
        spacer = Gtk.Box(hexpand=True)
        bar.append(spacer)
        close = Gtk.Button(label="✕")
        close.add_css_class("closebtn")
        close.set_tooltip_text("Collapse")
        close.connect("clicked", lambda *_: self.set_expanded(False))
        bar.append(close)
        panel.append(bar)

        clip_page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        h = Gtk.Label(label="CLIPBOARD", xalign=0)
        h.add_css_class("heading")
        clip_page.append(h)
        stub = Gtk.Label(
            label="Clipboard history lands in Phase 2.\n"
                  "Until then SUPER+CTRL+V opens Omarchy's own manager.")
        stub.add_css_class("hint")
        stub.set_margin_top(18)
        stub.set_margin_bottom(18)
        clip_page.append(stub)

        self.stack.add_named(clip_page, "clipboard")
        self.stack.add_named(self.shots_tab.widget, "screenshots")
        self.stack.add_named(self.pinned_tab.widget, "pinned")
        panel.append(self.stack)

        # The whole panel is a drop target while open — its input region is
        # the panel's full size, fixed for the duration (never grown
        # mid-drag; see pinned_tab.py's input-region policy note).
        panel.add_controller(self.pinned_tab.make_drop_target())

        self.select_tab("screenshots")
        return panel

    def _on_tab_toggled(self, button, name):
        if button.get_active():
            self.stack.set_visible_child_name(name)
            self._last_tab = name
            self.sync_input_region_soon()

    def select_tab(self, name):
        self._tab_buttons[name].set_active(True)

    # ---------------- chip ----------------
    def _build_chip(self):
        chip = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        chip.add_css_class("chip")
        chip.set_halign(Gtk.Align.END)
        chip.set_valign(Gtk.Align.START)

        self.chip_thumb = Gtk.Picture()
        self.chip_thumb.set_content_fit(Gtk.ContentFit.COVER)
        pin_size(self.chip_thumb, 34, 20)
        self.chip_thumb.add_css_class("thumb")
        self.shots_tab._drag_source_for(self.chip_thumb,
                                        lambda: self.shots_tab.current())
        chip.append(self.chip_thumb)

        self.chip_lbl = Gtk.Label(label="Sill")
        self.chip_lbl.add_css_class("filename")
        chip.append(self.chip_lbl)

        # ✕ appears on hover only.
        self.chip_close = Gtk.Button(label="✕")
        self.chip_close.add_css_class("closebtn")
        self.chip_close.set_tooltip_text("Clear screenshots")
        self.chip_close.set_visible(False)
        self.chip_close.connect("clicked", self._on_chip_close)
        chip.append(self.chip_close)

        hover = Gtk.EventControllerMotion()
        hover.connect("enter", lambda *_: self.chip_close.set_visible(True))
        hover.connect("leave", lambda *_: self.chip_close.set_visible(False))
        chip.add_controller(hover)

        click = Gtk.GestureClick()
        click.set_button(0)
        click.connect("released", self._on_chip_click)
        chip.add_controller(click)

        # Collapsed drop-in: the chip itself is the (chip-sized) drop zone.
        chip.add_controller(self.pinned_tab.make_drop_target(
            lambda on: (chip.add_css_class if on
                        else chip.remove_css_class)("armed")))
        return chip

    def _on_chip_click(self, gesture, _n, _x, _y):
        if gesture.get_current_button() == 3:
            self.shots_tab.clear_all()
            return
        if self.settings.get("sill.expand_on_click", True):
            self._pick_context_tab()
            self.set_expanded(True, auto=False)

    def _on_chip_close(self, *_a):
        self.shots_tab.clear_all()

    def update_chip(self):
        shots = self.shots_tab.shots
        pins = self.pinned_tab.store.pins
        cur = self.shots_tab.current()
        self.chip_thumb.set_visible(bool(cur))
        if cur:
            self.chip_thumb.set_paintable(thumb(cur, 34, 20))
        parts = []
        if shots:
            parts.append(f"{len(shots)} shot" + ("s" if len(shots) > 1 else ""))
        if pins:
            parts.append(f"{len(pins)} pinned")
        self.chip_lbl.set_text(" · ".join(parts) if parts else "Sill")
        self.sync_input_region_soon()

    # ---------------- expand / collapse ----------------
    def toggle_panel(self):
        if self.expanded:
            self.set_expanded(False)
        else:
            self._pick_context_tab()
            self.set_expanded(True, auto=False)

    def _pick_context_tab(self):
        # Context-aware default: fresh screenshot -> Screenshots;
        # otherwise the last tab used.
        if time.time() - self.shots_tab.latest_at < 60:
            self.select_tab("screenshots")
        else:
            self.select_tab(self._last_tab)

    def set_expanded(self, want, auto=False):
        if want == self.expanded:
            if want and auto:
                self._auto_expanded = True
                self.schedule_collapse()
            return
        self.expanded = want
        self._auto_expanded = auto if want else False
        self._apply_state()
        if want and auto:
            self.schedule_collapse()

    def _apply_state(self):
        showing, hiding = ((self.panel, self.chip) if self.expanded
                           else (self.chip, self.panel))
        showing.remove_css_class("off")
        hiding.add_css_class("off")
        showing.set_can_target(True)
        hiding.set_can_target(False)
        # Re-cut the input region once the motion settles on its new size.
        GLib.timeout_add(280, self._sync_region_once)
        self.sync_input_region()

    def schedule_collapse(self):
        """Arm the auto-collapse timer — only for auto-expanded panels; a
        panel the user opened stays until they close it."""
        self.cancel_collapse()
        if not (self.expanded and self._auto_expanded):
            return
        secs = int(self.settings.get("sill.collapse_s", 15))
        if secs <= 0:
            return  # 0 = never auto-collapse
        self._collapse_id = GLib.timeout_add(secs * 1000, self._collapse_now)

    def cancel_collapse(self):
        if self._collapse_id:
            GLib.source_remove(self._collapse_id)
            self._collapse_id = 0

    def _collapse_now(self):
        self._collapse_id = 0
        if not self._hovering:
            self.set_expanded(False)
        return False

    def _on_enter(self, *_a):
        self._hovering = True
        self.cancel_collapse()

    def _on_leave(self, *_a):
        self._hovering = False
        if self.expanded:
            self.schedule_collapse()

    # ---------------- tab callbacks ----------------
    def on_screenshot_arrived(self):
        self.select_tab("screenshots")
        self.set_expanded(True, auto=True)
        self.update_chip()

    def on_pin_dropped(self):
        self.select_tab("pinned")
        if not self.expanded:
            self.set_expanded(True, auto=True)
        self.update_chip()

    def on_tab_content_changed(self):
        if not self.shots_tab.has_content() and self.expanded \
                and self.stack.get_visible_child_name() == "screenshots" \
                and self._auto_expanded:
            self.set_expanded(False)
        self.update_chip()

    # ---------------- input region ----------------
    def apply_position(self):
        """Place the panel at one of the nine points. Called on startup and on
        every settings change, so editing the TOML moves it immediately."""
        name = str(self.settings.get("sill.position", "top-right"))
        if name not in POSITIONS:
            name = "top-right"
        halign, valign = POSITIONS[name]
        margin = max(0, min(128, int(self.settings.get("sill.margin", 10))))

        # Align inside the canvas so the panel hugs the screen-facing corner.
        self.holder.set_halign(halign)
        self.holder.set_valign(valign)
        for setter in (self.holder.set_margin_start, self.holder.set_margin_end,
                       self.holder.set_margin_top, self.holder.set_margin_bottom):
            setter(0)   # the rule owns the offset; margins here would double it

        mx, my = _move_expr(name, margin)
        rule = (
            "-- Generated by Sill. Edit `sill.position` / `sill.margin` in\n"
            "-- ~/.config/ghost/settings.toml instead; Sill rewrites this file.\n"
            'o.window("^dev\\\\.ghost\\\\.sill$", {\n'
            '  size = { "%d", "%d" },\n'
            '  move = { "%s", "%s" },\n'
            "})\n" % (WIN_W, WIN_H, mx, my))
        try:
            with open(RULE_FILE) as fh:
                unchanged = fh.read() == rule
        except OSError:
            unchanged = False
        if not unchanged:
            tmp = RULE_FILE + ".tmp"
            with open(tmp, "w") as fh:
                fh.write(rule)
            os.replace(tmp, RULE_FILE)          # atomic; no partial read by Hyprland
            _spawn(["hyprctl", "reload"])
            # A rule only applies at map time, so bounce the surface to re-place it.
            GLib.timeout_add(400, self._remap)
        self.sync_input_region_soon()

    def _remap(self):
        if self.win and self.win.get_visible():
            self.win.set_visible(False)
            GLib.timeout_add(80, lambda: (self.win.set_visible(True), False)[1])
        return False

    def sync_input_region_soon(self):
        if self._region_id:
            return
        self._region_id = GLib.timeout_add(60, self._sync_region_debounced)

    def _sync_region_debounced(self):
        self._region_id = 0
        self.sync_input_region()
        return False

    def _sync_region_once(self):
        self.sync_input_region()
        return False

    def sync_input_region(self):
        """Confine input to the visible chip/panel. Without this the whole
        560x720 transparent window would swallow clicks meant for the app
        underneath. While expanded the region is the panel's FULL bounds —
        also the drop zone; it never changes mid-drag (R9-independent)."""
        surface = self.win.get_surface() if self.win else None
        if not surface:
            return
        target = self.panel if self.expanded else self.chip
        ok, rect = target.compute_bounds(self.win)
        region = cairo.Region()
        if ok:
            region = cairo.Region(cairo.RectangleInt(
                int(rect.origin.x), int(rect.origin.y),
                max(1, int(rect.size.width)), max(1, int(rect.size.height)),
            ))
        try:
            surface.set_input_region(region)
        except Exception:
            pass


# ---------------- CLI (non-app subcommands) ----------------

def doctor(self_test=False):
    import glob
    print(f"sill doctor · {time.strftime('%F %T')}")
    unit = os.popen("systemctl --user is-active sill.service 2>/dev/null").read().strip()
    print(f"  sill.service        {unit or 'unknown'}")
    watchers = os.popen("pgrep -af 'wl-paste.*--watch' 2>/dev/null").read().strip()
    n = len([l for l in watchers.splitlines() if "capture.sh" in l])
    print(f"  clipboard watchers  {n} (want 2)")
    store = os.path.expanduser("~/.local/state/omarchy/clipboard-history.json")
    print(f"  clipboard store     {'present' if os.path.exists(store) else 'MISSING'}")
    cfg = os.path.expanduser("~/.config/ghost/settings.toml")
    print(f"  settings.toml       {'present' if os.path.exists(cfg) else 'absent (defaults)'}")
    rc = 0
    if self_test:
        gi.require_version("Gtk", "4.0")
        from gi.repository import Gtk as _Gtk
        _Gtk.init()
        import providers
        samples = (glob.glob(os.path.expanduser(
            "~/.local/state/omarchy/clipboard-images/*.png"))
            or glob.glob(os.path.join(
                os.environ.get("OMARCHY_SCREENSHOT_DIR")
                or os.environ.get("XDG_PICTURES_DIR")
                or os.path.expanduser("~/Pictures"), "*.png")))
        failures = providers.self_test(samples[0] if samples else None)
        if failures:
            rc = 1
            for f in failures:
                print(f"  provider self-test  FAIL: {f}")
        else:
            print("  provider self-test  ok (text/file"
                  + ("/image/union" if samples else " — no sample image")
                  + " mimes on the wire)")
    return rc


def main():
    argv = sys.argv[1:]
    if argv and argv[0] == "doctor":
        sys.exit(doctor(self_test="--self-test" in argv))
    if argv and argv[0] == "purge":
        print("sill purge ships with the Clipboard tab (Phase 2).",
              file=sys.stderr)
        sys.exit(2)
    app = Sill()
    sys.exit(app.run(sys.argv))


if __name__ == "__main__":
    main()
