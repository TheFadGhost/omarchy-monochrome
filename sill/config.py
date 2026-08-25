"""Sill config shim — loads ghost-settings' schema/config modules and arms a
file watch on ~/.config/ghost/settings.toml so hand-edited TOML applies live.

ghost-settings' config.py is loaded under the module name "gs_config" via
importlib (NOT `import config` — that would collide with this very module).
Its `from schema import ...` resolves because schema is loaded first under
its own name.
"""

import importlib.util
import os
import sys

GS_DIR = os.path.expanduser("~/.local/share/ghost-settings")


def _load(fname, modname):
    spec = importlib.util.spec_from_file_location(modname,
                                                  os.path.join(GS_DIR, fname))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[modname] = mod
    spec.loader.exec_module(mod)
    return mod


schema = sys.modules.get("schema") or _load("schema.py", "schema")
gs_config = sys.modules.get("gs_config") or _load("config.py", "gs_config")

CONFIG_PATH = gs_config.CONFIG


class Settings:
    """Current settings + live reload. GTK-side only (needs a main loop)."""

    def __init__(self):
        self.current, self.warnings = gs_config.load(CONFIG_PATH)
        self._apply = {}       # dotted key -> handler(value)
        self._generic = None   # fallback handler(changed_keys)
        self._monitor = None
        self._debounce = 0

    def get(self, dotted, default=None):
        return self.current.get(dotted, default)

    def on(self, dotted, handler):
        self._apply[dotted] = handler

    def on_any(self, handler):
        self._generic = handler

    # ---------------- watch ----------------
    def watch(self):
        from gi.repository import Gio
        gfile = Gio.File.new_for_path(str(CONFIG_PATH))
        # Monitoring a not-yet-existing file is fine; CREATED fires later.
        self._monitor = gfile.monitor_file(Gio.FileMonitorFlags.WATCH_MOVES, None)
        self._monitor.connect("changed", self._on_changed)

    def _on_changed(self, *_a):
        from gi.repository import GLib
        if self._debounce:
            GLib.source_remove(self._debounce)
        self._debounce = GLib.timeout_add(100, self._reload)

    def _reload(self):
        self._debounce = 0
        new, self.warnings = gs_config.load(CONFIG_PATH)
        changed = gs_config.diff(self.current, new)
        self.current = new
        unhandled = []
        for key in changed:
            if key in self._apply:
                try:
                    self._apply[key](new[key])
                except Exception as e:
                    print(f"sill: apply {key}: {e}", file=sys.stderr)
            else:
                unhandled.append(key)
        if unhandled and self._generic:
            self._generic(unhandled)
        return False


def ensure_config_file():
    """Write the fully-commented default file if none exists — the file is
    also the documentation, so first run should leave one to hand-edit."""
    if not CONFIG_PATH.exists():
        vals = dict(gs_config.defaults())
        vals["_unknown"] = {}
        gs_config.save(CONFIG_PATH, vals)
