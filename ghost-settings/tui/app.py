"""ghost-settings app — curses bootstrap, event loop, screen stack, resize.

Rendering is unconditional full-redraw per event; curses diffs internally.
Modals push onto the stack; input goes to the top, unconsumed keys fall
through to the globals (q ? Tab s).
"""

import curses
import locale
import os
import tomllib
from pathlib import Path

import config as gs_config
import schema
import theme
from tui import draw
from tui.draw import Rect, put
from tui.screens import Confirm, Help, MainScreen, Recovery


class App:
    def __init__(self, stdscr):
        self.stdscr = stdscr
        self.running = True
        self.flash = ""
        self.needs_write = False
        self.mode = "full"
        self.saved, self.warnings = gs_config.load(gs_config.CONFIG)
        self.staged = dict(self.saved)
        self.disk_sig = self._file_sig()
        clamped = [w for w in self.warnings if "clamped" in w]
        self.clamp_note = f"{len(clamped)} values clamped" if clamped else ""
        self.stack: list = [MainScreen(self)]
        err = self._parse_error()
        if err:
            self.needs_write = True
            self.stack.append(Recovery(self, err))
        self.relayout()

    # ---------------- state
    @staticmethod
    def _parse_error():
        try:
            with open(gs_config.CONFIG, "rb") as f:
                tomllib.load(f)
        except FileNotFoundError:
            return None
        except (OSError, tomllib.TOMLDecodeError) as e:
            return str(e)
        return None

    @staticmethod
    def _file_sig():
        try:
            st = gs_config.CONFIG.stat()
            return (st.st_mtime_ns, st.st_size)
        except OSError:
            return None

    def unsaved_keys(self):
        return [k for k in self.staged
                if k != "_unknown" and self.staged[k] != self.saved.get(k)]

    def stage(self, dotted, value):
        _sec, fld = schema.field_for(dotted)
        v = gs_config.clamp_field(fld, value) if fld else value
        self.staged[dotted] = v
        return v

    def reload_from_disk(self):
        self.saved, self.warnings = gs_config.load(gs_config.CONFIG)
        self.staged = dict(self.saved)
        self.disk_sig = self._file_sig()

    # ---------------- save
    def save_all(self):
        if not self.unsaved_keys() and not self.needs_write:
            self.flash = "nothing to save"
            return
        if self.disk_sig is not None and self._file_sig() != self.disk_sig \
                and not self.needs_write:
            def reload_restage():
                edits = {k: self.staged[k] for k in self.unsaved_keys()}
                self.reload_from_disk()
                for k, v in edits.items():
                    self.stage(k, v)
                self.flash = "reloaded from disk - your edits re-staged"
            self.push(Confirm(
                self, "settings.toml changed on disk since it was loaded.",
                [("R", "reload & re-stage my edits", reload_restage),
                 ("O", "overwrite", self._write)]))
            return
        self._write()

    def _write(self):
        vals = dict(self.staged)
        vals.setdefault("_unknown", {})
        gs_config.save(gs_config.CONFIG, vals)
        self.saved = dict(self.staged)
        self.disk_sig = self._file_sig()
        self.needs_write = False
        self.flash = "saved - applied live"

    # ---------------- stack
    def push(self, screen):
        self.stack.append(screen)

    def pop(self, screen=None):
        if len(self.stack) > 1:
            if screen is None or self.stack[-1] is screen:
                self.stack.pop()

    # ---------------- loop
    def relayout(self):
        h, w = self.stdscr.getmaxyx()
        self.mode = ("full" if w >= 84 and h >= 24 else
                     "stack" if w >= 60 and h >= 18 else "tiny")

    def run(self):
        while self.running:
            self.stdscr.erase()
            for scr in self.stack:          # bottom-up: modals overlay
                scr.render(self.stdscr)
            self.stdscr.refresh()
            try:
                key = self.stdscr.get_wch()
            except curses.error:            # get_wch timeout (picker preview)
                self.stack[-1].on_timeout()
                continue
            except KeyboardInterrupt:       # Ctrl+C == q, never a crash-out
                key = "q"
            self.flash = ""
            if key == curses.KEY_RESIZE:
                self.relayout()
                continue
            if not self.stack[-1].handle(key):
                self.handle_global(key)

    def handle_global(self, key):
        if key in ("q", "\x03"):
            self.quit()
        elif key == "?":
            self.push(Help(self))
        elif key == "s":
            self.save_all()
        elif key == "\t":
            main = self.stack[0]
            if len(self.stack) == 1 and main.section is not None:
                main.zone = "fields" if main.zone == "side" else "side"

    def quit(self):
        if self.unsaved_keys() or self.needs_write:
            def save_quit():
                self._write()
                self.running = False

            def discard_quit():
                self.running = False
            self.push(Confirm(
                self, f"{len(self.unsaved_keys())} unsaved change(s).",
                [("s", "save & quit", save_quit),
                 ("d", "discard & quit", discard_quit)],
                cancel_label="Esc stay"))
        else:
            self.running = False


# ---------------- single instance + bootstrap

def _pidfile() -> Path:
    run = os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
    return Path(run, "ghost", "ghost-settings.pid")


def _other_instance() -> int | None:
    try:
        pid = int(_pidfile().read_text().strip())
        cmd = Path(f"/proc/{pid}/cmdline").read_bytes().decode(
            "utf-8", "replace")
        if "ghost-settings" in cmd and pid != os.getpid():
            return pid
    except (OSError, ValueError):
        pass
    return None


def _curses_main(stdscr):
    try:
        curses.set_escdelay(25)
    except AttributeError:
        pass
    try:
        curses.curs_set(0)
    except curses.error:
        pass          # vt100 etc. cannot hide the cursor
    theme.init()
    draw.init_glyphs()
    App(stdscr).run()


def run_tui() -> int:
    other = _other_instance()
    if other is not None:
        print(f"ghost-settings already running (pid {other})")
        return 0
    pf = _pidfile()
    try:
        pf.parent.mkdir(parents=True, exist_ok=True)
        pf.write_text(str(os.getpid()))
    except OSError:
        pf = None
    locale.setlocale(locale.LC_ALL, "")
    try:
        curses.wrapper(_curses_main)   # restores the terminal on any exception
    except KeyboardInterrupt:
        pass
    finally:
        if pf is not None:
            try:
                pf.unlink()
            except OSError:
                pass
    return 0
