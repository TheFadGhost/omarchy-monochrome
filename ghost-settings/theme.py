"""ghost-settings theme — Omarchy colors.toml -> curses colour pairs.

Tiers (all information in the TUI is colour-redundant):
  256 colours  -> quantised Omarchy palette
  8/16 colours -> default fg/bg + A_BOLD/A_DIM/A_REVERSE
  NO_COLOR / no colours / unreadable colors.toml -> attributes only
"""

import curses
import os
import tomllib
from pathlib import Path

# ~/.local/state/omarchy/current/theme is replaced wholesale on theme switch
# (rm -rf && mv); we read it fresh at startup, never hold a watch on it.
THEME = Path(os.path.expanduser(
    "~/.local/state/omarchy/current/theme/colors.toml"))

ROLES = {   # role: (theme key, mono fallback attr)
    "NORMAL": ("foreground",       curses.A_NORMAL),
    "MUTED":  ("muted",            curses.A_DIM),
    "ACCENT": ("accent",           curses.A_BOLD),
    "TITLE":  ("light_foreground", curses.A_BOLD),
    "WARN":   ("bright_yellow",    curses.A_BOLD),
    "SEL":    ("selection",        curses.A_REVERSE),  # used as background
}

_attrs: dict[str, int] = {}
_info: dict[str, str] = {}


def _to_256(hexstr: str) -> int:
    """Nearest xterm-256 entry: 6x6x6 cube vs grey ramp."""
    r, g, b = bytes.fromhex(hexstr.lstrip("#"))
    cube = tuple(0 if c < 48 else min(5, 1 + (c - 35) // 40) for c in (r, g, b))
    cube_idx = 16 + 36 * cube[0] + 6 * cube[1] + cube[2]
    steps = (0, 95, 135, 175, 215, 255)
    cube_rgb = tuple(steps[c] for c in cube)
    grey = max(0, min(23, (((r + g + b) // 3) - 8) // 10))
    grey_idx = 232 + grey
    grey_v = 8 + grey * 10
    d_cube = sum((a - b) ** 2 for a, b in zip(cube_rgb, (r, g, b)))
    d_grey = sum((a - b) ** 2 for a, b in zip((grey_v,) * 3, (r, g, b)))
    return grey_idx if d_grey < d_cube else cube_idx


def _load_theme() -> dict:
    try:
        with open(THEME, "rb") as f:
            return tomllib.load(f)
    except Exception:
        return {}


def init() -> None:
    """Call once after curses is up. Safe on any terminal."""
    global _attrs, _info
    raw = _load_theme()
    _info = {
        "available": bool(raw),
        "mode": raw.get("mode", "?"),
        "accent": raw.get("accent", ""),
        "foreground": raw.get("foreground", ""),
    }
    _attrs = {role: fb for role, (_k, fb) in ROLES.items()}
    if os.environ.get("NO_COLOR"):
        return
    try:
        if not curses.has_colors():
            return
        curses.start_color()
        curses.use_default_colors()
        if curses.COLORS < 256 or not raw:
            return
    except curses.error:
        return
    pair = 0
    for role, (key, fb) in ROLES.items():
        hexstr = raw.get(key)
        if not isinstance(hexstr, str) or not hexstr.startswith("#"):
            continue
        pair += 1
        try:
            if role == "SEL":
                fg = _to_256(raw.get("foreground", "#ffffff"))
                curses.init_pair(pair, fg, _to_256(hexstr))
                _attrs[role] = curses.color_pair(pair)
            else:
                curses.init_pair(pair, _to_256(hexstr), -1)
                extra = curses.A_BOLD if role in ("ACCENT", "TITLE", "WARN") else 0
                _attrs[role] = curses.color_pair(pair) | extra
        except curses.error:
            _attrs[role] = fb


def attr(role: str) -> int:
    """Every call site uses attr() — nothing touches pairs directly."""
    return _attrs.get(role, 0)


def info() -> dict:
    return dict(_info) if _info else {"available": False, "mode": "?",
                                      "accent": "", "foreground": ""}


def theme_name() -> str:
    for probe in ("~/.local/state/omarchy/current/theme.name",):
        try:
            name = Path(os.path.expanduser(probe)).read_text().strip()
            if name:
                return name
        except OSError:
            pass
    try:
        p = Path(os.path.expanduser("~/.config/omarchy/current/theme"))
        return p.resolve().name or "unknown"
    except OSError:
        return "unknown"
