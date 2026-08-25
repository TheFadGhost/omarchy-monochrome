"""ghost-settings screens — MainScreen + modals.

Screen contract: render(win) draws from state; handle(key) -> True if
consumed; on_timeout() fires when a get_wch timeout elapses (only the
position picker arms one). Modals push onto app.stack; Esc pops.

The anti-spaghetti rule: screens never know settings. CategoryScreen logic
is generic over a schema.Section; adding a setting is one line in schema.py.
"""

import curses
import json
import os
import subprocess
import tempfile
import time
from pathlib import Path

import config as gs_config
from schema import (SPEC, Choice, NinePoint, Number, StrList, Text, Toggle,
                    NINE_POINTS)
from theme import attr, info as theme_info, theme_name
from tui import draw, widgets
from tui.draw import G, Rect, put

ESC = "\x1b"


def k_up(k):    return k in ("k", curses.KEY_UP)
def k_down(k):  return k in ("j", curses.KEY_DOWN)
def k_left(k):  return k in ("h", curses.KEY_LEFT)
def k_right(k): return k in ("l", curses.KEY_RIGHT)
def k_enter(k): return k in ("\n", "\r", curses.KEY_ENTER)
def k_back(k):  return k in ("\b", "\x7f", curses.KEY_BACKSPACE)
def k_bigl(k):  return k == "H" or k == curses.KEY_SLEFT
def k_bigr(k):  return k == "L" or k == curses.KEY_SRIGHT


class Screen:
    def __init__(self, app):
        self.app = app

    def render(self, win): ...
    def handle(self, key) -> bool: return False
    def on_timeout(self): ...
    def help_lines(self) -> list[str]: return []


# --------------------------------------------------------------- MainScreen

class MainScreen(Screen):
    GLOBAL_HINT = ""  # built per-render (glyph set)

    def __init__(self, app):
        super().__init__(app)
        self.entries = widgets.sidebar_entries()
        self.side = 0
        self.zone = "side"           # side | fields
        self.cursors: dict[str, int] = {}
        self.scrolls: dict[str, int] = {}
        self.edit_buf: str | None = None
        self._status_cache = (0.0, {})
        self.content = Rect(1, 18, 1, 1)

    # ---- helpers
    @property
    def section(self):
        return self.entries[self.side][0]

    def rows(self):
        return widgets.build_rows(self.section) if self.section else []

    def cursor(self):
        return self.cursors.get(self.section.key, self._first_sel())

    def _selectable(self, rows, i):
        f = rows[i]
        return f is not None and not widgets.is_locked(self.app,
                                                       self.section, f)

    def _first_sel(self):
        rows = self.rows()
        for i in range(len(rows)):
            if self._selectable(rows, i):
                return i
        return 0

    def _move_cursor(self, delta):
        rows = self.rows()
        if not rows:
            return
        i = self.cursor()
        for _ in range(len(rows)):
            i = (i + delta) % len(rows)
            if self._selectable(rows, i):
                break
        self.cursors[self.section.key] = i

    def focused_field(self):
        rows = self.rows()
        i = self.cursor()
        if 0 <= i < len(rows):
            return rows[i]
        return None

    def dotted(self, fld):
        return f"{self.section.key}.{fld.key}"

    # ---- render
    def render(self, win):
        h, w = win.getmaxyx()
        mode = self.app.mode
        widgets.render_header(win, w, self.app)
        if mode == "tiny":
            msg = f"ghost-settings needs at least 60x18 (now {w}x{h})"
            put(win, h // 2, max(0, (w - len(msg)) // 2), msg, attr("WARN"))
            return
        body = Rect(1, 0, h - 3, w)
        ctx_r = Rect(h - 2, 0, 1, w)
        glob_r = Rect(h - 1, 0, 1, w)
        sec = self.section
        if mode == "full":
            side_r, rest = body.split_v(17)
            self.content = Rect(rest.y, rest.x + 1, rest.h,
                                min(rest.w - 1, 96))
            widgets.render_sidebar(win, side_r, self.app, self.side,
                                   self.zone == "side")
            if sec is None:
                self._render_overview(win, self.content)
            else:
                self._render_category(win, self.content)
        else:  # stack
            self.content = body
            if self.zone == "side":
                self._render_menu(win, body)
            else:
                inner_w = body.w
                rows = self.rows()
                cur = self.cursor()
                scroll = self._fix_scroll(rows, cur, body.h - 2)
                widgets.render_fields(win, body, self.app, sec, rows, cur,
                                      True, self.edit_buf, scroll)
        context = self._context_hint()
        glob = (f"{G.UD} navigate · Enter open · Tab content · "
                "? help · q quit")
        summary = ("components & config at a glance" if sec is None
                   else f"{sec.title} {G.SEP} {sec.summary}")
        if mode == "stack":
            put(win, glob_r.y, 1, context[:w - 2], attr("MUTED"))
        else:
            widgets.render_hints(win, ctx_r, glob_r, context, glob, summary)
        if self.app.flash:
            put(win, ctx_r.y, max(1, w - len(self.app.flash) - 2),
                self.app.flash, attr("WARN"))

    def _context_hint(self):
        if self.zone == "side":
            return (f"{G.UD} navigate · Enter open · g/G ends · s save all")
        base = (f"{G.UD} field · {G.LR} adjust · Enter edit · u undo · "
                "s save · r revert · Esc back")
        if self.app.mode == "stack":
            base = (f"{G.UD} · {G.LR} adjust · Enter · i about · s save · "
                    "Esc back · q quit")
        if self.edit_buf is not None:
            base = "type value · Enter commit · Esc cancel"
        return base

    def _fix_scroll(self, rows, cur, view_h):
        key = self.section.key
        s = self.scrolls.get(key, 0)
        if cur < s:
            s = cur
        if cur >= s + view_h:
            s = cur - view_h + 1
        self.scrolls[key] = max(0, s)
        return self.scrolls[key]

    def _render_category(self, win, r):
        sec = self.section
        rows = self.rows()
        cur = self.cursor()
        left_w = max(40, min(46, r.w * 11 // 20))
        left, right = r.split_v(left_w)
        scroll = self._fix_scroll(rows, cur, left.h - 2)
        widgets.render_fields(win, left, self.app, sec, rows, cur,
                              self.zone == "fields", self.edit_buf, scroll)
        widgets.render_about(win, right, self.app, sec, self.focused_field())

    def _render_menu(self, win, r):
        inner = draw.boxed(win, r, "Categories", focus=True)
        for i, (sec, label) in enumerate(self.entries):
            if i >= inner.h:
                break
            cur = i == self.side
            a = attr("SEL") | curses.A_BOLD if cur else attr("NORMAL")
            if cur:
                put(win, inner.y + i, inner.x, " " * inner.w, attr("SEL"))
            put(win, inner.y + i, inner.x,
                (G.CUR if cur else " ") + " " + label, a)
            if sec:
                put(win, inner.y + i, inner.x + 22,
                    sec.summary[:inner.w - 23], attr("MUTED"))

    # ---- overview
    def _statuses(self):
        now = time.time()
        ts, cache = self._status_cache
        if now - ts < 2.0:
            return cache
        cache = {"sill": self._pid_running("sill"),
                 "bar": self._proc_running("quickshell")}
        self._status_cache = (now, cache)
        return cache

    @staticmethod
    def _pid_running(name):
        run = os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
        try:
            pid = int(Path(run, "ghost", f"{name}.pid").read_text().strip())
            cmd = Path(f"/proc/{pid}/cmdline").read_bytes().decode(
                "utf-8", "replace")
            return name in cmd or "python" in cmd
        except (OSError, ValueError):
            return False

    @staticmethod
    def _proc_running(name):
        try:
            r = subprocess.run(["pgrep", "-x", name], capture_output=True,
                               timeout=2)
            return r.returncode == 0
        except (OSError, subprocess.TimeoutExpired):
            return False

    def _render_overview(self, win, r):
        st = self._statuses()
        s = self.app.staged
        comp, rest = r.split_h(4)
        inner = draw.boxed(win, comp, "Components")

        def comprow(y, name, running, detail):
            put(win, y, inner.x + 1, name, attr("NORMAL"))
            dot = G.ON if running else G.OFF
            lbl = "running" if running else "stopped"
            put(win, y, inner.x + 11, f"{dot} {lbl}",
                attr("ACCENT") if running else attr("MUTED"))
            put(win, y, inner.x + 23, detail[:inner.w - 24], attr("MUTED"))

        deny = len(s.get("sill.privacy.denylist", ()))
        comprow(inner.y, "Sill", st["sill"],
                f"chip {s.get('sill.position')} {G.SEP} margin "
                f"{s.get('sill.margin')} px {G.SEP} "
                f"{s.get('sill.max_items')} items {G.SEP} deny {deny}")
        drawer_n = sum(bool(s.get(f"bar.drawer.{k}"))
                       for k in ("wifi", "bluetooth", "audio", "display"))
        mods = [m for m in ("media", "sysmon", "pomodoro", "notes")
                if s.get(f"bar.{m}.enabled")]
        drawer = (f"drawer on ({drawer_n} icons)"
                  if s.get("bar.drawer.enabled") else "drawer off")
        comprow(inner.y + 1, "Bar", st["bar"],
                f"{drawer} {G.SEP} " + f" {G.SEP} ".join(mods))

        boxes, rest2 = rest.split_h(7)
        tb, cb = boxes.split_v(boxes.w // 2)
        ti = draw.boxed(win, tb, "Theme")
        info = theme_info()
        put(win, ti.y, ti.x + 1, f"{theme_name()}  ({info['mode']})",
            attr("TITLE"))
        if info["available"]:
            put(win, ti.y + 1, ti.x + 1, f"accent {info['accent']} ",
                attr("NORMAL"))
            put(win, ti.y + 1, ti.x + 1 + 16, G.SWATCH, attr("ACCENT"))
            put(win, ti.y + 1, ti.x + 1 + 20, f"fg {info['foreground']} ",
                attr("NORMAL"))
            put(win, ti.y + 1, ti.x + 1 + 32, G.SWATCH, attr("NORMAL"))
        else:
            put(win, ti.y + 1, ti.x + 1, "theme unavailable", attr("MUTED"))
        put(win, ti.y + 3, ti.x + 1, "follow Omarchy theme", attr("NORMAL"))
        put(win, ti.y + 3, ti.x + 24,
            "on" if s.get("general.follow_theme") else "off", attr("ACCENT"))
        put(win, ti.y + 4, ti.x + 1, "animations master", attr("NORMAL"))
        put(win, ti.y + 4, ti.x + 24,
            "on" if s.get("general.animations") else "off", attr("ACCENT"))

        ci = draw.boxed(win, cb, "Config")
        path = gs_config.CONFIG
        put(win, ci.y, ci.x + 1,
            draw.shorten("~/" + str(path.relative_to(Path.home())), ci.w - 2),
            attr("NORMAL"))
        nkeys = sum(len(sec.fields) for sec in SPEC)
        try:
            mtime = time.strftime("%H:%M", time.localtime(
                path.stat().st_mtime))
            state = f"valid {G.SEP} {nkeys} keys {G.SEP} saved {mtime}"
            if self.app.needs_write:
                state = f"PARSE ERROR {G.SEP} recovery active"
        except OSError:
            state = f"not written yet {G.SEP} defaults active"
        put(win, ci.y + 1, ci.x + 1, state, attr("MUTED"))
        bak = path.with_suffix(".toml.bak")
        put(win, ci.y + 2, ci.x + 1,
            f"backup settings.toml.bak {G.SEP} "
            + ("ok" if bak.exists() else "none yet"), attr("MUTED"))
        put(win, ci.y + 3, ci.x + 1, "live consumers: sill bar",
            attr("MUTED"))
        if self.app.warnings:
            put(win, ci.y + 4, ci.x + 1,
                f"{len(self.app.warnings)} load warning(s)", attr("WARN"))

        ly = rest2.y + 1
        put(win, ly, r.x + 1,
            f"{G.ON} running   {G.OFF} stopped   {G.MOD} unsaved   "
            f"{G.LOCK} locked by dependency   {G.ADJ_L} {G.ADJ_R} adjustable",
            attr("MUTED"))
        put(win, min(r.bottom, ly + 3), r.x + 1,
            "Enter a category to edit · everything applies live on save",
            attr("NORMAL"))

    # ---- input
    def handle(self, key):
        if self.app.mode == "tiny":
            return key not in ("q", "\x03")
        if self.edit_buf is not None:
            return self._handle_edit(key)
        if self.zone == "side":
            return self._handle_side(key)
        return self._handle_fields(key)

    def _handle_side(self, key):
        n = len(self.entries)
        if k_up(key):
            self.side = (self.side - 1) % n
        elif k_down(key):
            self.side = (self.side + 1) % n
        elif key == "g":
            self.side = 0
        elif key == "G":
            self.side = n - 1
        elif k_enter(key) or k_right(key):
            if self.section is not None:
                self.zone = "fields"
        elif key == ESC and self.app.mode == "stack":
            return False   # falls through to global quit? no: consume
        else:
            return False
        return True

    def _handle_fields(self, key):
        fld = self.focused_field()
        if k_up(key):
            self._move_cursor(-1)
        elif k_down(key):
            self._move_cursor(1)
        elif key == ESC:
            self.zone = "side"
        elif fld is None:
            return False
        elif k_left(key) or k_right(key) or key == " ":
            if not widgets.is_adjustable(fld):
                if k_left(key):
                    self.zone = "side"
                    return True
                if key == " ":
                    return False
                return self._open_editor(fld)
            self._adjust(fld, 1 if (k_right(key) or key == " ") else -1)
        elif k_bigl(key) or k_bigr(key):
            if isinstance(fld, Number):
                self._adjust(fld, 10 if k_bigr(key) else -10)
        elif k_enter(key):
            if isinstance(fld, Toggle):
                self._adjust(fld, 1)
            elif isinstance(fld, Choice):
                self._adjust(fld, 1)
            elif isinstance(fld, (Number, Text)):
                self.edit_buf = ""
            else:
                return self._open_editor(fld)
        elif isinstance(key, str) and key.isdigit() and isinstance(fld, Number):
            self.edit_buf = key
        elif key == "u":
            d = self.dotted(fld)
            self.app.staged[d] = self.app.saved.get(d, fld.default)
            self.app.flash = f"{fld.label} restored"
        elif key == "r":
            sec = self.section
            def revert():
                for f in sec.fields:
                    d = f"{sec.key}.{f.key}"
                    self.app.staged[d] = self.app.saved.get(d, f.default)
                self.app.flash = f"{sec.title} reverted to saved"
            self.app.push(Confirm(self.app,
                                  f"Revert {sec.title} to last saved?",
                                  [("y", "revert", revert)]))
        elif key == "i" and self.app.mode == "stack":
            self.app.push(AboutModal(self.app, self.section, fld))
        else:
            return False
        return True

    def _open_editor(self, fld):
        if isinstance(fld, NinePoint):
            self.app.push(PositionPicker(self.app, self.section, fld))
            return True
        if isinstance(fld, StrList):
            self.app.push(ListEditor(self.app, self.section, fld))
            return True
        if isinstance(fld, Text):
            self.edit_buf = ""
            return True
        return False

    def _adjust(self, fld, direction):
        d = self.dotted(fld)
        v = self.app.staged.get(d, fld.default)
        if isinstance(fld, Toggle):
            self.app.stage(d, not v)
        elif isinstance(fld, Choice):
            i = fld.options.index(v) if v in fld.options else 0
            self.app.stage(d, fld.options[(i + (1 if direction > 0 else -1))
                                          % len(fld.options)])
        elif isinstance(fld, Number):
            step = fld.step * (abs(direction) if abs(direction) > 1 else 1)
            nv = v + (step if direction > 0 else -step)
            self.app.stage(d, max(fld.min, min(fld.max, nv)))

    def _handle_edit(self, key):
        fld = self.focused_field()
        if fld is None:
            self.edit_buf = None
            return True
        if key == ESC:
            self.edit_buf = None
        elif k_enter(key):
            buf = self.edit_buf
            self.edit_buf = None
            if buf == "":
                return True
            d = self.dotted(fld)
            if isinstance(fld, Number):
                try:
                    n = int(buf)
                except ValueError:
                    self.app.flash = "not a number"
                    return True
                staged = self.app.stage(d, n)
                if staged != n:
                    self.app.flash = f"clamped to {staged}"
            else:
                self.app.stage(d, buf)
        elif k_back(key):
            self.edit_buf = self.edit_buf[:-1]
        elif isinstance(key, str) and key.isprintable():
            if isinstance(fld, Number) and not key.isdigit():
                return True
            if len(self.edit_buf) < 120:
                self.edit_buf += key
        return True

    def help_lines(self):
        lines = ["Global",
                 "  q quit · s save all · ? help · Tab switch zone",
                 "", "Sidebar",
                 f"  {G.UD} or j/k move · Enter open · g/G first/last",
                 "", "Fields",
                 f"  {G.UD} move · {G.LR} adjust · Shift+{G.LR} big step",
                 "  Enter edit/open · Space flip toggle · 0-9 type number",
                 "  u undo field · r revert category · Esc back"]
        if self.app.mode == "stack":
            lines += ["", "Small terminal", "  i about panel for the field"]
        return lines


# ------------------------------------------------------------------ modals

def modal_rect(win, h, w):
    sh, sw = win.getmaxyx()
    h = min(h, sh - 2)
    w = min(w, sw - 2)
    return Rect(max(1, (sh - h) // 2), max(1, (sw - w) // 2), h, w)


class Confirm(Screen):
    """options: [(key, label, callback)]; Esc cancels."""

    def __init__(self, app, message, options, cancel_label="Esc cancel"):
        super().__init__(app)
        self.message = message
        self.options = options
        self.cancel_label = cancel_label

    def render(self, win):
        lines = draw.wrap(self.message, 46)
        r = modal_rect(win, len(lines) + 4, 52)
        inner = draw.boxed(win, r, "Confirm", focus=True, fill=True)
        for i, ln in enumerate(lines):
            put(win, inner.y + i, inner.x + 1, ln, attr("NORMAL"))
        hint = " · ".join([f"{k} {lbl}" for k, lbl, _ in self.options]
                          + [self.cancel_label])
        put(win, inner.y + len(lines) + 1, inner.x + 1, hint, attr("MUTED"))

    def handle(self, key):
        if key == ESC:
            self.app.pop(self)
            return True
        for k, _lbl, cb in self.options:
            if key == k:
                self.app.pop(self)
                cb()
                return True
        return True   # modal swallows everything


class Help(Screen):
    def render(self, win):
        base = self.app.stack[0]
        lines = base.help_lines() or ["q quit"]
        for scr in self.app.stack[1:]:
            if scr is not self and scr.help_lines():
                lines = scr.help_lines()
        w = max(len(x) for x in lines) + 6
        r = modal_rect(win, len(lines) + 3, max(w, 40))
        inner = draw.boxed(win, r, "Help", focus=True, fill=True)
        for i, ln in enumerate(lines[:inner.h - 1]):
            put(win, inner.y + i, inner.x + 1, ln, attr("NORMAL"))
        put(win, inner.y + inner.h - 1, inner.x + 1, "any key closes",
            attr("MUTED"))

    def handle(self, key):
        self.app.pop(self)
        return True


class AboutModal(Screen):
    def __init__(self, app, section, fld):
        super().__init__(app)
        self.section, self.fld = section, fld

    def render(self, win):
        r = modal_rect(win, 14, 44)
        for i in range(r.h):
            put(win, r.y + i, r.x, " " * r.w)
        widgets.render_about(win, r, self.app, self.section, self.fld)

    def handle(self, key):
        self.app.pop(self)
        return True


class ListEditor(Screen):
    """String-list modal (Stash-style): a add · e edit · d delete · u undo."""

    def __init__(self, app, section, fld):
        super().__init__(app)
        self.section, self.fld = section, fld
        self.items = list(app.staged.get(f"{section.key}.{fld.key}",
                                         fld.default))
        self.cursor = 0
        self.trash: list[tuple[int, str]] = []
        self.buf: str | None = None
        self.adding = False

    def render(self, win):
        title = f"{self.section.title} {G.SEP} {self.fld.label}"
        view = 10
        r = modal_rect(win, view + 6, 46)
        inner = draw.boxed(win, r, title, focus=True, fill=True)
        doc = (self.fld.doc or "").split("\n")[0]
        put(win, inner.y, inner.x + 1, doc[:inner.w - 2], attr("MUTED"))
        top = max(0, min(self.cursor - view + 1, len(self.items) - view))
        y = inner.y + 2
        shown = self.items[top:top + view]
        for i, item in enumerate(shown):
            idx = top + i
            cur = idx == self.cursor
            a = attr("SEL") | curses.A_BOLD if cur else attr("NORMAL")
            text = item
            if cur and self.buf is not None and not self.adding:
                text = f"[{self.buf}_]"
                a = attr("ACCENT")
            put(win, y + i, inner.x + 1,
                (G.FLD if cur else " ") + " " + text[:inner.w - 4], a)
        if self.adding and self.buf is not None:
            put(win, y + len(shown), inner.x + 1,
                f"{G.FLD} [{self.buf}_]", attr("ACCENT"))
        if not self.items and self.buf is None:
            put(win, y, inner.x + 1, "(empty)", attr("MUTED"))
        hint = ("type · Enter commit · Esc cancel" if self.buf is not None
                else "a add · e edit · d delete · u undo · Esc done")
        put(win, inner.y + inner.h - 1, inner.x + 1, hint, attr("MUTED"))

    def handle(self, key):
        if self.buf is not None:
            if key == ESC:
                self.buf = None
                self.adding = False
            elif k_enter(key):
                v = self.buf.strip()
                if v:
                    if self.adding:
                        self.items.append(v)
                        self.cursor = len(self.items) - 1
                    else:
                        self.items[self.cursor] = v
                self.buf = None
                self.adding = False
            elif k_back(key):
                self.buf = self.buf[:-1]
            elif isinstance(key, str) and key.isprintable():
                self.buf += key
            return True
        if key == ESC:
            d = f"{self.section.key}.{self.fld.key}"
            self.app.stage(d, tuple(self.items))
            self.app.pop(self)
        elif k_up(key) and self.items:
            self.cursor = max(0, self.cursor - 1)
        elif k_down(key) and self.items:
            self.cursor = min(len(self.items) - 1, self.cursor + 1)
        elif key == "a":
            self.buf, self.adding = "", True
        elif key == "e" and self.items:
            self.buf, self.adding = self.items[self.cursor], False
        elif key == "d" and self.items:
            self.trash.append((self.cursor, self.items.pop(self.cursor)))
            self.cursor = min(self.cursor, max(0, len(self.items) - 1))
        elif key == "u" and self.trash:
            i, v = self.trash.pop()
            self.items.insert(min(i, len(self.items)), v)
            self.cursor = min(i, len(self.items) - 1)
        return True

    def help_lines(self):
        return ["List editor", "  a add · e edit · d delete · u undo delete",
                "  Esc closes and stages the list"]


class PositionPicker(Screen):
    """Nine-point picker: a miniature of the monitor you arrow the pill
    around. Space holds a live preview through the production save path."""

    PREVIEW_MS = 700

    def __init__(self, app, section, fld):
        super().__init__(app)
        self.section, self.fld = section, fld
        self.dot_pos = f"{section.key}.{fld.key}"
        self.dot_margin = f"{section.key}.margin"
        self.pos = app.staged.get(self.dot_pos, fld.default)
        self.margin = app.staged.get(self.dot_margin, 10)
        self.monitors = self._monitors()
        self.mon_i = 0
        self.snapshot: bytes | None = None
        self.previewing = False

    @staticmethod
    def _monitors():
        try:
            out = subprocess.run(["hyprctl", "monitors", "-j"],
                                 capture_output=True, timeout=2).stdout
            mons = [(m["name"], m["width"], m["height"])
                    for m in json.loads(out)]
            return mons or [("monitor", 1920, 1080)]
        except Exception:
            return [("monitor", 1920, 1080)]

    # grid index <-> name (reading order matches NINE_POINTS)
    @property
    def idx(self):
        return NINE_POINTS.index(self.pos)

    def _move(self, dc, dr):
        c, r = self.idx % 3, self.idx // 3
        c = max(0, min(2, c + dc))     # edges clamp — a corner feels like one
        r = max(0, min(2, r + dr))
        self.pos = NINE_POINTS[r * 3 + c]
        if self.previewing:
            self._write_preview()

    def render(self, win):
        area = self.app.stack[0].content
        name, mw, mh = self.monitors[self.mon_i]
        title = f"{self.section.title} {G.SEP} {self.fld.label}"
        bw = min(area.w - 14, 64)
        bh = max(8, min(area.h - 10, round(bw * mh / mw * 0.30)))
        for i in range(area.h):
            put(win, area.y + i, area.x, " " * area.w)
        r = Rect(area.y, area.x, min(area.h, bh + 9), area.w)
        inner = draw.boxed(win, r, title, focus=True, fill=True)
        bx = inner.x + (inner.w - bw) // 2
        by = inner.y + 1
        mon = Rect(by, bx, bh, bw)
        mtitle = f" {name} {G.SEP} {mw}x{mh} "
        mi = draw.boxed(win, mon, "", focus=False)
        put(win, mon.y, mon.x + (bw - len(mtitle)) // 2, mtitle, attr("MUTED"))

        cols = (mi.x + 1, mi.x + mi.w // 2 - 1, mi.x + mi.w - 3)
        rows_ = (mi.y, mi.y + mi.h // 2, mi.y + mi.h - 1)
        saved = self.app.saved.get(self.dot_pos)
        for i, pname in enumerate(NINE_POINTS):
            c, rr = i % 3, i // 3
            glyph = (G.SAVED if pname == saved else G.DOT) + str(i + 1)
            a = attr("NORMAL") if pname == saved else attr("MUTED")
            put(win, rows_[rr], cols[c], glyph, a)
        self._draw_pill(win, mi)

        iy = mon.bottom + 2
        put(win, iy, bx + 2, "position", attr("MUTED"))
        put(win, iy, bx + 12, self.pos, attr("TITLE"))
        put(win, iy, bx + 28, "saved", attr("MUTED"))
        put(win, iy, bx + 35, str(saved), attr("NORMAL"))
        put(win, iy + 1, bx + 2, "margin", attr("MUTED"))
        put(win, iy + 1, bx + 12,
            f"{G.ADJ_L} {self.margin} px {G.ADJ_R}", attr("NORMAL"))
        pill = G.PILL_L + G.PILL_M * 2 + G.PILL_R
        put(win, iy + 1, bx + 28, pill, attr("ACCENT"))
        put(win, iy + 1, bx + 33, "the chip, drawn to scale", attr("MUTED"))
        if self.previewing:
            put(win, iy + 2, bx + 2, "PREVIEW live on the desktop",
                attr("WARN"))
        hy = min(inner.y + inner.h - 1, iy + 3)
        put(win, hy, bx + 2,
            "arrows/hjkl move · 1-9 jump · -+ margin · Space preview · "
            "Enter apply", attr("MUTED"))
        if len(self.monitors) > 1:
            put(win, hy - 1 if hy - 1 > iy + 1 else hy, bx + 2,
                "Tab next monitor", attr("MUTED"))
        h, w = win.getmaxyx()
        put(win, h - 2, 1, " " * (w - 2))
        put(win, h - 2, 1,
            "Space holds a live preview on the real desktop; release restores",
            attr("MUTED"))
        put(win, h - 1, 1, " " * (w - 2))
        put(win, h - 1, 1, "Enter apply · Esc cancel · ? help", attr("MUTED"))
        put(win, h - 1, 36, G.V + "  pick where the chip lives",
            attr("MUTED"))

    def _draw_pill(self, win, mi):
        pill = G.PILL_L + G.PILL_M * 8 + G.PILL_R
        c, rr = self.idx % 3, self.idx // 3
        nudge = 1 if self.margin > 0 else 0
        if c == 0:
            x = mi.x + nudge
        elif c == 2:
            x = mi.x + mi.w - len(pill) - nudge
        else:
            x = mi.x + (mi.w - len(pill)) // 2
        if rr == 0:
            y = mi.y + (1 if self.margin > 24 else 0)
        elif rr == 2:
            y = mi.y + mi.h - 1 - (1 if self.margin > 24 else 0)
        else:
            y = mi.y + mi.h // 2
        digit = str(self.idx + 1)
        put(win, y, x, pill, attr("ACCENT") | curses.A_BOLD)
        put(win, y, x + len(pill), digit, attr("ACCENT"))

    # ---- preview through the production save path
    def _write_preview(self):
        if self.snapshot is None and gs_config.CONFIG.exists():
            self.snapshot = gs_config.CONFIG.read_bytes()
        vals = dict(self.app.staged)
        vals[self.dot_pos] = self.pos
        vals[self.dot_margin] = self.margin
        gs_config.save(gs_config.CONFIG, vals)
        self.previewing = True
        self.app.stdscr.timeout(self.PREVIEW_MS)

    def _restore_preview(self):
        if not self.previewing:
            return
        self.previewing = False
        self.app.stdscr.timeout(-1)
        try:
            if self.snapshot is None:
                gs_config.CONFIG.unlink(missing_ok=True)
            else:
                fd, tmp = tempfile.mkstemp(dir=gs_config.CONFIG.parent,
                                           prefix=".settings-")
                os.write(fd, self.snapshot)
                os.fsync(fd)
                os.close(fd)
                os.replace(tmp, gs_config.CONFIG)
        except OSError:
            pass
        self.snapshot = None

    def on_timeout(self):
        self._restore_preview()   # space auto-repeat stopped -> released

    def handle(self, key):
        if key == ESC:
            self._restore_preview()
            self.app.pop(self)
        elif k_enter(key):
            self._restore_preview()
            self.app.stage(self.dot_pos, self.pos)
            self.app.stage(self.dot_margin, self.margin)
            self.app.pop(self)
        elif k_left(key):
            self._move(-1, 0)
        elif k_right(key):
            self._move(1, 0)
        elif k_up(key):
            self._move(0, -1)
        elif k_down(key):
            self._move(0, 1)
        elif isinstance(key, str) and key in "123456789":
            self.pos = NINE_POINTS[int(key) - 1]
            if self.previewing:
                self._write_preview()
        elif key in ("-", "_"):
            self.margin = max(0, self.margin - 2)
            if self.previewing:
                self._write_preview()
        elif key in ("+", "="):
            self.margin = min(128, self.margin + 2)
            if self.previewing:
                self._write_preview()
        elif key == " ":
            self._write_preview()
        elif key == "\t":
            self.mon_i = (self.mon_i + 1) % len(self.monitors)
        elif key == "?":
            self.app.push(Help(self.app))
        return True

    def help_lines(self):
        return ["Position picker",
                "  arrows / hjkl move the chip · 1-9 jump",
                "  - + adjust margin · Tab next monitor",
                "  Space (hold) live preview on the desktop",
                "  Enter stage · Esc cancel"]


class Recovery(Screen):
    """Corrupt-config screen: E edit · B restore backup · D stage defaults.
    Nothing touches the broken file until an explicit s."""

    def __init__(self, app, error):
        super().__init__(app)
        self.error = error

    def render(self, win):
        lines = draw.wrap(f"settings.toml could not be parsed:\n{self.error}",
                          56)
        r = modal_rect(win, len(lines) + 9, 62)
        inner = draw.boxed(win, r, "Config recovery", focus=True, fill=True)
        y = inner.y
        for ln in lines:
            put(win, y, inner.x + 1, ln, attr("WARN"))
            y += 1
        y += 1
        bak = gs_config.CONFIG.with_suffix(".toml.bak")
        opts = ["E  edit the file in $EDITOR (re-checked on exit)",
                "B  restore the last-good backup"
                + ("" if bak.exists() else "  (no backup found)"),
                "D  start from schema defaults"]
        for o in opts:
            put(win, y, inner.x + 1, o, attr("NORMAL"))
            y += 1
        y += 1
        put(win, y, inner.x + 1,
            "The broken file is untouched until you press s to save.",
            attr("MUTED"))
        put(win, inner.y + inner.h - 1, inner.x + 1,
            "E edit · B backup · D defaults · q quit", attr("MUTED"))

    def _reload_ok(self):
        try:
            with open(gs_config.CONFIG, "rb") as f:
                import tomllib
                tomllib.load(f)
        except FileNotFoundError:
            pass
        except Exception as e:
            self.error = str(e)
            return False
        self.app.reload_from_disk()
        self.app.needs_write = False
        self.app.pop(self)
        return True

    def handle(self, key):
        if key == "E":
            editor = os.environ.get("EDITOR") or os.environ.get(
                "VISUAL") or "vi"
            curses.def_prog_mode()
            curses.endwin()
            try:
                subprocess.call([editor, str(gs_config.CONFIG)])
            except OSError:
                pass
            curses.reset_prog_mode()
            self.app.stdscr.refresh()
            self._reload_ok()
        elif key == "B":
            bak = gs_config.CONFIG.with_suffix(".toml.bak")
            if bak.exists():
                self.app.staged, _w = gs_config.load(bak)
                self.app.saved = {}
                self.app.needs_write = True
                self.app.flash = "backup staged - press s to write it"
                self.app.pop(self)
        elif key == "D":
            vals = gs_config.defaults()
            vals["_unknown"] = {}
            self.app.staged = dict(vals)
            self.app.saved = {}
            self.app.needs_write = True
            self.app.flash = "defaults staged - press s to write them"
            self.app.pop(self)
        elif key in ("q", "\x03"):
            return False
        return True

    def help_lines(self):
        return ["Recovery", "  E edit in $EDITOR · B restore backup",
                "  D stage defaults · s writes the choice · q quit"]
