# ghost-settings — design

A curses TUI that configures every custom piece of this desktop from one place:
the screenshot shelf (`ghost-shotshelf`, GTK4/Python), the stash panel
(`ghost-stash`, GTK4), the four Quickshell bar widgets
(`bar/modules/{mediapill,sysmon,pomodoro,notes}.qml`), the bar's icon drawer,
and two general switches. Shaped after `voxtype configure`: sidebar of
categories with a `▶` cursor, boxed panels with titles in the border, a legend,
two rows of keybind hints, monochrome, keyboard only.

Decisions up front:

| Decision      | Choice                                                          |
|---------------|-----------------------------------------------------------------|
| Name          | `ghost-settings` (fits the `ghost-*` family)                    |
| Language      | Python 3, stdlib only (`curses`, `tomllib`, `dataclasses`)      |
| Config        | One TOML file: `~/.config/ghost/settings.toml`                  |
| Live apply    | Atomic write + per-app file watch (inotify via Gio / FileView)  |
| Theme         | 256-colour quantisation of the active Omarchy `colors.toml`     |
| Install       | `~/.local/share/ghost-settings/` + launcher in `~/.local/bin`   |

---

## 1 · Screens

Reference terminal: `foot -W 100x32`. Layout constants: sidebar 17 cols,
`│` separator, content 82 cols. All boxes carry their title in the top border,
`voxtype`-style. Focused box border uses the accent colour; unfocused, muted.

### 1.1 Landing — Overview

First screen on launch. Read-only dashboard: component status, active theme,
config health. `● running` is detected per component (see §7).

```
 Ghost Settings · Omarchy desktop                                                      all saved ✓
▶ Overview       │┌Components──────────────────────────────────────────────────────────────────────┐
  General        ││ Shelf      ● running    pill bottom-right · collapse 2.5 s · history 10        │
  Shelf          ││ Stash      ● running    3 tabs · 187 items · denylist 3 apps                   │
  Stash          ││ Bar        ● running    drawer on (4 icons) · media · sysmon · pomodoro · notes│
  Bar            │└────────────────────────────────────────────────────────────────────────────────┘
  · Media        │┌Theme─────────────────────────────────┐┌Config──────────────────────────────────┐
  · Sysmon       ││ monochrome  (dark)                   ││ ~/.config/ghost/settings.toml          │
  · Pomodoro     ││ accent #8f979c  ▓▓   fg #dfe3e6  ▓▓  ││ valid · 43 keys · saved 09:41          │
  · Notes        ││ follow Omarchy theme   on            ││ backup settings.toml.bak · ok          │
                 ││ animations master      on            ││ live consumers: shelf stash bar        │
                 ││                                      ││                                        │
                 ││                                      ││                                        │
                 │└──────────────────────────────────────┘└────────────────────────────────────────┘
                 │
                 │ ● running   ○ stopped   ✱ unsaved   — locked by dependency   ◂ ▸ adjustable
                 │
                 │
                 │ Enter a category to edit · everything applies live on save
 ↑↓ navigate · Enter open · Tab content · ? help · q quit │  components & config at a glance
```

- Row 1: app title left, save-state right (`all saved ✓` / `✱ unsaved (n)`).
- Second-to-last row: context hints for the focused pane (changes per screen).
- Last row: global hints, fixed, then `│` and a one-line summary of the
  selected category (mirrors voxtype's bottom-right summary).
- The legend row sits in the content column, exactly like voxtype's symbol
  legend above its hint rows.

### 1.2 Category screen — settings list (Shelf shown)

Same chrome; content splits into a `Settings` field list and an `About` panel
describing the *focused* field (its doc text, current/default, live-apply
note). Every category screen is this same generic widget fed by the schema —
no per-category screen code (§5).

```
 Ghost Settings · Omarchy desktop                                                    ✱ unsaved (2)
  Overview       │┌Settings────────────────────────────────────┐┌About─────────────────────────────┐
  General        ││▸ Position                    bottom-right ▸││Position                          │
▶ Shelf ✱        ││                                            ││                                  │
  Stash          ││  Margin (px)                         ◂ 12 ▸││Where the pill and expanded       │
  Bar            ││  Auto-collapse                       ◂ on ▸││shelf anchor on the monitor.      │
  · Media        ││  Collapse after (ms) ✱             ◂ 2500 ▸││Nine positions; Enter opens the   │
  · Sysmon       ││  Pill expires                       ◂ off ▸││visual picker.                    │
  · Pomodoro     ││  Expire after (min)                  — 15 —││                                  │
  · Notes        ││                                            ││current   bottom-right            │
                 ││  Actions ✱                      5 of 7 on ▸││default   bottom-right            │
                 ││  Animations                      ◂ follow ▸││                                  │
                 ││  Max history                         ◂ 10 ▸││Applies live: the running shelf   │
                 ││                                            ││re-anchors its layer surface on   │
                 ││                                            ││save, no restart.                 │
                 │└────────────────────────────────────────────┘└──────────────────────────────────┘
                 │
                 │ ↑↓ field · ←→ adjust · Enter edit · u undo · s save · r revert · Esc sidebar
 ↑↓ navigate · Enter open · Tab content · ? help · q quit │  Shelf · pill, actions, history
```

Field grammar (one line each, value cluster right-aligned):

| Rendering                          | Meaning                                            |
|------------------------------------|----------------------------------------------------|
| `▸ Name` / `  Name`                | focused / unfocused field                          |
| `Name ✱`                           | staged change, not yet saved                       |
| `◂ value ▸`                        | adjustable in place with ← →                       |
| `value ▸` (no `◂`)                 | Enter opens a dedicated editor (picker/list/text)  |
| `— value —`                        | locked: its gate is off (here `Pill expires`)      |
| `5 of 7 on ▸`                      | summarised composite (the Actions toggle set)      |

Blank rows group related fields. Locked fields are skipped by ↑↓ (dimmed,
still visible so the layout never jumps).

### 1.3 Nine-point position picker (modal)

Opened with Enter on `Position`. The grid **is** a miniature of the monitor:
you arrow the pill itself around the screen. The nine anchor points show as
faint `·` dots with their jump digit; the saved position is `○`; the focused
position is drawn as the pill glyph, to scale, hugging the edge it would hug.

```
 Ghost Settings · Omarchy desktop                                                    ✱ unsaved (2)
                 │┌Shelf · Position────────────────────────────────────────────────────────────────┐
                 ││                                                                                │
  (sidebar       ││        ┌──────────────────── eDP-1 · 2944×1840 ──────────────────────┐         │
   dimmed)       ││        │ ·1                 ·2                                     ·3│         │
                 ││        │                                                             │         │
                 ││        │                                                             │         │
                 ││        │ ·4                 ·5                                     ·6│         │
                 ││        │                                                             │         │
                 ││        │                                                             │         │
                 ││        │ ·7                 ○8                            ▐▬▬▬▬▬▬▬▬▌9│         │
                 ││        └─────────────────────────────────────────────────────────────┘         │
                 ││                                                                                │
                 ││              position  bottom-right        saved  bottom-center                │
                 ││              margin    ◂ 12 px ▸           ▐▬▬▌  the pill, drawn to scale      │
                 ││                                                                                │
                 ││      arrows / hjkl move · 1-9 jump · -+ margin · Space preview · Enter apply   │
                 ││                                                                                │
                 │└────────────────────────────────────────────────────────────────────────────────┘
                 │
                 │ Space holds a live preview on the real desktop; release restores
 Enter apply · Esc cancel · ? help                        │  pick where the shelf lives
```

Feel:

- Arrows/`hjkl` move one cell; edges clamp (no wrap — it's a spatial map, the
  corner should feel like a corner). Digits `1`–`9` jump directly (reading
  order, matching the printed digits).
- The pill glyph re-renders at the new anchor instantly; corner cells draw it
  flush into the corner, edge cells centred on the edge — the mini-monitor
  always shows exactly what the desktop will do.
- `-`/`+` adjusts margin without leaving the picker; the pill nudges 1 char
  off the border when margin > 0 so the change is visible.
- `Space` (hold) writes a preview to the real config so the actual shelf jumps
  there; on release the previous bytes are restored (§6, preview). `Enter`
  stages the value (marks ✱); `Esc` abandons.
- The monitor title comes from the compositor (`hyprctl monitors -j`); on a
  multi-monitor setup ` Tab ` cycles which output the grid depicts (the shelf
  anchors per-output).

### 1.4 List editor (modal) — used by `Stash · Privacy denylist`

Small centred box over the category screen:

```
                 ┌Stash · Privacy denylist──────────────┐
                 │ app-ids / window classes never       │
                 │ captured                             │
                 │                                      │
                 │ ▸ org.keepassxc.KeePassXC            │
                 │   1Password                          │
                 │   signal                             │
                 │                                      │
                 │ a add · e edit · d delete · Esc done │
                 └──────────────────────────────────────┘
```

`a`/`e` open a one-line input at the row (cursor visible, Enter commits,
Esc cancels). `d` asks nothing — a just-deleted row can be restored with `u`
while the modal is open. Closing the modal stages the list (✱).

### 1.5 Help overlay

`?` anywhere pushes a centred box listing every key for the current screen
plus the globals. Any key closes it.

---

## 2 · Category tree — every setting

Types: **T** toggle · **C** choice · **N** number (min–max, step) · **S** text ·
**L** string list · **P** nine-point position. “gate:” = field is locked
unless the named field is on.

### Overview
Read-only dashboard, no settings.

### General `[general]`
| Setting              | Key            | Type | Default | Range / options |
|----------------------|----------------|------|---------|-----------------|
| Follow Omarchy theme | `follow_theme` | T    | on      |                 |
| Animations (master)  | `animations`   | T    | on      | per-app `follow` resolves to this |

### Shelf `[shelf]`
| Setting             | Key             | Type | Default        | Range / options |
|---------------------|-----------------|------|----------------|-----------------|
| Position            | `position`      | P    | `bottom-right` | 9 anchors       |
| Margin (px)         | `margin`        | N    | 12             | 0–128, step 2   |
| Auto-collapse       | `auto_collapse` | T    | on             |                 |
| Collapse after (ms) | `collapse_ms`   | N    | 2500           | 500–10000, step 250 · gate: auto_collapse |
| Pill expires        | `expires`       | T    | off            |                 |
| Expire after (min)  | `expire_min`    | N    | 15             | 1–120 · gate: expires |
| Actions             | `actions.*`     | 7×T  | see below      | opens toggle-set modal |
| Animations          | `animations`    | C    | `follow`       | follow / on / off |
| Max history         | `max_history`   | N    | 10             | 1–50            |

Actions (`[shelf.actions]`): `copy` on · `edit` on · `ocr` on · `share` off ·
`save_as` on · `drag` on · `trash` on.

### Stash `[stash]`
| Setting             | Key              | Type | Default | Range / options |
|---------------------|------------------|------|---------|-----------------|
| Enabled             | `enabled`        | T    | on      | gates the whole section |
| Tabs: clips         | `tabs.clips`     | T    | on      |                 |
| Tabs: files         | `tabs.files`     | T    | on      |                 |
| Tabs: images        | `tabs.images`    | T    | on      |                 |
| Tabs: links         | `tabs.links`     | T    | off     |                 |
| Capture text        | `capture.text`   | T    | on      |                 |
| Capture images      | `capture.images` | T    | on      |                 |
| Capture files       | `capture.files`  | T    | on      |                 |
| Dedupe consecutive  | `capture.dedupe` | T    | on      |                 |
| Min text length     | `capture.min_text_len` | N | 3  | 1–64            |
| Privacy denylist    | `privacy.denylist` | L  | KeePassXC, 1Password | app-ids / classes |
| Hover to expand     | `hover_expand`   | T    | on      |                 |
| Hover delay (ms)    | `hover_delay_ms` | N    | 300     | 0–2000, step 50 · gate: hover_expand |
| Max items           | `max_items`      | N    | 200     | 10–1000, step 10 |
| Max age (days)      | `max_age_days`   | N    | 14      | 0–90 · 0 = keep forever |

### Bar `[bar.drawer]`
| Setting            | Key           | Type | Default | Range / options |
|--------------------|---------------|------|---------|-----------------|
| Drawer enabled     | `enabled`     | T    | on      | off = icons stay inline |
| Wifi in drawer     | `wifi`        | T    | on      |                 |
| Bluetooth in drawer| `bluetooth`   | T    | on      |                 |
| Audio in drawer    | `audio`       | T    | on      |                 |
| Display in drawer  | `display`     | T    | on      |                 |
| Expand on          | `expand_on`   | C    | `click` | click / hover   |
| Auto-close (s)     | `auto_close_s`| N    | 5       | 0–30 · 0 = stays open |

### Media `[bar.media]`
| Setting             | Key                  | Type | Default | Range / options |
|---------------------|----------------------|------|---------|-----------------|
| Enabled             | `enabled`            | T    | on      |                 |
| Max title chars     | `max_title_chars`    | N    | 32      | 10–80           |
| Scroll long titles  | `scroll_title`       | C    | `hover` | off / hover / always |
| Progress bar        | `show_progress`      | T    | on      |                 |
| Controls on hover   | `controls_on_hover`  | T    | on      |                 |
| Hide after pause (s)| `hide_after_pause_s` | N    | 60      | 0–600 · 0 = never hide |

### Sysmon `[bar.sysmon]`
| Setting          | Key           | Type | Default | Range / options |
|------------------|---------------|------|---------|-----------------|
| Enabled          | `enabled`     | T    | on      |                 |
| CPU              | `cpu`         | T    | on      |                 |
| Memory           | `mem`         | T    | on      |                 |
| Temperature      | `temp`        | T    | off     |                 |
| Network          | `net`         | T    | off     |                 |
| Interval (s)     | `interval_s`  | N    | 3       | 1–30            |
| Style            | `style`       | C    | `bars`  | bars / text     |
| CPU warn (%)     | `cpu_warn_pct`| N    | 85      | 50–100 · emphasised above |

### Pomodoro `[bar.pomodoro]`
| Setting               | Key               | Type | Default  | Range / options |
|-----------------------|-------------------|------|----------|-----------------|
| Enabled               | `enabled`         | T    | on       |                 |
| Work (min)            | `work_min`        | N    | 25       | 5–120, step 5   |
| Short break (min)     | `short_break_min` | N    | 5        | 1–30            |
| Long break (min)      | `long_break_min`  | N    | 15       | 5–60, step 5    |
| Cycles to long break  | `cycles`          | N    | 4        | 2–8             |
| Auto-start next       | `autostart`       | C    | `breaks` | off / breaks / all |
| Notify on phase end   | `notify`          | T    | on       |                 |
| Show when idle        | `show_when_idle`  | T    | off      |                 |

### Notes `[bar.notes]`
| Setting     | Key          | Type | Default                          | Range |
|-------------|--------------|------|----------------------------------|-------|
| Enabled     | `enabled`    | T    | on                               |       |
| Notes file  | `file`       | S    | `~/.local/share/ghost/notes.md`  | `~` expanded; created on first write |
| Show count  | `show_count` | T    | on                               |       |

43 keys total.

---

## 3 · Interaction spec

Two focus zones — sidebar and content — plus a modal stack. Input always goes
to the top of the stack; unconsumed keys fall through to the globals.

### Global (any screen, unless a text input is open)
| Key         | Action |
|-------------|--------|
| `q`         | quit; if unsaved → confirm dialog: `s` save & quit · `d` discard & quit · `Esc` stay |
| `Ctrl+C`    | same as `q` (never a raw crash-out) |
| `?`         | help overlay for current screen |
| `Tab`       | jump focus sidebar ⇄ content |
| `s`         | save **all** staged changes (atomic write, §6) |

### Sidebar focused
| Key                | Action |
|--------------------|--------|
| `↑` `↓` / `k` `j`  | move category cursor (wraps) |
| `Enter` / `→` / `l`| open category: focus moves into its field list |
| `g` / `G`          | first / last category |

### Field list focused
| Key                 | Action |
|---------------------|--------|
| `↑` `↓` / `k` `j`   | move field cursor; skips locked fields; About panel follows |
| `←` `→` / `h` `l`   | adjust in place: toggle flips; choice cycles (wraps); number ±step |
| `Shift+←/→` or `H` `L` | number ±10×step, clamped at range ends |
| `Space`             | flip a toggle (same as ←→) |
| `Enter`             | toggles: flip · choice: cycle · number/text: inline edit · P/L: open modal |
| `0`–`9`             | on a number field: start inline edit with that digit |
| `u`                 | undo focused field to last-saved value |
| `r`                 | revert whole category to last-saved (confirm dialog) |
| `Esc` / `←` on first column | back to sidebar |

### Inline edit (number/text; a cursor appears in the value area)
| Key             | Action |
|-----------------|--------|
| printable keys  | edit buffer (numbers accept digits only) |
| `Enter`         | commit → validate: numbers clamp to range with a one-beat `clamped to 128` flash in the context row; stage (✱) |
| `Esc`           | abandon buffer, restore displayed value |

### Modals (picker §1.3, list editor §1.4, confirm, help)
`Esc` always closes without effect (confirm dialogs treat it as "cancel").
Keys as printed in each modal's own hint row.

### Unsaved-change model
- Edits are **staged in memory**, never auto-written. Three indicators, all
  redundant: `✱` on the field, `✱` on the sidebar category, `✱ unsaved (n)`
  top-right.
- `s` writes everything atomically and flips the header to `all saved ✓`.
  Apps apply within ~100 ms (§6) — save *is* apply.
- `u`/`r` operate against the last-saved state, not defaults. Restoring a
  field to its saved value clears its ✱.
- If the file changed on disk since load (hand edit in another terminal), `s`
  prompts: `changed on disk — R reload & re-stage my edits · O overwrite`.

---

## 4 · Config file — as it ships

`~/.config/ghost/settings.toml`. TOML because: `tomllib` reads it from the
stdlib; it carries comments (this file is also the documentation); it is the
Omarchy house format (`colors.toml`, `alacritty.toml`). Writing TOML has no
stdlib support, but the schema is the single source of truth, so
`ghost-settings` *regenerates* the file from the schema on save — comments
included, unknown keys preserved verbatim in a trailing block. QML can't parse
TOML; the bar reads it through `ghost-settings dump --json` (§6).

```toml
# ghost desktop — one config for shelf, stash, and bar widgets.
# Written by `ghost-settings`; hand-editing is fine — every running component
# watches this file and applies changes on save. Out-of-range values are
# clamped on load; unknown keys are kept but ignored.

[general]
follow_theme = true         # recolour components when the Omarchy theme changes
animations = true           # master switch; any per-app "follow" resolves to this

[shelf]
position = "bottom-right"   # top-left|top|top-right|left|center|right|bottom-left|bottom|bottom-right
margin = 12                 # px from the screen edge (0-128)
auto_collapse = true        # fold into the pill after a capture
collapse_ms = 2500          # ms before folding (500-10000)
expires = false             # true: the pill disappears after expire_min
expire_min = 15             # minutes (1-120)
animations = "follow"       # follow|on|off
max_history = 10            # captures kept in the shelf (1-50)

[shelf.actions]             # buttons shown on the expanded shelf
copy = true
edit = true
ocr = true
share = false
save_as = true
drag = true
trash = true

[stash]
enabled = true
hover_expand = true         # expand the panel on pointer hover
hover_delay_ms = 300        # ms before expanding (0-2000)
max_items = 200             # kept per tab (10-1000)
max_age_days = 14           # drop items older than this; 0 = keep forever (0-90)

[stash.tabs]
clips = true
files = true
images = true
links = false

[stash.capture]
text = true
images = true
files = true
dedupe = true               # drop consecutive duplicates
min_text_len = 3            # ignore clips shorter than this (1-64)

[stash.privacy]
# app-ids / window classes whose clipboard is never captured
denylist = [
  "org.keepassxc.KeePassXC",
  "1Password",
]

[bar.drawer]                # wifi/bt/audio/display collapsed into one group
enabled = true
wifi = true
bluetooth = true
audio = true
display = true
expand_on = "click"         # click|hover
auto_close_s = 5            # collapse again after n seconds; 0 = stay open (0-30)

[bar.media]
enabled = true
max_title_chars = 32        # truncate titles beyond this (10-80)
scroll_title = "hover"      # off|hover|always
show_progress = true
controls_on_hover = true
hide_after_pause_s = 60     # hide the pill n seconds after playback pauses; 0 = never (0-600)

[bar.sysmon]
enabled = true
cpu = true
mem = true
temp = false
net = false
interval_s = 3              # refresh period (1-30)
style = "bars"              # bars|text
cpu_warn_pct = 85           # emphasise the readout above this (50-100)

[bar.pomodoro]
enabled = true
work_min = 25               # (5-120)
short_break_min = 5         # (1-30)
long_break_min = 15         # (5-60)
cycles = 4                  # work blocks before a long break (2-8)
autostart = "breaks"        # off|breaks|all — what starts without a click
notify = true
show_when_idle = false      # keep the widget visible with no timer running

[bar.notes]
enabled = true
file = "~/.local/share/ghost/notes.md"
show_count = true           # show open-item count in the bar
```

---

## 5 · Code structure

```
~/.local/share/ghost-settings/
  main.py          # argparse: TUI (default) | get | set | dump --json | check
  schema.py        # SPEC — the single source of truth (all sections/fields)
  config.py        # load / clamp / diff / atomic save / TOML emitter
  theme.py         # colors.toml → curses colour pairs (+ attr fallbacks)
  tui/
    app.py         # curses bootstrap, event loop, screen stack, resize
    draw.py        # put(), boxed(), glyph sets (unicode/ascii)
    widgets.py     # Sidebar, FieldList, About, StatusRows
    screens.py     # OverviewScreen, CategoryScreen, PositionPicker,
                   # ListEditor, Confirm, Help — all subclasses of Screen
```

The anti-spaghetti rule: **screens never know settings**. `CategoryScreen` is
one generic widget instantiated with a `Section` from the schema; adding a
setting is one line in `schema.py` (the TOML emitter, the field list, the
About panel, validation, and the CLI all derive from it).

### schema.py

```python
from dataclasses import dataclass

@dataclass(frozen=True)
class Field:
    key: str; label: str; doc: str = ""
    gate: str | None = None          # dotted key; field locked unless truthy

@dataclass(frozen=True)
class Toggle(Field):
    default: bool = False

@dataclass(frozen=True)
class Number(Field):
    default: int = 0; min: int = 0; max: int = 100
    step: int = 1; unit: str = ""; zero_means: str = ""   # e.g. "never"

@dataclass(frozen=True)
class Choice(Field):
    default: str = ""; options: tuple[str, ...] = ()

@dataclass(frozen=True)
class NinePoint(Field):
    default: str = "bottom-right"
    OPTIONS = ("top-left", "top", "top-right", "left", "center", "right",
               "bottom-left", "bottom", "bottom-right")

@dataclass(frozen=True)
class Text(Field):     default: str = ""
@dataclass(frozen=True)
class StrList(Field):  default: tuple[str, ...] = ()

@dataclass(frozen=True)
class Section:
    key: str            # TOML table, dotted ok: "bar.media"
    title: str          # sidebar label
    summary: str        # bottom-right summary text
    fields: tuple[Field, ...]

SPEC: tuple[Section, ...] = (
    Section("general", "General", "theme & motion", (
        Toggle("follow_theme", "Follow Omarchy theme", default=True,
               doc="Recolour components when the Omarchy theme changes."),
        Toggle("animations", "Animations (master)", default=True),
    )),
    Section("shelf", "Shelf", "pill, actions, history", (
        NinePoint("position", "Position",
                  doc="Where the pill and expanded shelf anchor.\n"
                      "Applies live: the shelf re-anchors on save."),
        Number("margin", "Margin", default=12, min=0, max=128, step=2, unit="px"),
        Toggle("auto_collapse", "Auto-collapse", default=True),
        Number("collapse_ms", "Collapse after", default=2500, min=500,
               max=10000, step=250, unit="ms", gate="shelf.auto_collapse"),
        # ...
    )),
    # ... stash, bar.drawer, bar.media, bar.sysmon, bar.pomodoro, bar.notes
)
```

### config.py — load, clamp, save

```python
def load(path) -> tuple[dict[str, object], list[str]]:
    """Returns flat {dotted_key: value} and warnings. Never raises:
    parse failure → try path.bak → schema defaults (warning either way)."""
    for candidate in (path, path.with_suffix(".toml.bak")):
        try:
            with open(candidate, "rb") as f:
                raw = tomllib.load(f)
            break
        except FileNotFoundError:
            raw = {}; break
        except (OSError, tomllib.TOMLDecodeError) as e:
            warn(f"{candidate.name}: {e}")
    else:
        raw = {}
    vals = {}
    for sec in SPEC:
        for fld in sec.fields:
            v = dig(raw, sec.key, fld.key, fld.default)
            vals[f"{sec.key}.{fld.key}"] = fld_clamp(fld, v)  # type+range coerce
    vals["_unknown"] = collect_unknown(raw)     # preserved verbatim on save
    return vals, warnings

def save(path, vals):
    if parses_ok(path):                        # keep last-known-good
        shutil.copy2(path, path.with_suffix(".toml.bak"))
    text = emit_toml(vals)                     # regenerated from SPEC + comments
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".settings-")
    os.write(fd, text.encode()); os.fsync(fd); os.close(fd)
    os.replace(tmp, path)                      # atomic → one inotify event
```

### theme.py — Omarchy colours → curses

```python
THEME = Path("~/.local/state/omarchy/current/theme/colors.toml").expanduser()
# (same file as ~/.config/omarchy/current/theme/colors.toml — a symlink pair)

def to_256(hexstr):                    # nearest xterm entry: 6x6x6 cube vs grey ramp
    r, g, b = bytes.fromhex(hexstr.lstrip("#"))
    cube = tuple(0 if c < 48 else 1 + (c - 35) // 40 for c in (r, g, b))
    grey = max(0, min(23, (((r + g + b) // 3) - 8) // 10))
    return best_of(16 + 36*cube[0] + 6*cube[1] + cube[2], 232 + grey, (r, g, b))

ROLES = {   # role: (theme key, mono fallback attr)
    "NORMAL": ("foreground",        curses.A_NORMAL),
    "MUTED":  ("muted",             curses.A_DIM),
    "ACCENT": ("accent",            curses.A_BOLD),
    "TITLE":  ("light_foreground",  curses.A_BOLD),
    "WARN":   ("bright_yellow",     curses.A_BOLD | curses.A_UNDERLINE),
    "SEL":    ("selection",         curses.A_REVERSE),   # used as background
}

def attr(role) -> int:
    """color_pair() when 256 colours are up; the fallback attr otherwise.
    Every call site uses attr() — nothing touches pairs directly."""
```

`init()` respects `NO_COLOR`, `curses.has_colors()`, and `COLORS < 256`
(8/16-colour terminals get default fg + attrs only). `SEL` pairs `foreground`
on `selection` for the sidebar cursor row and picker cells.

### tui/draw.py — boxes with titles, safe writes, glyphs

```python
def put(win, y, x, s, a=0):
    h, w = win.getmaxyx()
    if 0 <= y < h and x < w:
        try: win.addnstr(y, max(x, 0), s, w - x, a)
        except curses.error: pass          # bottom-right cell write is legal

def boxed(win, r, title="", focus=False):
    """Draw a border with the title embedded in the top rule; return r.inset(1)."""
    a = attr("ACCENT") if focus else attr("MUTED")
    top = G.TL + title + G.H * (r.w - 2 - len(title)) + G.TR
    put(win, r.y, r.x, top, a)
    if title:
        put(win, r.y, r.x + 1, title, attr("TITLE") | (curses.A_BOLD if focus else 0))
    for i in range(1, r.h - 1):
        put(win, r.y + i, r.x, G.V, a); put(win, r.y + i, r.x + r.w - 1, G.V, a)
    put(win, r.y + r.h - 1, r.x, G.BL + G.H * (r.w - 2) + G.BR, a)
    return r.inset(1)

UNICODE = Glyphs(TL="┌", TR="┐", BL="└", BR="┘", H="─", V="│", CUR="▶",
                 FLD="▸", ADJ_L="◂", ADJ_R="▸", MOD="✱", ON="●", OFF="○",
                 DOT="·", PILL="▐▬▬▌", LOCK="—")
ASCII   = Glyphs(TL="+", TR="+", BL="+", BR="+", H="-", V="|", CUR=">",
                 FLD=">", ADJ_L="<", ADJ_R=">", MOD="*", ON="*", OFF="o",
                 DOT=".", PILL="[==]", LOCK="-")
G = UNICODE if "UTF-8" in locale expected else ASCII
```

`Rect` is a tiny frozen dataclass (`y x h w`, `.inset()`, `.split_h()`,
`.split_v()`); all layout is Rect math on the real screen — **no subwindows**
(`derwin` resize behaviour is the classic curses spaghetti source).

### tui/app.py — event loop, stack, resize

```python
class Screen:
    def layout(self, rect): ...        # cache Rects; no drawing
    def render(self, win): ...         # draw everything from state
    def handle(self, key) -> bool: ... # True = consumed

class App:
    def __init__(self, stdscr, cfg):
        self.stack: list[Screen] = [MainScreen(self)]   # modals push on top

    def run(self):
        while self.running:
            self.stdscr.erase()
            for scr in self.stack:                 # bottom-up: modals overlay
                scr.render(self.stdscr)
            self.stdscr.refresh()
            try:
                key = self.stdscr.get_wch()        # blocking; wide-char aware
            except curses.error:
                continue
            if key == curses.KEY_RESIZE:
                self.relayout(); continue
            if not self.stack[-1].handle(key):
                self.handle_global(key)            # q ? Tab s

    def relayout(self):
        h, w = self.stdscr.getmaxyx()
        self.mode = ("full"  if w >= 84 and h >= 24 else
                     "stack" if w >= 60 and h >= 18 else "tiny")
        for scr in self.stack: scr.layout(Rect(0, 0, h, w))

def main():
    locale.setlocale(locale.LC_ALL, "")
    curses.wrapper(_run)          # guarantees terminal restore on any exception
```

Rendering is unconditional full-redraw per event — at 100×32 that is
microseconds; no dirty tracking, no flicker (curses diffs internally).
`MainScreen` owns Sidebar + the current `CategoryScreen` and routes keys by
which zone has focus. `PositionPicker`, `ListEditor`, `Confirm`, `Help` are
pushed modals; `Esc` pops.

---

## 6 · Live apply

**Mechanism: atomic file replace + per-app file watch.** Compared:

| Mechanism            | Verdict |
|----------------------|---------|
| Unix signal (SIGUSR1)| No payload → full reload anyway; needs PID discovery for 3+ processes; QML can't catch signals. No. |
| IPC socket / daemon  | A broker to write, install, supervise, and reconnect to; hand-edits with vim bypass it entirely. Overkill for one file. |
| D-Bus per app        | Free in GTK, awkward in the TUI, still bypassed by hand-edits. No. |
| **File watch**       | Works identically for TUI saves, `ghost-settings set`, and hand edits; zero discovery (the file *is* the rendezvous); restart-safe; the exact pattern the suite already uses for Omarchy theme switching. **Yes.** |

The one hazard of file watching — partial reads mid-write — is eliminated by
the writer, not the readers: `save()` writes a temp file in the same directory
and `os.replace()`s it, so watchers see exactly one event and always a
complete file.

**Consumers:**

Shelf / Stash (GTK4, Python):

```python
mon = Gio.File.new_for_path(CONFIG).monitor_file(Gio.FileMonitorFlags.NONE, None)
mon.connect("changed", lambda *_: debounce())          # 100 ms GLib timeout

def reload_config():
    new, _ = config.load(CONFIG)
    for key in (k for k in new if new[k] != current.get(k)):
        APPLY.get(key, apply_generic)(new[key])         # per-key handlers
    current.update(new)

APPLY = {
    "shelf.position":    lambda v: reanchor_layer_surface(v),   # gtk4-layer-shell margins/anchors
    "shelf.collapse_ms": lambda v: rearm_collapse_timer(v),
    "shelf.max_history": lambda v: trim_history(v),
    "general.animations": set_animations_enabled,
    # unlisted changed keys → apply_generic: rebuild the widget tree
}
```

Bar (Quickshell): one `SettingsStore` singleton; every widget binds to it.
QML has no TOML parser, so the store shells out to the same binary — one
source of truth for parsing *and* clamping:

```qml
// bar/modules/SettingsStore.qml  (pragma Singleton)
Singleton {
    id: store
    property var s: ({})                        // widgets bind: store.s.bar.media.enabled
    FileView { path: `${Quickshell.env("HOME")}/.config/ghost/settings.toml`
               watchChanges: true; onFileChanged: proc.running = true
               Component.onCompleted: proc.running = true }
    Process  { id: proc; command: ["ghost-settings", "dump", "--json"]
               stdout: StdioCollector { onStreamFinished: store.s = JSON.parse(text) } }
}
```

Because widgets *bind* to `store.s`, visibility and behaviour update the frame
the JSON lands — enabling the pomodoro widget or shrinking the media title is
instant, no bar restart.

**CLI surface** (same file, same rules, scriptable):
`ghost-settings get shelf.position` · `ghost-settings set shelf.margin 16`
(clamps, atomic write → live) · `ghost-settings dump --json` ·
`ghost-settings check` (exit 1 + line number if invalid).

**Picker preview (`Space`)**: the picker snapshots the file bytes, saves the
candidate position through the normal path, and restores the snapshot on
release/Esc. The real shelf visibly jumps — the preview *is* the production
apply path, so it can never lie. Restricted to cheap keys (`position`,
`margin`).

**Running/stopped detection (Overview)**: each app writes
`$XDG_RUNTIME_DIR/ghost/<name>.pid` on startup; Overview shows `● running`
iff the pid exists and `/proc/<pid>/cmdline` matches. No pgrep guessing.

---

## 7 · Robustness & accessibility

**Terminal size.** Three layout modes, re-evaluated on every `KEY_RESIZE`:

- `full` (≥ 84×24): everything above.
- `stack` (≥ 60×18): sidebar becomes a full-width category menu; Enter
  replaces it with the full-width field list (`Esc` back); the About panel is
  summoned per-field with `i` as a modal. Hint rows collapse to one.
- `tiny` (below): a centred, non-crashing notice —
  `ghost-settings needs at least 60×18 (now 45×12)` — that recovers the
  moment the terminal grows. Every render path writes through `put()`, which
  clips, so no size can raise.

**Colour.** Terminal capability tiers, all information colour-redundant
(✱/▸/—/●, never colour alone):

- 256 colours → quantised Omarchy palette (on this monochrome theme, curses
  output is greys matching the rest of the rice).
- 8/16 colours → default fg/bg plus `A_BOLD`/`A_DIM`/`A_REVERSE`.
- `NO_COLOR` set, or `has_colors()` false → attributes only.
- Non-UTF-8 locale → ASCII glyph set (`+--+` boxes, `>` cursors, `*` unsaved).
- Missing/unreadable `colors.toml` → tier 2 behaviour, plus a muted header
  note `theme unavailable`.

**Corrupt config.**

- Apps: `load()` never raises — bad file → `settings.toml.bak` (last
  known-good, refreshed before every successful save) → schema defaults.
  Components keep running on the fallback and log one warning. They never
  write the config, so a hand-edit mistake is never destroyed by an app.
- TUI: opens in a recovery banner — `settings.toml: TOML parse error, line 37`
  with `E` edit in `$EDITOR` (re-checks on exit), `B` restore backup, `D`
  stage defaults. Nothing touches the broken file until an explicit `s`.
- Out-of-range or wrong-typed values are clamped/coerced per field on load and
  listed once in the header (`3 values clamped`) so hand edits fail soft.

**Other.** Ctrl+C is caught (`curses.wrapper` + KeyboardInterrupt → same path
as `q`), so the terminal is always restored. The single-instance guard reuses
the pid-file check from §6. All state writes are atomic; a crash mid-save
cannot half-write the config.

---

## 8 · Launch integration

Launcher, matching the shelf's pattern —
`~/.local/bin/ghost-settings`:

```bash
#!/bin/bash
exec python3 "$HOME/.local/share/ghost-settings/main.py" "$@"
```

1. **Command**: `ghost-settings` in any terminal.
2. **Hyprland keybind** (`~/.config/hypr/bindings.lua`, house style — reuses
   the launch-or-focus helper already used for btop/cava so a second press
   focuses instead of duplicating):

```lua
o.bind("SUPER + comma", "Ghost settings",
       "omarchy-launch-or-focus-tui --app-id=ghost-settings ghost-settings")
```

   with a float rule in `windows.lua`:

```lua
o.window({ class = "ghost-settings" }, {
  float = true, size = "1040 720", center = true,   -- ≈ 104×34 cells
})
```

3. **Omarchy menu**: a desktop entry the launcher indexes —
   `~/.local/share/applications/ghost-settings.desktop`:

```ini
[Desktop Entry]
Type=Application
Name=Ghost Settings
Comment=Configure shelf, stash and bar widgets
Exec=xdg-terminal-exec --app-id=ghost-settings -e ghost-settings
Icon=preferences-system
Categories=Settings;
```

   (Same `--app-id`, so the float rule applies from all three entry points.)
