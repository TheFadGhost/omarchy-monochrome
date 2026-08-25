"""ghost-settings draw — Rect math, clipped writes, boxes, glyph sets.

All layout is Rect math on the real screen — no subwindows (derwin resize
behaviour is the classic curses spaghetti source). Every write goes through
put(), which clips, so no terminal size can raise.
"""

import curses
import locale
from dataclasses import dataclass, replace
from typing import NamedTuple

from theme import attr


@dataclass(frozen=True)
class Rect:
    y: int
    x: int
    h: int
    w: int

    def inset(self, dy: int, dx: int | None = None) -> "Rect":
        dx = dy if dx is None else dx
        return Rect(self.y + dy, self.x + dx,
                    max(0, self.h - 2 * dy), max(0, self.w - 2 * dx))

    def split_v(self, left_w: int) -> tuple["Rect", "Rect"]:
        left_w = max(0, min(left_w, self.w))
        return (replace(self, w=left_w),
                Rect(self.y, self.x + left_w, self.h, self.w - left_w))

    def split_h(self, top_h: int) -> tuple["Rect", "Rect"]:
        top_h = max(0, min(top_h, self.h))
        return (replace(self, h=top_h),
                Rect(self.y + top_h, self.x, self.h - top_h, self.w))

    @property
    def bottom(self) -> int:
        return self.y + self.h - 1

    @property
    def right(self) -> int:
        return self.x + self.w - 1


class Glyphs(NamedTuple):
    TL: str; TR: str; BL: str; BR: str; H: str; V: str
    CUR: str; FLD: str; ADJ_L: str; ADJ_R: str; MOD: str
    ON: str; OFF: str; DOT: str; SAVED: str; LOCK: str
    PILL_L: str; PILL_M: str; PILL_R: str; SEP: str; CHECK: str
    SWATCH: str; UD: str; LR: str


UNICODE = Glyphs(TL="┌", TR="┐", BL="└", BR="┘", H="─", V="│",
                 CUR="▶", FLD="▸", ADJ_L="◂", ADJ_R="▸", MOD="✱",
                 ON="●", OFF="○", DOT="·", SAVED="○", LOCK="—",
                 PILL_L="▐", PILL_M="▬", PILL_R="▌", SEP="·", CHECK="✓",
                 SWATCH="▓▓", UD="↑↓", LR="←→")
ASCII = Glyphs(TL="+", TR="+", BL="+", BR="+", H="-", V="|",
               CUR=">", FLD=">", ADJ_L="<", ADJ_R=">", MOD="*",
               ON="*", OFF="o", DOT=".", SAVED="o", LOCK="-",
               PILL_L="[", PILL_M="=", PILL_R="]", SEP="-", CHECK="+",
               SWATCH="##", UD="^v", LR="<->")

G = UNICODE


def init_glyphs() -> None:
    global G
    enc = (locale.getpreferredencoding(False) or "").upper()
    G = UNICODE if "UTF" in enc else ASCII


def put(win, y: int, x: int, s: str, a: int = 0) -> None:
    h, w = win.getmaxyx()
    if not (0 <= y < h) or x >= w:
        return
    if x < 0:
        s = s[-x:]
        x = 0
    if not s:
        return
    try:
        win.addnstr(y, x, s, w - x, a)
    except curses.error:
        pass  # writing the bottom-right cell is legal and raises


def boxed(win, r: Rect, title: str = "", focus: bool = False,
          fill: bool = False) -> Rect:
    """Border with the title embedded in the top rule; returns r.inset(1)."""
    if r.h < 2 or r.w < 2:
        return r.inset(1)
    a = attr("ACCENT") if focus else attr("MUTED")
    if fill:
        for i in range(r.h):
            put(win, r.y + i, r.x, " " * r.w)
    put(win, r.y, r.x, G.TL + G.H * (r.w - 2) + G.TR, a)
    if title:
        t = title[:max(0, r.w - 4)]
        put(win, r.y, r.x + 1, t,
            attr("TITLE") | (curses.A_BOLD if focus else 0))
    for i in range(1, r.h - 1):
        put(win, r.y + i, r.x, G.V, a)
        put(win, r.y + i, r.right, G.V, a)
    put(win, r.bottom, r.x, G.BL + G.H * (r.w - 2) + G.BR, a)
    return r.inset(1)


def wrap(text: str, width: int) -> list[str]:
    """Word wrap that keeps explicit newlines."""
    out: list[str] = []
    for para in text.split("\n"):
        if not para:
            out.append("")
            continue
        line = ""
        for word in para.split():
            cand = f"{line} {word}".strip()
            if len(cand) <= width:
                line = cand
            else:
                if line:
                    out.append(line)
                line = word[:width]
        out.append(line)
    return out


def shorten(s: str, width: int) -> str:
    if len(s) <= width:
        return s
    return "…" + s[-(width - 1):] if G is UNICODE else "..." + s[-(width - 3):]
