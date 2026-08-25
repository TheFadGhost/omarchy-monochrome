"""ghost-settings widgets — Sidebar, FieldList, About, StatusRows.

Pure render helpers: state (cursor positions, staged values, edit buffers)
lives in the screens; widgets draw from it. Screens never know settings —
everything here is driven by schema.SPEC.
"""

import curses

from schema import (SPEC, Choice, NinePoint, Number, StrList, Text, Toggle,
                    NINE_POINTS)
from theme import attr
from tui import draw
from tui.draw import G, Rect, put

# Display-only grouping: blank separator before these dotted keys.
GROUP_BREAKS = {
    "sill.expand_on_hover", "sill.max_items", "sill.disable_omarchy_clipboard",
    "sill.screenshots.copy",
    "bar.drawer.wifi", "bar.drawer.expand_on",
    "bar.media.max_title_chars",
    "bar.sysmon.cpu", "bar.sysmon.interval_s",
    "bar.pomodoro.work_min", "bar.pomodoro.autostart",
    "bar.notes.file",
}


def sidebar_entries():
    """[(None, 'Overview'), (Section, label), ...] — dotted keys get a
    sub-item prefix, except bar.drawer which reads as the bar's own row."""
    out = [(None, "Overview")]
    for sec in SPEC:
        sub = "." in sec.key and sec.key != "bar.drawer"
        out.append((sec, (G.SEP + " " if sub else "") + sec.title))
    return out


def build_rows(section):
    """Field rows with None separators (display grouping)."""
    rows = []
    for fld in section.fields:
        if rows and f"{section.key}.{fld.key}" in GROUP_BREAKS:
            rows.append(None)
        rows.append(fld)
    return rows


def is_locked(app, section, fld) -> bool:
    return bool(fld.gate) and not app.staged.get(fld.gate)


def is_adjustable(fld) -> bool:
    return isinstance(fld, (Toggle, Choice, Number))


def value_text(app, section, fld) -> str:
    v = app.staged.get(f"{section.key}.{fld.key}", fld.default)
    if isinstance(fld, Toggle):
        return "on" if v else "off"
    if isinstance(fld, Number):
        if v == 0 and fld.zero_means:
            return f"0 ({fld.zero_means})"
        return str(v)
    if isinstance(fld, StrList):
        n = len(v)
        return f"{n} app{'s' if n != 1 else ''}"
    if isinstance(fld, Text):
        return draw.shorten(str(v), 24)
    return str(v)


def cluster(app, section, fld, editing_buf=None) -> tuple[str, int]:
    """Right-aligned value cluster text + attr for one field row."""
    if editing_buf is not None:
        return f"[{editing_buf}_]", attr("ACCENT")
    val = value_text(app, section, fld)
    if is_locked(app, section, fld):
        return f"{G.LOCK} {val} {G.LOCK}", attr("MUTED")
    if is_adjustable(fld):
        return f"{G.ADJ_L} {val} {G.ADJ_R}", attr("NORMAL")
    return f"{val} {G.ADJ_R}", attr("NORMAL")


def render_sidebar(win, r: Rect, app, cursor: int, focused: bool):
    entries = sidebar_entries()
    for i, (sec, label) in enumerate(entries):
        if i >= r.h:
            break
        cur = i == cursor
        mark = G.CUR if cur else " "
        star = ""
        if sec is not None and any(
                k.startswith(sec.key + ".") and "." not in
                k[len(sec.key) + 1:] and app.staged.get(k) != app.saved.get(k)
                for k in app.staged if k != "_unknown"):
            star = " " + G.MOD
        a = attr("NORMAL")
        if cur:
            a = (attr("SEL") | curses.A_BOLD) if focused else attr("TITLE")
        put(win, r.y + i, r.x, mark + " ", attr("ACCENT") if cur else 0)
        put(win, r.y + i, r.x + 2, (label + star).ljust(r.w - 2)[:r.w - 2], a)
    for i in range(r.h):
        put(win, r.y + i, r.right + 1, G.V, attr("MUTED"))


def render_fields(win, r: Rect, app, section, rows, cursor: int,
                  focused: bool, edit_buf=None, scroll: int = 0):
    inner = draw.boxed(win, r, "Settings", focus=focused)
    for i, fld in enumerate(rows[scroll:scroll + inner.h]):
        y = inner.y + i
        idx = scroll + i
        if fld is None:
            continue
        cur = idx == cursor
        locked = is_locked(app, section, fld)
        staged = app.staged.get(f"{section.key}.{fld.key}") != \
            app.saved.get(f"{section.key}.{fld.key}")
        name = fld.label
        if isinstance(fld, Number) and fld.unit:
            name += f" ({fld.unit})"
        if staged:
            name += " " + G.MOD
        buf = edit_buf if (cur and edit_buf is not None) else None
        val, va = cluster(app, section, fld, buf)
        na = attr("MUTED") if locked else attr("NORMAL")
        if cur and focused:
            na = attr("SEL") | curses.A_BOLD
            va = va if buf is not None else na
            put(win, y, inner.x, " " * inner.w, attr("SEL"))
        put(win, y, inner.x, (G.FLD if cur else " ") + " ",
            attr("ACCENT") if cur else 0)
        put(win, y, inner.x + 2, name[:inner.w - 4], na)
        vx = inner.x + inner.w - len(val) - 1
        put(win, y, max(vx, inner.x + 2 + len(name) + 1), val,
            va if not locked else attr("MUTED"))
    return inner


def render_about(win, r: Rect, app, section, fld):
    inner = draw.boxed(win, r, "About")
    if fld is None:
        return
    y = inner.y
    put(win, y, inner.x, fld.label[:inner.w], attr("TITLE"))
    y += 2
    doc = " ".join((fld.doc or "No description.").split())
    for line in draw.wrap(doc, inner.w):
        if y >= inner.y + inner.h - 5:
            break
        put(win, y, inner.x, line, attr("NORMAL"))
        y += 1
    y += 1
    cur = value_text(app, section, fld)
    dflt = fld.default
    if isinstance(fld, Toggle):
        dflt = "on" if dflt else "off"
    elif isinstance(fld, StrList):
        dflt = f"{len(dflt)} apps"
    if y < inner.y + inner.h:
        put(win, y, inner.x, "current".ljust(10) + str(cur), attr("NORMAL"))
        y += 1
    if y < inner.y + inner.h:
        put(win, y, inner.x, "default".ljust(10) + str(dflt), attr("MUTED"))
        y += 1
    extra = []
    if isinstance(fld, Number):
        rng = f"range     {fld.min}-{fld.max}"
        if fld.step != 1:
            rng += f" step {fld.step}"
        if fld.unit:
            rng += f" {fld.unit}"
        extra.append(rng)
    if isinstance(fld, Choice):
        extra.append("options   " + " / ".join(fld.options))
    if isinstance(fld, NinePoint):
        extra.append("Enter opens the visual picker.")
    if fld.gate:
        from schema import field_for
        _s, gf = field_for(fld.gate)
        gl = gf.label if gf else fld.gate
        extra.append(f"locked unless “{gl}” is on"
                     if G is draw.UNICODE else f"locked unless {gl} is on")
    for line in extra:
        if y < inner.y + inner.h:
            put(win, y, inner.x, line[:inner.w], attr("MUTED"))
            y += 1
    y += 1
    for line in draw.wrap("Applies live: running components watch the "
                          "file and apply on save.", inner.w):
        if y < inner.y + inner.h:
            put(win, y, inner.x, line, attr("MUTED"))
            y += 1


def render_header(win, w: int, app):
    put(win, 0, 1, "Ghost Settings", attr("TITLE") | curses.A_BOLD)
    if w >= 64:
        put(win, 0, 16, G.SEP + " Omarchy desktop", attr("MUTED"))
    n = len(app.unsaved_keys())
    if n or app.needs_write:
        s = f"{G.MOD} unsaved ({n})" if n else f"{G.MOD} recovered - press s"
        put(win, 0, w - len(s) - 1, s, attr("WARN"))
    else:
        s = f"all saved {G.CHECK}"
        put(win, 0, w - len(s) - 1, s, attr("MUTED"))
    if app.clamp_note and w > 60:
        put(win, 0, w - len(s) - 3 - len(app.clamp_note),
            app.clamp_note, attr("WARN"))


def render_hints(win, r_context: Rect, r_global: Rect,
                 context: str, glob: str, summary: str):
    put(win, r_context.y, 1, context[:r_context.w - 2], attr("MUTED"))
    put(win, r_global.y, 1, glob, attr("MUTED"))
    x = 1 + len(glob) + 1
    put(win, r_global.y, x, G.V, attr("MUTED"))
    put(win, r_global.y, x + 2, summary[:max(0, r_global.w - x - 3)],
        attr("MUTED"))
