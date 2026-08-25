"""Sill theming — live Omarchy colours + font, ported from ghost-shotshelf.

The live theme is ~/.local/state/omarchy/current/theme/colors.toml, NOT the
~/.config path (which does not exist — reading it silently falls back).
omarchy-theme-set does `rm -rf current/theme && mv next current/theme`, which
destroys the directory an inner file monitor is watching, so ThemeWatch
watches the STABLE parent (~/.local/state/omarchy/current) and re-arms the
inner colors.toml monitor after every rebuild.
"""

import os
import subprocess

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, Gio, GLib, Gtk  # noqa: E402

HOME = os.path.expanduser("~")
THEME_DIR = os.path.join(HOME, ".local/state/omarchy/current/theme")

# No-theme fallbacks only — at runtime colours come from the live colors.toml.
FALLBACK = {
    "background": "#0a0a0b",
    "foreground": "#dfe3e6",
    "accent": "#8f979c",
    "lighter_background": "#16181a",
    "dark_foreground": "#565c60",
}


def read_theme():
    """Parse the *current* theme's colors.toml so Sill follows
    `omarchy theme set` instead of pinning one palette. Values are quoted
    hex strings ("#rrggbb"); tomllib handles the file directly."""
    import tomllib
    colors = dict(FALLBACK)
    path = os.path.join(THEME_DIR, "colors.toml")
    try:
        with open(path, "rb") as fh:
            raw = tomllib.load(fh)
    except (OSError, tomllib.TOMLDecodeError):
        return colors
    for k, v in raw.items():
        if isinstance(v, str) and v.startswith("#"):
            colors[k] = v
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


def css_for(c, animations=True):
    fg, bg = c["foreground"], c["background"]
    font = current_font()
    trans = (
        """
    .panel, .chip {
        transition: opacity 200ms cubic-bezier(0.22, 1, 0.36, 1),
                    transform 260ms cubic-bezier(0.22, 1, 0.36, 1);
    }
    """ if animations else "")
    return f"""
    window {{ background: transparent; }}
    * {{ font-family: "{font}", monospace; }}
    .panel, .chip {{
        background: {bg};
        border: 1px solid alpha({fg}, 0.20);
        border-radius: 12px;
    }}
    .panel {{ padding: 12px; }}
    .chip  {{ padding: 5px 10px; }}
    {trans}
    .panel, .chip {{ opacity: 1; transform: scale(1); }}
    .panel.off {{ opacity: 0; transform: scale(0.94); }}
    .chip.off  {{ opacity: 0; transform: scale(1.10); }}
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
    .tabbtn {{
        background: transparent;
        color: alpha({fg}, 0.55);
        border: none;
        border-radius: 8px;
        padding: 2px 10px;
        font-size: 11px;
        min-height: 0;
    }}
    .tabbtn:hover  {{ color: {fg}; background: alpha({fg}, 0.08); }}
    .tabbtn:checked {{
        color: {fg};
        background: alpha({fg}, 0.12);
        font-weight: bold;
    }}
    .thumb {{
        border: 1px solid alpha({fg}, 0.18);
        border-radius: 8px;
        background: alpha({fg}, 0.05);
    }}
    .thumb:hover {{ border-color: alpha({fg}, 0.55); }}
    .thumb.sel  {{ border-color: alpha({fg}, 0.70); }}
    .pinrow {{
        border: 1px solid alpha({fg}, 0.14);
        border-radius: 8px;
        padding: 6px 8px;
    }}
    .pinrow:hover {{ border-color: alpha({fg}, 0.40); background: alpha({fg}, 0.05); }}
    .pinrow.dead .filename {{ color: alpha({fg}, 0.35); }}
    .pintext {{ color: alpha({fg}, 0.80); font-size: 11px; }}
    .dropzone {{
        border: 1px dashed alpha({fg}, 0.30);
        border-radius: 8px;
        color: alpha({fg}, 0.45);
        font-size: 10px;
        padding: 14px;
    }}
    .dropzone.armed {{ border-color: alpha({fg}, 0.70); color: alpha({fg}, 0.85); }}
    entry.rename {{
        background: alpha({fg}, 0.07);
        color: {fg};
        border: 1px solid alpha({fg}, 0.30);
        border-radius: 6px;
        padding: 0 4px;
        font-size: 11px;
        min-height: 0;
        caret-color: {fg};
    }}
    """


class ThemeWatch:
    """Owns the CSS provider and the two-level theme watch."""

    def __init__(self, animations=True):
        self.css_provider = None
        self.theme_monitor = None
        self.theme_dir_monitor = None
        self._theme_id = 0
        self.animations = animations
        self.colors = dict(FALLBACK)
        self.on_change = None  # optional callback after a re-theme

    def apply(self):
        display = Gdk.Display.get_default()
        if display is None:
            return
        self.colors = read_theme()
        provider = Gtk.CssProvider()
        provider.load_from_data(css_for(self.colors, self.animations).encode())
        if self.css_provider is not None:
            Gtk.StyleContext.remove_provider_for_display(display, self.css_provider)
        Gtk.StyleContext.add_provider_for_display(
            display, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )
        self.css_provider = provider

    def start(self):
        try:
            parent = Gio.File.new_for_path(os.path.dirname(THEME_DIR))
            self.theme_dir_monitor = parent.monitor_directory(
                Gio.FileMonitorFlags.WATCH_MOVES, None
            )
            self.theme_dir_monitor.set_rate_limit(300)
            self.theme_dir_monitor.connect("changed", self._on_changed)
        except GLib.Error:
            self.theme_dir_monitor = None
        self._arm_inner()

    def _arm_inner(self):
        if self.theme_monitor is not None:
            self.theme_monitor.cancel()
            self.theme_monitor = None
        try:
            gfile = Gio.File.new_for_path(os.path.join(THEME_DIR, "colors.toml"))
            self.theme_monitor = gfile.monitor_file(
                Gio.FileMonitorFlags.WATCH_MOVES, None
            )
            self.theme_monitor.set_rate_limit(300)
            self.theme_monitor.connect("changed", self._on_changed)
        except GLib.Error:
            self.theme_monitor = None

    def _on_changed(self, *_a):
        # Coalesce the burst of events one theme swap produces.
        if self._theme_id:
            return
        self._theme_id = GLib.timeout_add(150, self._retheme)

    def _retheme(self):
        self._theme_id = 0
        self.apply()
        self._arm_inner()
        if self.on_change:
            self.on_change()
        return False
