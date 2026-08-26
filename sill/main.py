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
with a Wayland input region cutting clicks to the expanded panel — and an
EMPTY region while collapsed, so the whole canvas is click-through and
nothing at all is drawn under the bar.

The window is a fixed 560x720 transparent canvas at the top-right; Hyprland
never has to reposition it as the panel expands and collapses — only the
input region changes.
"""

import json
import os
import signal
import sys
import time

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("GLibUnix", "2.0")   # GLib.unix_signal_add is deprecated
from gi.repository import Adw, Gdk, Gio, GLib, GLibUnix, Gtk  # noqa: E402

import cairo  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config as sill_config  # noqa: E402
import theme as sill_theme  # noqa: E402
from clipboard_tab import ClipboardTab  # noqa: E402
from pinned_tab import PinnedTab  # noqa: E402
from screenshots_tab import ScreenshotsTab  # noqa: E402

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
        self._pending_written = None
        self._hovering = False
        self._hover_id = 0        # pending hover-expand delay timer
        self._hover_debounce = 0
        self._bar_zone_in = None  # last bar-hover eligibility (None = unknown)
        self._drag_count = 0      # in-flight Sill drags (blocks hover-expand)
        self._hover_monitor = None
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

        # The holder only aligns the panel inside the full-screen canvas
        # (see apply_position). The panel stays mapped even while collapsed —
        # a hidden widget is out of the layout and cannot transition — so it
        # is faded out, made non-targetable, and the surface's input region
        # is emptied instead.
        self.holder = Gtk.Overlay()
        self.apply_position()
        self.win.set_child(self.holder)

        self.shots_tab = ScreenshotsTab(self)
        self.pinned_tab = PinnedTab(self)
        self.clip_tab = ClipboardTab(self)

        self.panel = self._build_panel()
        self.holder.set_child(self.panel)
        self.panel.add_css_class("off")
        self.panel.set_can_target(False)

        motion = Gtk.EventControllerMotion()
        motion.connect("enter", self._on_enter)
        motion.connect("leave", self._on_leave)
        self.win.add_controller(motion)

        self.win.connect("notify::default-width",
                         lambda *_: self.sync_input_region())
        self.win.present()
        GLib.timeout_add(150, self._sync_region_once)

        # systemd stops the unit with SIGTERM and GApplication does not
        # handle it, so without this the process dies before do_shutdown and
        # leaves a stale count in the pending file.
        GLibUnix.signal_add(GLib.PRIORITY_DEFAULT, signal.SIGTERM,
                            self._on_sigterm)

        self._wire_settings()
        self._watch_bar_hover()
        self.content_changed()

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
        s.on("sill.position",
             lambda *_: (self.apply_position(), self._hover_reeval()))
        s.on("sill.expand_on_hover", lambda *_: self._hover_reeval())
        s.on("sill.collapse_s", lambda v: self.schedule_collapse())
        s.on("sill.screenshots.max_history", self.shots_tab.trim_history)
        s.on("general.animations", self._set_animations)
        s.on("sill.max_items", lambda *_: self.clip_tab.render())
        s.on("sill.max_age_days", lambda *_: self.clip_tab.daily_prune())
        s.on("sill.privacy.denylist", self.clip_tab.set_denylist)
        s.on("sill.keybind_toggle", lambda *_: self._sync_flags())
        s.on("sill.disable_omarchy_clipboard", lambda *_: self._sync_flags())
        s.on_any(lambda keys: self._rerender())
        s.watch()
        self._sync_flags()
        self._watch_lock()
        # TTL + orphan prune: once at startup (inside ClipboardTab.__init__)
        # and then daily (plan §4).
        GLib.timeout_add_seconds(24 * 3600, self._daily_prune)

    def _daily_prune(self):
        self.clip_tab.daily_prune()
        return True

    # ---------------- flag files (read by ~/.config/hypr/bindings.lua) ----
    # A Hyprland bind cannot read the TOML, so boolean bind-affecting
    # settings are mirrored as flag files (existence = the non-default
    # state) and bindings.lua checks them at config parse:
    #   disable-omarchy-clipboard -> hl.unbind("SUPER + CTRL + V") ONLY.
    #       The Quickshell clipboard plugin stays loaded — it owns the
    #       wl-paste watchers Sill's own tab depends on.
    #   sill-no-toggle-bind       -> SUPER+SHIFT+V not bound.
    FLAG_DIR = os.path.expanduser("~/.config/ghost/flags")

    def _sync_flags(self):
        changed = False
        for name, want in (
            ("disable-omarchy-clipboard",
             bool(self.settings.get("sill.disable_omarchy_clipboard", False))),
            ("sill-no-toggle-bind",
             not self.settings.get("sill.keybind_toggle", True)),
        ):
            path = os.path.join(self.FLAG_DIR, name)
            have = os.path.exists(path)
            if want and not have:
                os.makedirs(self.FLAG_DIR, mode=0o700, exist_ok=True)
                with open(path, "w") as f:
                    f.write("flag file read by ~/.config/hypr/bindings.lua;"
                            " written by Sill from settings.toml\n")
                changed = True
            elif have and not want:
                try:
                    os.remove(path)
                except OSError:
                    pass
                changed = True
        if changed:
            _spawn(["hyprctl", "reload"])   # binds re-evaluate the flags

    # ---------------- purge on lock (logind LockedHint) ----------------
    def _watch_lock(self):
        """Subscribe to this session's Lock signal / LockedHint property.
        Only acts when `sill.purge_on_lock` is true AT LOCK TIME, so the
        subscription is armed unconditionally and cheap."""
        try:
            mgr = Gio.DBusProxy.new_for_bus_sync(
                Gio.BusType.SYSTEM, Gio.DBusProxyFlags.NONE, None,
                "org.freedesktop.login1", "/org/freedesktop/login1",
                "org.freedesktop.login1.Manager", None)
            try:
                path = mgr.call_sync(
                    "GetSessionByPID", GLib.Variant("(u)", (os.getpid(),)),
                    Gio.DBusCallFlags.NONE, 2000, None).unpack()[0]
            except GLib.Error:
                # sill.service runs in the systemd user manager, which is
                # OUTSIDE any logind session — GetSessionByPID fails with
                # NoSessionForPID. Fall back to the seated session of our
                # uid (the graphical one; SSH sessions have no seat).
                path = None
                uid = os.getuid()
                sessions = mgr.call_sync("ListSessions", None,
                                         Gio.DBusCallFlags.NONE,
                                         2000, None).unpack()[0]
                for _sid, s_uid, _user, seat, s_path in sessions:
                    if s_uid == uid and seat:
                        path = s_path
                        break
                if path is None:
                    raise GLib.Error.new_literal(
                        Gio.io_error_quark(), "no seated session found", 0)
            self._session_proxy = Gio.DBusProxy.new_for_bus_sync(
                Gio.BusType.SYSTEM, Gio.DBusProxyFlags.NONE, None,
                "org.freedesktop.login1", path,
                "org.freedesktop.login1.Session", None)
            self._session_proxy.connect("g-signal", self._on_session_signal)
            self._session_proxy.connect("g-properties-changed",
                                        self._on_session_props)
        except GLib.Error as e:
            print(f"sill: purge-on-lock unavailable: {e}", file=sys.stderr)

    def _on_session_signal(self, _p, _sender, signal, _params):
        if signal == "Lock":
            self._maybe_purge_on_lock()

    def _on_session_props(self, _p, changed, _inv):
        if changed.unpack().get("LockedHint") is True:
            self._maybe_purge_on_lock()

    def _maybe_purge_on_lock(self):
        if not self.settings.get("sill.purge_on_lock", False):
            return
        import store_clipboard
        store_clipboard.purge()
        print("sill: purged clipboard history on session lock",
              file=sys.stderr)
        self.clip_tab.store.load(initial=True)
        self.clip_tab.render()
        self.content_changed()

    def _set_animations(self, v):
        self.themer.animations = bool(v)
        self.themer.apply()

    def _rerender(self):
        self.shots_tab.render()
        self.pinned_tab.render()
        self.content_changed()

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

        self.stack.add_named(self.clip_tab.widget, "clipboard")
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
        if self.expanded:
            self.panel.remove_css_class("off")
        else:
            self.panel.add_css_class("off")
        self.panel.set_can_target(self.expanded)
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


    # ---------------- hover-to-expand (Phase 5) ----------------
    # The ghost.barhover Quickshell service plugin samples the pointer only
    # while it is over the bar (gated on the bar's own HoverHandler state,
    # so zero wakeups at idle) and writes pointer-rest-zone transitions to
    # a tmpfs state file. Sill watches that file and applies the policy:
    # sill.expand_on_hover, sill.hover_delay_ms, position adjacency, and
    # the in-flight-drag guard. File-watch IPC on purpose -- it is STATE,
    # not an event stream: either side can restart in any order and the
    # truth is still on disk; inotify delivery (~1ms) is far below the
    # hover delay it gates. See plugins/ghost.barhover/Hover.qml for why a
    # hover surface over the bar is impossible (it would swallow the bar's
    # own move-bar drag and double-click gestures at the Wayland level).
    HOVER_STATE = os.path.join(
        os.environ.get("XDG_RUNTIME_DIR", "/tmp"), "ghost",
        "sill-hover.state")

    def _watch_bar_hover(self):
        gfile = Gio.File.new_for_path(self.HOVER_STATE)
        # Monitoring a not-yet-existing file is fine; CREATED fires later.
        # WATCH_MOVES because the plugin writes atomically (temp + rename).
        self._hover_monitor = gfile.monitor_file(
            Gio.FileMonitorFlags.WATCH_MOVES, None)
        self._hover_monitor.connect("changed", self._on_hover_file)
        GLib.idle_add(self._read_hover_state)   # adopt current state

    def _on_hover_file(self, *_a):
        if self._hover_debounce:
            GLib.source_remove(self._hover_debounce)
        self._hover_debounce = GLib.timeout_add(30, self._read_hover_state)

    def _read_hover_state(self):
        self._hover_debounce = 0
        try:
            with open(self.HOVER_STATE) as fh:
                data = json.loads(fh.read() or "{}")
        except (OSError, ValueError):
            data = {}
        if not isinstance(data, dict):
            data = {}
        in_zone = self._hover_zone_ok(data)
        if in_zone == self._bar_zone_in:
            return False
        self._bar_zone_in = in_zone
        self._cancel_hover_expand()
        if in_zone and self.settings.get("sill.expand_on_hover", True) \
                and not self.expanded and not self._drag_count:
            delay = max(0, min(2000, int(
                self.settings.get("sill.hover_delay_ms", 300))))
            self._hover_id = GLib.timeout_add(delay, self._hover_expand_now)
        return False

    def _hover_zone_ok(self, data):
        """Is the reported pointer-rest zone adjacent to the panel? The
        panel is under the bar only when its row matches the bar's edge;
        middle-row and opposite-edge positions never hover-expand
        (documented in CUSTOMISATIONS.md rather than inventing behaviour
        for them)."""
        zone = data.get("zone")
        if zone not in ("left-gap", "right-gap"):
            return False
        pos = str(self.settings.get("sill.position", "top-right"))
        row = ("top" if pos.startswith("top")
               else "bottom" if pos.startswith("bottom") else "middle")
        if row == "middle" or data.get("bar") != row:
            return False
        if pos.endswith("left"):
            return zone == "left-gap"
        if pos.endswith("right"):
            return zone == "right-gap"
        return True   # centred panel ("top"/"bottom"): either flanking gap

    def _cancel_hover_expand(self):
        if self._hover_id:
            GLib.source_remove(self._hover_id)
            self._hover_id = 0

    def _hover_expand_now(self):
        self._hover_id = 0
        if self.settings.get("sill.expand_on_hover", True) \
                and not self.expanded and not self._drag_count:
            self._pick_context_tab()
            # auto=True: sill.collapse_s folds it back like any other
            # auto-expansion; the GTK enter/leave handlers keep it open
            # while the pointer is actually inside the panel.
            self.set_expanded(True, auto=True)
        return False

    def _hover_reeval(self):
        """Settings changed under a possibly-armed hover state."""
        self._cancel_hover_expand()
        self._bar_zone_in = None    # force re-evaluation on next read
        GLib.idle_add(self._read_hover_state)

    # ---------------- drag bookkeeping ----------------
    # Tabs report their GTK drag lifecycles here. While any Sill drag is in
    # flight, auto-collapse is frozen (as before) and hover-expand is
    # blocked: expanding would re-cut the window's input region mid-drag,
    # which the input-region policy forbids (see sync_input_region).
    def drag_began(self):
        self._drag_count += 1
        self._cancel_hover_expand()
        self.cancel_collapse()

    def drag_ended(self):
        # drag-cancel and drag-end can both fire for one drag; clamp.
        self._drag_count = max(0, self._drag_count - 1)
        self.schedule_collapse()

    # ---------------- tab callbacks ----------------
    def on_screenshot_arrived(self):
        self.select_tab("screenshots")
        self.set_expanded(True, auto=True)
        self.content_changed()

    def on_pin_dropped(self):
        self.select_tab("pinned")
        if not self.expanded:
            self.set_expanded(True, auto=True)
        self.content_changed()

    def on_tab_content_changed(self):
        if not self.shots_tab.has_content() and self.expanded \
                and self.stack.get_visible_child_name() == "screenshots" \
                and self._auto_expanded:
            self.set_expanded(False)
        self.content_changed()

    # ---------------- placement ----------------
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

    # ---------------- pending-screenshot count (bar module) ----------
    # ghost-capture suppresses Omarchy's screenshot toast, so something
    # has to say a capture happened. That used to be the collapsed floating
    # pill; it is now a bar module, which reads the count from this file.
    # CONTRACT (fixed — the bar module codes against it): a single ASCII
    # integer and nothing else, written atomically; the number of
    # screenshots currently held undismissed in the Screenshots tab; 0 on
    # clean shutdown.
    PENDING_FILE = os.path.expanduser("~/.local/state/ghost/sill-pending")

    def content_changed(self):
        """Anything the panel shows changed: republish the pending count and
        re-cut the input region (the panel may have changed size with it)."""
        self.write_pending()
        self.sync_input_region_soon()

    def write_pending(self, count=None):
        """Idempotent — an unchanged count is not rewritten, so the bar's
        file monitor never wakes for a no-op (this is called from every
        render). The existence check is not redundant: the file lives in a
        shared state directory another component may clear, and without it
        an unchanged count would never re-create the file."""
        if count is None:
            count = len(self.shots_tab.shots) if self.shots_tab else 0
        count = int(count)
        if count == self._pending_written \
                and os.path.exists(self.PENDING_FILE):
            return
        try:
            os.makedirs(os.path.dirname(self.PENDING_FILE), mode=0o700,
                        exist_ok=True)
            tmp = self.PENDING_FILE + ".tmp"
            with open(tmp, "w") as fh:
                fh.write(str(count))
            os.replace(tmp, self.PENDING_FILE)   # atomic; no partial read
        except OSError as e:
            print(f"sill: pending file: {e}", file=sys.stderr)
            return
        self._pending_written = count

    def _on_sigterm(self):
        self.quit()          # runs do_shutdown, unlike a bare SIGTERM
        return GLib.SOURCE_REMOVE

    def do_shutdown(self):
        # Nothing is pending once Sill is gone; the bar must not keep
        # showing a badge for a panel that no longer exists.
        self.write_pending(0)
        Adw.Application.do_shutdown(self)

    # ---------------- input region ------------------------------------
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
        """Confine input to the panel. Without this the whole 560x720
        transparent window would swallow clicks meant for the app
        underneath. While expanded the region is the panel's FULL bounds —
        also the drop zone; it never changes mid-drag (R9-independent).
        While collapsed the region is EMPTY: the panel is still mapped (a
        hidden widget cannot transition) but invisible, and must not take a
        single click."""
        surface = self.win.get_surface() if self.win else None
        if not surface:
            return
        region = cairo.Region()
        if self.expanded:
            ok, rect = self.panel.compute_bounds(self.win)
            if ok:
                region = cairo.Region(cairo.RectangleInt(
                    int(rect.origin.x), int(rect.origin.y),
                    max(1, int(rect.size.width)),
                    max(1, int(rect.size.height)),
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
    import store_clipboard
    cs = store_clipboard.ClipStore()
    cs.load(initial=True)
    print(f"  clipboard store     {cs.state} "
          f"({cs.recognised_count}/{cs.raw_count} entries recognised)")
    flags = os.path.expanduser("~/.config/ghost/flags")
    for fname in ("disable-omarchy-clipboard", "sill-no-toggle-bind"):
        if os.path.exists(os.path.join(flags, fname)):
            print(f"  flag                {fname}")
    pend = os.path.expanduser("~/.local/state/ghost/sill-pending")
    try:
        with open(pend) as fh:
            print(f"  pending screenshots {fh.read().strip() or '(empty)'}")
    except OSError:
        print("  pending screenshots (no state file yet)")
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
        # GTK-free and instance-free on purpose: works from a keybind, a
        # lock hook or a dead session alike. A running Sill notices via its
        # file monitor and re-renders.
        import store_clipboard
        store_clipboard.purge()
        print("sill: clipboard history purged (pins untouched)")
        sys.exit(0)
    app = Sill()
    sys.exit(app.run(sys.argv))


if __name__ == "__main__":
    main()
