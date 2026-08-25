"""ghost-settings schema — SPEC is the single source of truth.

Every consumer (sill, the future TUI, the TOML emitter, validation) derives
from SPEC; adding a setting is one line here. Field kinds mirror
docs/ghost-settings-design.md §5, with the Sill schema delta from
docs/sill-plan.md §3 applied: [shelf]+[stash] merged into [sill],
[stash.capture] and the links tab deleted, bar sections unchanged.
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Field:
    key: str
    label: str
    doc: str = ""
    gate: str | None = None  # dotted key; field locked unless truthy


@dataclass(frozen=True)
class Toggle(Field):
    default: bool = False


@dataclass(frozen=True)
class Number(Field):
    default: int = 0
    min: int = 0
    max: int = 100
    step: int = 1
    unit: str = ""
    zero_means: str = ""  # e.g. "never"


@dataclass(frozen=True)
class Choice(Field):
    default: str = ""
    options: tuple[str, ...] = ()


NINE_POINTS = ("top-left", "top", "top-right", "left", "center", "right",
               "bottom-left", "bottom", "bottom-right")


@dataclass(frozen=True)
class NinePoint(Field):
    default: str = "top-right"


@dataclass(frozen=True)
class Text(Field):
    default: str = ""


@dataclass(frozen=True)
class StrList(Field):
    default: tuple[str, ...] = ()


@dataclass(frozen=True)
class Section:
    key: str            # TOML table, dotted ok: "bar.media"
    title: str          # sidebar label (TUI, Phase 4)
    summary: str        # bottom-right summary text (TUI, Phase 4)
    fields: tuple[Field, ...] = field(default_factory=tuple)


SPEC: tuple[Section, ...] = (
    Section("general", "General", "theme & motion", (
        Toggle("follow_theme", "Follow Omarchy theme", default=True,
               doc="Recolour components when the Omarchy theme changes."),
        Toggle("animations", "Animations (master)", default=True,
               doc="Master switch; any per-app \"follow\" resolves to this."),
    )),
    Section("sill", "Sill", "panel, tabs, history", (
        NinePoint("position", "Position", default="top-right",
                  doc="Where the chip and expanded panel anchor.\n"
                      "NOTE: in Phase 1 the window itself is placed by a\n"
                      "Hyprland rule in ~/.config/hypr/windows.lua; only\n"
                      "top-right is wired up."),
        Number("margin", "Margin", default=10, min=0, max=128, step=2,
               unit="px", doc="Gap between the panel and the screen edge."),
        Toggle("keybind_toggle", "Toggle keybind", default=True,
               doc="SUPER+SHIFT+V toggles the panel (bound in bindings.lua)."),
        Toggle("expand_on_hover", "Expand on hover", default=True,
               doc="Expand when the pointer rests on the bar's empty space\n"
                   "(needs the ghost.sillhover plugin — Phase 5)."),
        Toggle("expand_on_drag", "Expand on drag", default=True,
               doc="Expand when a drag hovers the chip (Phase 5)."),
        Toggle("expand_on_click", "Expand on click", default=True,
               doc="Expand when the chip is clicked."),
        Number("hover_delay_ms", "Hover delay", default=300, min=0, max=2000,
               step=50, unit="ms", gate="sill.expand_on_hover",
               doc="Delay before a hover expands the panel."),
        Number("collapse_s", "Auto-collapse after", default=15, min=0, max=120,
               unit="s", zero_means="never",
               doc="Seconds before an auto-expanded panel folds back into\n"
                   "the chip. 0 = never auto-collapse."),
        Number("max_items", "Max items", default=200, min=10, max=1000,
               step=10, doc="Clipboard entries shown (Phase 2)."),
        Number("max_age_days", "Max age", default=7, min=0, max=90,
               unit="days", zero_means="keep forever",
               doc="Drop clipboard entries older than this (Phase 2)."),
        Toggle("disable_omarchy_clipboard", "Disable Omarchy clipboard",
               default=False,
               doc="Unbind SUPER+CTRL+V only. The Quickshell plugin stays\n"
                   "loaded — it owns the wl-paste capture watchers Sill\n"
                   "depends on (Phase 2)."),
        Toggle("purge_on_lock", "Purge on lock", default=False,
               doc="Purge clipboard history when the session locks (Phase 2)."),
    )),
    Section("sill.screenshots", "Screenshots", "history & actions", (
        Number("max_history", "Max history", default=10, min=1, max=50,
               doc="Screenshots kept in the shelf strip."),
        Toggle("copy", "Copy actions", default=True,
               doc="Show the Copy path / Copy image buttons."),
        Toggle("edit", "Edit action", default=True,
               doc="Show the Edit button (OMARCHY_SCREENSHOT_EDITOR)."),
        Toggle("ocr", "OCR action", default=False,
               doc="Reserved; not implemented in Phase 1."),
        Toggle("share", "Share action", default=False,
               doc="Reserved; not implemented in Phase 1."),
        Toggle("save_as", "Save-as action", default=False,
               doc="Reserved; not implemented in Phase 1."),
        Toggle("drag", "Drag out", default=True,
               doc="Thumbnails and the chip are drag sources."),
        Toggle("trash", "Trash action", default=True,
               doc="Right-click a fan thumbnail removes it from the shelf\n"
                   "(the file on disk is never auto-deleted)."),
    )),
    Section("sill.privacy", "Privacy", "app denylist", (
        StrList("denylist", "Denylist",
                default=("org.keepassxc.KeePassXC", "1Password.*",
                         "Bitwarden", "Alacritty", "kitty", "foot",
                         "org.codeberg.dnkl.foot", "com.mitchellh.ghostty",
                         "wezterm", "org.omarchy.terminal", "TUI[.].*"),
                doc="Window classes whose clipboard entries are deleted\n"
                    "reactively — each entry a case-insensitive regex\n"
                    "full-matched against the focused window class when the\n"
                    "entry lands (~300 ms after capture; if focus moved in\n"
                    "between, the check misses — honest limit, see\n"
                    "CUSTOMISATIONS.md §6e). Default: password managers +\n"
                    "terminals. org.omarchy.agent (Claude windows) is NOT\n"
                    "denied by default — add it if agent output is secret."),
    )),
    Section("bar.drawer", "Bar drawer", "collapsed status icons", (
        Toggle("enabled", "Drawer enabled", default=True,
               doc="Off = icons stay inline (Phase 6)."),
        Toggle("wifi", "Wifi in drawer", default=True),
        Toggle("bluetooth", "Bluetooth in drawer", default=True),
        Toggle("audio", "Audio in drawer", default=True),
        Toggle("display", "Display in drawer", default=True),
        Choice("expand_on", "Expand on", default="click",
               options=("click", "hover")),
        Number("auto_close_s", "Auto-close", default=5, min=0, max=30,
               unit="s", zero_means="stays open"),
    )),
    Section("bar.media", "Media", "now-playing pill", (
        Toggle("enabled", "Enabled", default=True),
        Number("max_title_chars", "Max title chars", default=32, min=10, max=80),
        Choice("scroll_title", "Scroll long titles", default="hover",
               options=("off", "hover", "always")),
        Toggle("show_progress", "Progress bar", default=True),
        Toggle("controls_on_hover", "Controls on hover", default=True),
        Number("hide_after_pause_s", "Hide after pause", default=60, min=0,
               max=600, unit="s", zero_means="never hide"),
    )),
    Section("bar.sysmon", "Sysmon", "cpu / mem / temp / net", (
        Toggle("enabled", "Enabled", default=True),
        Toggle("cpu", "CPU", default=True),
        Toggle("mem", "Memory", default=True),
        Toggle("temp", "Temperature", default=False),
        Toggle("net", "Network", default=False),
        Number("interval_s", "Interval", default=3, min=1, max=30, unit="s"),
        Choice("style", "Style", default="bars", options=("bars", "text")),
        Number("cpu_warn_pct", "CPU warn", default=85, min=50, max=100,
               unit="%"),
    )),
    Section("bar.pomodoro", "Pomodoro", "focus timer", (
        Toggle("enabled", "Enabled", default=True),
        Number("work_min", "Work", default=25, min=5, max=120, step=5,
               unit="min"),
        Number("short_break_min", "Short break", default=5, min=1, max=30,
               unit="min"),
        Number("long_break_min", "Long break", default=15, min=5, max=60,
               step=5, unit="min"),
        Number("cycles", "Cycles to long break", default=4, min=2, max=8),
        Choice("autostart", "Auto-start next", default="breaks",
               options=("off", "breaks", "all")),
        Toggle("notify", "Notify on phase end", default=True),
        Toggle("show_when_idle", "Show when idle", default=False),
    )),
    Section("bar.notes", "Notes", "scratchpad", (
        Toggle("enabled", "Enabled", default=True),
        Text("file", "Notes file", default="~/.local/share/ghost/notes.md"),
        Toggle("show_count", "Show count", default=True),
    )),
)


def known_keys() -> set[str]:
    return {f"{sec.key}.{fld.key}" for sec in SPEC for fld in sec.fields}


def field_for(dotted: str):
    """Return (Section, Field) for a dotted key, or (None, None)."""
    for sec in SPEC:
        for fld in sec.fields:
            if f"{sec.key}.{fld.key}" == dotted:
                return sec, fld
    return None, None
