# Omarchy customisations — recovery reference

Written 2026-08-25 — keep this file; if `omarchy update` breaks something, start
here instead of re-deriving it all.

**Rule: every new customisation gets logged here.** Anything added — widget,
keybind, service, package — goes into its owning section *and* §9's inventory,
in the same change: an undocumented change can't be undone.

**Baseline when this was built:** Omarchy `4.0.0-1` · Hyprland `0.56.2` ·
quickshell-git `0.3.0.r20` · Lenovo Yoga Slim 7 14ARE05 · Ryzen 5 4500U · Radeon
Vega (Renoir) · 8 GB RAM · eDP-1 1920x1080@60.

---

## 1. Quick triage

| Symptom | Most likely cause | Section |
|---|---|---|
| Bar completely missing | custom QML module threw, or `bar.id` points at a dead plugin | §5, §6 |
| Bar present, floating island gone | `ghost.barisland` plugin failed, or `shell.toml` height override lost | §6 |
| Widgets there but bar not tall | `~/.config/omarchy/shell.toml` missing/ignored | §6 |
| Icons clipped at bar ends | edge spacers dropped from `shell.json` | §6 |
| Everything huge again | `monitors.lua` scale reverted to `"auto"` | §2 |
| Caps Lock types capitals | `input.lua` kb_options lost | §3 |
| Gestures dead | `input.lua` gestures lost, or Hyprland changed gesture API | §3 |

**Verifying a visual change:** screenshot with `grim -g "0,0 1920x50"
/tmp/b.png` and look at it — check the widget in the state you changed, not its
default. A Pomodoro bug appearing only while *running* won't show in an idle
screenshot; an overflowing pill only shows once it has a background to draw.

First commands to run:

```bash
hyprctl configerrors                       # must be empty
journalctl --user --since "2 min ago" | grep -iE "WARN scene|not initialized"
omarchy theme current                      # expect: Monochrome
hyprctl monitors | grep -E "scale|reserved"  # expect scale: 1, reserved: 0 44 0 0
```

---

## 2. Display

`~/.config/hypr/monitors.lua`

- `omarchy_monitor_scale = 1` (was `"auto"`, which resolved to **2** and made
  everything render at an effective 960x540).
- `GDK_SCALE` left at 1.

---

## 3. Input — `~/.config/hypr/input.lua`

**Keyboard.** `kb_options = "caps:escape,compose:ralt,shift:both_capslock_cancel"`

> Omarchy's default is `compose:caps,shift:both_capslock_cancel` — it puts the
> **Compose key on Caps Lock**, so a naive `caps:escape` silently destroys
> Compose. Compose was relocated to **Right Alt** — if you reset this file,
> re-apply all three options together or you'll lose one.

**Touchpad — "Windows feel".** Omarchy's defaults already match Windows on
direction and clicking (`natural_scroll=false`, `tap-to-click`,
`clickfinger_behavior`, `tap-and-drag`); only speed didn't — Omarchy cuts
scrolling to **40%** globally, **20% in Ghostty**. Both restored to `1.0` here,
including the two `o.window(...)` scroll overrides.

**Gestures** (Hyprland 0.56 "gestures v2", `fingers` accepts 2–9):

| Gesture | Action |
|---|---|
| 4 fingers ← → | switch workspace |
| 4 fingers ↑ | `omarchy-menu summon` |
| 4 fingers ↓ | `omarchy-menu close` |
| 3 fingers ← → | move window focus |

> There is **no built-in overview/expo action** in Hyprland 0.56 — the only way
> to get one is the `hyprexpo` plugin via `hyprpm`, deliberately **not**
> installed: Hyprland plugins compile against an exact ABI, break on every
> version bump, and a failed plugin load can stop Hyprland starting.

---

## 4. Look & feel — `~/.config/hypr/looknfeel.lua`

- rounding **10**, `gaps_in` **4**, `gaps_out` **8**, `border_size` **2**
- `dim_inactive` on, `dim_strength` 0.12
- focused window fully opaque, unfocused 0.93 (`opacity = "1.0 0.93"`),
  overriding Omarchy's `"0.985 0.96"`
- **Blur policy:** enabled globally *only* because layer blur requires it; every
  window is excluded via `o.window(".*", { no_blur = true })`, and
  `hl.layer_rule` applies it to shell layers only (bar, **ghost-bar-island**,
  menu, notifications, osd, clipboard, emojis, reminders, polkit,
  keyboard-panel, image-selector, network-qr).

> `omarchy-bar` alone blurs nothing here: the bar surface is transparent
> (`shell.json`), and the visible plate is the `ghost-bar-island` layer. Both
> namespaces stay in the list — blurring the bar is harmless, blurring the
> island is the one that shows.

*Measured:* idle 19% GPU / 9.25 W with blur vs 19% / 9.26 W without (free);
under load 23% vs 21% GPU — the delta is below the battery sensor's noise floor.
Window blur was skipped anyway: it's nearly invisible over a monochrome palette.

- **Animation switch — line 14:** `local animation_feel = "snappy"`; set
  `"fluid"` and save — Hyprland self-reloads. `snappy` = fast/tight (holds 60fps
  under load), `fluid` = slower with overshoot (reference-rice feel). Hyprland
  `speed` is **duration in deciseconds — higher is slower**.

---

## 5. Keybindings — `~/.config/hypr/bindings.lua`

All were verified free before binding, so there are **no `hl.unbind` calls** —
if a future Omarchy claims one of these, add an unbind first.

| Key | Action |
|---|---|
| `SUPER + E` | nautilus |
| `SUPER + N` | Obsidian (also on stock `SUPER+SHIFT+O`) |
| `SUPER + M` | btop |
| `SUPER + ALT + M` | cava |
| `SUPER + ALT + C` | cmatrix |
| `SUPER + ALT + P` | pipes.sh |
| `SUPER + ALT + T` | tty-clock |

Autostart (`autostart.lua`): one terminal on login, kept minimal — 8 GB RAM is
the binding constraint here.

---

## 6. The bar  ← most fragile part, read this first if the bar breaks

### 6a. The floating island — how it actually works

Omarchy's bar **cannot** be detached from the screen edge — `margins` exist only
for hide-parking, and a `PanelWindow`'s own colour can't be rounded.

> ### KNOWN UPSTREAM BUG (Omarchy 4.0.0)
> **`omarchy plugin clone omarchy.bar` produces a bar that doesn't work.** The
> shell host never injects the required properties (`omarchyPath`,
> `barWidgetRegistry`, `barConfig`) into a cloned `kind: bar` plugin, so it
> fails on startup with *"Required property … was not initialized"* and no bar
> renders — verified with a **pristine, unmodified clone**, not caused by
> editing. **Do not try to fork the bar.** Re-test after a major update.

The working approach uses only supported APIs, in three parts — **all three are
required**, and losing any one breaks the look:

1. `~/.config/omarchy/shell.toml` → `[bar] size-horizontal = 44` (makes the bar
   band tall; verify with `hyprctl monitors | grep reserved` → `0 44 0 0`)
2. `shell.json` → `bar.transparent = true`, `bar.id` **must stay `omarchy.bar`**
   (stock bar; never a clone)
3. Plugin `~/.config/omarchy/plugins/ghost.barisland/` paints a rounded plate
   inside that band on `WlrLayer.Bottom`, inset `sideInset` 10px / `inset` 7px.

Bar widgets are vertically centred in the 44px band, landing on the plate;
verified to survive a fullscreen window.

**Tuning knobs** (`ghost.barisland/Island.qml`): `inset`, `sideInset`, tint
alpha. Theme background `#0a0a0b` matches the dark parts of the wallpaper, so a
plate in the raw theme colour is **invisible** — tinted toward the foreground
(currently `0.05`) to read as a raised surface. Border alpha `0.22`.

**Edge spacers.** `shell.json` has `{"id":"omarchy.spacer","size":14}` as the
first entry of `left` and the last of `right` — without them the outermost icons
are clipped by the island's rounded ends.

### 6b. Custom widgets — `~/.config/omarchy/bar/modules/`

Registered in `shell.json` as `{"id":"<name>","type":"qml"}`. All four draw via
`bar.foreground` / `bar.background` / `bar.fontFamily`, following the active
theme automatically.

| Module | Section | Notes |
|---|---|---|
| `sysmon.qml` | right | CPU/GPU/RAM/temp + sparkline. Click = detail pop-out, right-click = btop. Backed by `~/.config/omarchy/bar/scripts/sysmon`. |
| `pomodoro.qml` | center | Focus timer, click for 15/25/45/60/90. Right-click stops. |
| `notes.qml` | right | Scratchpad, saves to `~/.local/state/omarchy/scratchpad.txt` 900ms after typing stops. |
| `mediapill.qml` | left | Now-playing. Idle: animated equaliser glyph + elided label over a progress hairline. Hover: pill fills in, prev/play-pause/next slide out, elapsed readout appears, label marquees. Click: panel with desaturated artwork, drag-scrub timeline with hover time preview, shuffle/repeat, volume, source switcher. Middle = next, right = play/pause, scroll = prev/next. **Scrubbing is panel-only** — the pill's progress hairline is purely visual (see the `modulePointer` gotcha below). Replaces first-party `omarchy.media`. |

**Gotchas learned the hard way — keep these in mind when editing:**

- **Do not name a property `top`** (or `left`/`right`/`bottom`/`baseline`) on an
  `Item` — these are FINAL anchor-line properties; QML throws *"Cannot override
  FINAL property"* and the module silently fails to load, which is why `sysmon`
  uses `topProcs`.
- **`PopupWindow` (xdg-popup) doesn't reliably receive keystrokes** — it only
  gets keys after focus routes through its parent surface, so anything you *type
  into* needs a layer-shell `PanelWindow` with `WlrLayershell.keyboardFocus:
  WlrKeyboardFocus.OnDemand`. That's why `notes.qml` uses `PanelWindow`, the
  other two `PopupWindow` (Omarchy documents this in `Ui/KeyboardPanel.qml`).
- **`bar.shellQuote()` doesn't exist.** Omarchy's bar README (§"Bar properties
  available to widgets") documents it, but `Bar.qml` never implements it —
  calling it throws `TypeError: Property 'shellQuote' ... is not a function` and
  the widget's action silently fails. `pomodoro.qml` and `notes.qml` each define
  a local `sq()` POSIX quoter instead; `bar.run()` is real. Re-check after a
  major update.
- **`clip: true` on a rounded `Rectangle` clips to the BOUNDING BOX, not the
  rounded corners.** A square-cornered child (e.g. a progress fill) pokes out
  past the rounded ends — give it its own matching `radius` instead of relying
  on the clip.
- **Widget pill height must track the ISLAND, not the bar band.** The band is
  44px; `ghost.barisland` insets 7px top and bottom, leaving ~30px of plate.
  Every module derives `pillH` from `bar.barSize - (islandInset*2) - 4`.
  Changing `[bar] size-horizontal` in `shell.toml` **or** `inset` in
  `Island.qml` means re-checking all four: sizing off the raw band overflows the
  plate and hangs outside the bar. Both the plate's `inset`/`sideInset` and the
  modules' `islandInset` are `Style.space(...)`, so they shrink with the base
  font in step with the pills — a raw number there collapses the plate faster
  than its contents.
- **Bar.qml's open-panel mark defaults to 55% of the slot width**, which on a
  wide pill paints a ~130px accent bar where a dot belongs. Every module that
  opens a panel declares `readonly property real openPanelIndicatorWidth:
  Style.space(18)` (or `...Height` on a vertical bar) to override it.
- Click-outside-to-dismiss needs `HyprlandFocusGrab` from `Quickshell.Hyprland`.
- The `sysmon` script resolves the CPU temp sensor by **name** (`k10temp`), not
  by hwmon index — hwmon numbering isn't stable across reboots.
- **Later siblings win both paint order and clicks.** A widget-wide catch-all
  `MouseArea` declared *after* the pill swallows every button inside it —
  declare it first and give the interactive row a `z`. `mediapill.qml` does
  both; the `z` keeps the transport buttons painted and clickable above the
  progress hairline.
- **Bar.qml puts a reorder `MouseArea` (`modulePointer`) on top of EVERY bar
  module.** It is the last child of each `ModuleSlot`, fills the slot, and
  starts a bar-reorder drag past a 4px threshold. Its `propagateComposedEvents`
  only re-delivers *composed* events (`clicked`, `doubleClicked`,
  `pressAndHold`) — `pressed`, `positionChanged` and `released` never reach the
  module. **A press-drag gesture inside a bar widget is therefore impossible**:
  it reorders the widget instead. `mediapill` used to put a 9px scrub strip on
  its bottom edge for this reason and it could never fire; that strip is gone
  and seeking lives on the panel's `PanelSlider`. Anything drag-shaped belongs
  in a popup, not in the pill.
- **A `MouseArea` with `hoverEnabled: false` is transparent to hover but still
  eats clicks** — lets `mediapill`'s buttons sit atop its hover area without
  breaking the hovered state.
- **MPRIS position doesn't tick on its own** — Quickshell refreshes
  `MprisPlayer.position` only when `positionChanged()` fires, so `mediapill`
  pumps it from a 1s `Timer`. Wrap the call in `try`: a player with no Position
  property throws.
- **The media service has no seek or volume logic.**
  `bar.shell.firstPartyServiceFor("omarchy.media")` gives
  `runAction("play"|"pause"|"playPause"|"next"|"previous", showFeedback,
  targetKey)` and `switchSource(delta, transferPlayback, showFeedback)`.
  Everything else — `position`, `length`, `canSeek` — comes off `activePlayer`,
  a raw Quickshell `MprisPlayer`, not a facade.
- **Do not double-animate width.** If inner clips already have `Behavior on
  width`, adding one to the module's `implicitWidth` too makes the pill visibly
  lag the cursor.
- `cliamp` (bundled TUI player, `SUPER + SHIFT + ALT + M`) publishes MPRIS, so
  the pill drives it too, alongside browsers and mpv.
- **Driving hover from a script** (to screenshot a hover state): `hyprctl
  dispatch 'hl.dsp.cursor.move({x=260,y=24})'`. Hyprland 0.56 takes a Lua table
  — the old `hyprctl dispatch movecursor X Y` form is gone, erroring with *"')'
  expected"*.
- **`hasMedia` flickers false for a frame during a source switch.** Latching a
  panel shut on that closes it under the cursor mid-switch. `mediapill` hides
  the popup while there is nothing to show and only *closes* it after a 3s
  grace timer.
- **`clamp01(undefined)` is `NaN`, and a `NaN` width renders as zero, not as a
  visible break.** The volume fill silently read empty until the guard became
  `isFinite(player.volume)`. Prefer `isFinite` over `!== undefined` for any
  MPRIS number.
- **`clip: true` cannot round a corner, but `MultiEffect` can.** For a rounded
  image or backdrop, set `maskEnabled: true` and point `maskSource` at a hidden
  `Rectangle` with `layer.enabled: true` and the matching radius. Both the
  panel's ambient backdrop and its cover thumbnail do this.
- **A hand-placed popup lands offscreen when the bar is not on the top edge.**
  `sysmon`, `pomodoro` and `mediapill` all use `PopupCard`, which anchors itself
  for all four bar positions. `notes.qml` is the one exception — it must keep a
  layer-shell `PanelWindow` to receive keystrokes — so it copies `PopupCard`'s
  `onAnchoring` four-edge logic by hand into its card's `x`/`y`. Note that
  `mapToItem()` is a *function call*: a QML binding wrapped around it captures
  no dependencies and freezes at the first (pre-layout) answer, so `notes` keeps
  the mapped origin in a plain property refreshed by a `relocate()` function.
- **Hyprland 0.56 has no click dispatcher** — only `hl.dsp.cursor.move`. To
  screenshot a click-opened panel, temporarily default its `open` property to
  `true` *and* disable the `HyprlandFocusGrab` (an active grab clears the state
  immediately), then revert.
- `mpv-mpris` publishes embedded cover art as a `data:image/...;base64` URI,
  which `Image.source` accepts directly. `cliamp` publishes no art, and
  declares a short `mpris:length` for long mixes, so its progress bar often
  pins full. Both are upstream metadata quirks, not widget bugs.
- A *"File name case mismatch"* warning for these modules is **benign**.
- `xkbcomp: Key <LFSH> added to map for multiple modifiers` is **benign** and
  pre-existing — it comes from Omarchy's own `shift:both_capslock_cancel`.

**Known limitation:** the Pomodoro session tally is in memory and resets when
the shell restarts.

### 6d. Popup design system — THE RULE

**Every popup, panel and card written for this machine must be built from
Omarchy's own UI components, not hand-rolled to look similar.** Hand-rolled
chrome drifts the moment a theme, font size or Hyprland rounding value changes.

A user QML file **can** `import qs.Ui` and `import qs.Commons`, even though it
lives outside `/usr/share/omarchy/shell`. The shell runs as one Quickshell
process (`quickshell -n -p /usr/share/omarchy/shell`), that path becomes the
`qs` module namespace, and every plugin and user module is loaded into that
*same engine* via `Qt.createComponent`. `qs.*` is a named module import
resolved against the engine, not against the importing file's directory — so it
resolves from anywhere. Verified empirically, not just assumed: a probe module
in `~/.config/omarchy/bar/modules/` printed real values
(`caption=10 body=12 displayLarge=28 popupPadding=14 popupsBg=#101315`).

> Those numbers are **theme- and font-dependent, not constants.** The colour in
> particular was probed under a different theme: `Color.popups.background`
> falls back to the theme `background`, which on Monochrome is `#0a0a0b`. Never
> hardcode a probed value — read the token.

Use these instead of rolling your own:

| Need | Use | Not |
|---|---|---|
| Popup container | `PopupCard` | a `PopupWindow` + `Rectangle` |
| Persistent overlay card | `BorderSurface` + `Color.popups.*` | a plain `Rectangle` |
| Section label | `PanelSectionHeader` | a bold `Text` |
| Divider | `PanelSeparator` | a 1px `Rectangle` |
| Slider / scrubber | `PanelSlider` | a track + knob by hand |
| Button, toggle pill | `Ui/Button` (`active`, `bordered`) | a `Rectangle` + `MouseArea` |
| Any size or gap | `Style.space()`, `Style.spacing.*` | a raw pixel number |
| Any font size | `Style.font.*` | a raw pixel number |
| Any colour | `Color.*`, `bar.foreground` | a hex literal |

`PopupCard` alone brings `Color.popups.background`, the themed border spec,
`Style.cornerRadius` (mirrors Hyprland `decoration:rounding`, currently **10**),
the shared 140ms fade, `HyprlandFocusGrab` outside-click dismissal, bar-position
-aware anchoring for all four bar edges, and the one-popup-at-a-time coordinator.

Design tokens worth knowing (base font size 12; `Style.space()` is a **scale
multiplier**, not identity):

```
font   caption 10 · bodySmall 11 · body 12 · subtitle 13 · title 14
       heading 16 · display 24 · displayLarge 28 · iconSmall 11 · icon 14 · iconLarge 18
space  labelGap 4 · md 6 · lg 8 · controlPaddingX 10 · controlPaddingY 6
       panelGap 14 · popupPadding 14 · panelPadding 18 · controlHeight 28
dim    Qt.darker(fg, 1.4) = section headers/status · opacity 0.6 = labels
       Util.alpha(fg, a) = translucency (darker ≠ alpha; both are used)
```

The battery popup's hero is the reference for a panel header: icon, stacked
labels, and an **uppercase letterspaced caption** status line —
`font.pixelSize: Style.font.caption; font.bold: true; font.letterSpacing: 1.2;
color: Qt.darker(foreground, 1.4)`. `mediapill.qml`'s panel copies exactly this.

**Gotcha:** `Ui/Button` centres a plain `Text` with **no eliding**. A long label
runs under the card border and is clipped. Truncate the string in JS before
handing it to `text:` (see `mediapill.qml`'s `sourceLabel()`).

### 6e. Screenshot shelf — `~/.local/share/ghost-shotshelf/`

Replaces Omarchy's five-second screenshot toast with a shelf that persists
until dismissed, collapses to a chip, fans out multiple shots, and — the whole
reason it exists — lets you **drag the image out into another application**.

**It is a GTK4/PyGObject app, not a Quickshell plugin, and that is forced.**
An earlier Quickshell version of this lives in git history; it could never
drag. Two independent blockers:

1. QtQuick's `Drag` is scene-local. `DragType` is `None`/`Automatic`/`Internal`
   — no `External` — and Quickshell registers no DnD types at all. Real
   cross-app drag needs C++ `QDrag::exec()`.
2. The drag must not originate from a **layer-shell** surface. wlroots
   validates a drag against the seat's last pointer-button serial *and*
   requires the origin surface to hold pointer focus; layer surfaces typically
   hold neither. KWin has a filed crash for exactly this pattern (bug 502497),
   and every app that drags files out on Wayland — Flameshot, Nautilus — uses
   an ordinary `xdg_toplevel`.

So the shelf is a normal toplevel made to behave like an overlay, via
`~/.config/hypr/windows.lua` (same pattern as Omarchy's `webcam-overlay.lua`):
`float`, `pin`, `no_initial_focus`, `no_follow_mouse`, `border_size = 0`,
`rounding = 0`, fixed `size`/`move`. **Verified: focus stays on the terminal
underneath** when a screenshot arrives.

| Piece | Path |
|---|---|
| App | `~/.local/share/ghost-shotshelf/shotshelf.py` |
| Launcher | `~/.local/bin/ghost-shotshelf` (autostarted) |
| Capture wrapper | `~/.local/bin/ghost-capture` |
| Toast shim | `~/.local/share/ghost-shotshelf/shim/omarchy-notification-send` |
| Window rules | `~/.config/hypr/windows.lua` |

**THE detail that makes the drag work.** `Gdk.ContentProvider.new_for_value(Gio.File(...))`
is what every tutorial shows and it is **wrong**: the GValue carries the
concrete type `GLocalFile`, GDK registers its serialisers against the `GFile`
*interface*, nothing matches, and the drag advertises **zero** mime types — it
looks perfect and silently fails on every drop. Measured here:

```
new_for_value(GFile)       -> ON THE WIRE: []
new_for_value(GdkFileList) -> ['text/uri-list', 'text/plain;charset=utf-8',
                               'application/vnd.portal.filetransfer', ...]
```

Use `Gdk.FileList`. Verify any change with
`provider.ref_formats().union_serialize_mime_types().get_mime_types()`.

**Replacing the toast.** `ghost-capture` runs Omarchy's own
`omarchy-capture-screenshot` with a directory prepended to `PATH` containing a
no-op `omarchy-notification-send`. Scoped to that process tree only, so every
other Omarchy notification is untouched. `PRINT` is rebound to it in
`bindings.lua` — and **`hl.unbind("PRINT")` first**, because Hyprland keeps
both binds otherwise and fires two captures. A/B verified: stock shows the
toast, wrapped shows nothing.

Detection is a `Gio.FileMonitor` on the screenshot directory keyed on
`CHANGES_DONE_HINT` (not `CREATED`, which fires while grim is still writing),
so captures started any other way — the Omarchy menu — still reach the shelf;
they just also show the stock toast.

**Gotchas:**

- **`Gtk.Picture`'s natural size is the image's real size**, and natural beats
  `set_size_request`, which is only a *minimum*. A 1920px screenshot inflates
  the whole card to fill the window. Load a pre-scaled texture at exactly the
  display size (`GdkPixbuf.new_from_file_at_scale`) — which also avoids holding
  full-resolution textures for 58px thumbnails on an 8 GB machine.
- **A hidden widget cannot transition.** The expand/collapse is a CSS
  `transition` on `opacity` and `transform` with the two surfaces stacked in a
  `Gtk.Overlay`; both stay mapped and the inactive one gets
  `set_can_target(False)` so it never eats a click.
- The window is a fixed 1000x300 transparent canvas; the app sets a Wayland
  **input region** around the visible card so the empty area stays
  click-through. Keeping the window size constant means Hyprland never has to
  reposition it as the card grows and shrinks.
- Fonts and colours are read at runtime from `omarchy-font-current` and the
  *current* theme's `colors.toml` — which lives under `~/.local/state`, **not**
  `~/.config`. The original code read the `~/.config` path, which does not
  exist; `read_theme()` swallowed the `OSError` and fell back to a hardcoded
  palette that happened to match, so the shelf looked right while following
  nothing. It also built its `Gtk.CssProvider` once at startup. Both fixed: the
  app now watches `~/.local/state/omarchy/current/theme/colors.toml` **and its
  parent directory** and rebuilds the provider on change. The parent matters —
  `omarchy-theme-set` does `rm -rf current/theme && mv next current/theme`, which
  destroys the directory any monitor on the inner file was watching.

**Supervision.** The shelf is started by `systemd --user` (`ghost-shotshelf.service`,
`Restart=on-failure`), **not** by `o.launch_on_start`. It died once mid-session
with no coredump, no journal entry and nothing to restart it — the first symptom
was pressing PRINT and getting nothing. systemd also gives
`journalctl --user -u ghost-shotshelf`, which is the answer to "how would I even
find out". `autostart.lua` now just does `systemctl --user start`.

**What cannot be scripted:** there is no way to synthesise a pointer button on
this setup, so the drag gesture itself must be tested by hand. `wtype` exits 0
and delivers nothing; Hyprland 0.56 exposes `hl.dsp.send_key_state`
(`{mods, key, state}`) and `hl.dsp.send_shortcut`, but both are keyboard-only —
`BTN_LEFT`/`mouse:272` return `ok` and produce no click, confirmed against a
GTK button that logs its clicks. `hl.dsp.cursor` has only `move` and
`move_to_corner`. Enumerate dispatchers with:

```bash
hyprctl eval 'local f=io.open("/tmp/d","w") local t={} for k in pairs(hl.dsp) do t[#t+1]=tostring(k) end table.sort(t) f:write(table.concat(t,"\n")) f:close() return "x"'
```

### 6c. Bar layout

```
left    spacer · menu · workspaces · mediapill
center  indicators · clock · pomodoro · keyboard-layout · weather · system-update
right   sysmon · notes · [tray] · agents · network · audio · bluetooth · monitor · power · spacer
```

> `omarchy.tray`'s position is **not** whatever `shell.json` says.
> `Bar.qml:341-343` runs every section through `pinTrayToInner()`, which moves
> the tray to the section's *inner* edge — the FRONT of the right section, the
> END of left/center — so the drawer reveals away from the screen edge. Moving
> the `omarchy.tray` entry in `shell.json` has no visible effect.

Idle: `screensaver` 600s, `lock` 1800s.

---

## 7. Theme — `~/.config/omarchy/themes/monochrome/`

Forked from stock **Vantablack**. Total greyscale, no colour in any ANSI slot.

- background `#0a0a0b` (near-black, not pure `#000` — keeps IPS-panel depth,
  stops UI layers collapsing together)
- foreground `#dfe3e6` (cool ash, not pure white — easier to read)
- `hyprland_active_border` = greyscale gradient
- One background: `backgrounds/0-dot-hands.jpg`
- Font unchanged: JetBrainsMono Nerd Font

Stock themes are untouched; `omarchy theme set "Matte Black"` restores the old look.

---

## 8. Power

- Profile `balanced`, **persisted** to `~/.local/state/omarchy/powerprofiles/ac`.

  > This file is the actual fix: `omarchy-powerprofiles-init` runs at every
  > Hyprland start and calls `omarchy-powerprofiles-set autodetect`, which
  > defaults to **`performance`** on AC when no state file exists — running
  > `powerprofilesctl set balanced` alone gets silently undone at next login.

- `amdgpu_panel_power` action **enabled** in power-profiles-daemon. Its own
  description says *"may affect color quality"* — it's ABM, and engages **on
  battery only**; if greys look crushed on battery, this is why:
  `powerprofilesctl configure-action --disable amdgpu_panel_power`
- Battery warning left stock at 10% (`omarchy.battery` service, unforked).
- Limine boot timeout reduced 5s → 2s (`/boot/limine.conf`, backup
  `/boot/limine.conf.bak.pretune`).
- Pacman cache: `paccache -rk2` freed nothing — 130 files for 128 unique
  packages (essentially one each) left nothing to prune. The 1.6 GB is
  current-version packages; reclaiming it costs offline reinstall/downgrade.
- `cups`, `cups-browsed`, `avahi-daemon` disabled (printing stack, unused).
  Re-enable: `sudo systemctl enable --now cups.service cups.socket
  avahi-daemon.service`
- Swap left as-is: zram 7.1G (prio 100) **and** a 7.1G `/swap/swapfile` (prio 0)
  — the disk swapfile is largely redundant behind zram if you want the space
  back.

---

## 9. Full inventory of changed/created files

```
~/.config/hypr/monitors.lua          scale 1
~/.config/hypr/looknfeel.lua         geometry, blur policy, 2 animation sets
~/.config/hypr/input.lua             kb_options, touchpad speed, gestures
~/.config/hypr/hyprland.lua          + require("hypr.windows")
~/.config/hypr/bindings.lua          8 keybinds
~/.config/hypr/autostart.lua         terminal on login
~/.config/omarchy/shell.json         bar layout, transparent, idle, plugins[]
~/.config/omarchy/shell.toml         [bar] size-horizontal = 44      (NEW)
~/.config/omarchy/themes/monochrome/                                  (NEW)
~/.config/omarchy/bar/modules/{sysmon,pomodoro,notes}.qml             (NEW)
~/.config/omarchy/bar/modules/mediapill.qml   replaces omarchy.media  (NEW)
~/.local/share/ghost-shotshelf/       GTK4 screenshot shelf app       (NEW)
~/.local/bin/{ghost-shotshelf,ghost-capture}                          (NEW)
~/.config/hypr/windows.lua           shelf window rules              (NEW)
~/.config/hypr/bindings.lua          PRINT rebound to ghost-capture
~/.config/hypr/autostart.lua         starts ghost-shotshelf.service
~/.config/systemd/user/ghost-shotshelf.service                        (NEW)
~/.config/omarchy/bar/scripts/sysmon                                  (NEW)
~/.config/omarchy/plugins/ghost.barisland/                            (NEW)
~/.local/state/omarchy/powerprofiles/ac                               (NEW)
/boot/limine.conf                    timeout 5 -> 2
```

Nothing under `/usr/share/omarchy/` was modified, no Hyprland plugin installed,
and no shell plugin forked (the bar clone was reverted and deleted).

---

## 10. Undo everything

```bash
# Hyprland configs (timestamped backups from the original session)
cd ~/.config/hypr
for f in looknfeel input bindings autostart hyprland; do cp $f.lua.bak.1787616894 $f.lua; done
cp monitors.lua.bak.1787613434 monitors.lua
hyprctl reload

# Shell / bar
cp ~/.config/omarchy/shell.json.bak.1787616894 ~/.config/omarchy/shell.json
rm -f ~/.config/omarchy/shell.toml
rm -rf ~/.config/omarchy/plugins/ghost.barisland ~/.config/omarchy/bar
systemctl --user disable --now ghost-shotshelf.service
rm -f ~/.config/systemd/user/ghost-shotshelf.service
rm -rf ~/.local/share/ghost-shotshelf ~/.local/bin/ghost-shotshelf ~/.local/bin/ghost-capture
rm -f ~/.config/hypr/windows.lua   # and drop require("hypr.windows") from hyprland.lua
omarchy restart shell

# Theme
omarchy theme set "Matte Black"
rm -rf ~/.config/omarchy/themes/monochrome

# Power
rm -f ~/.local/state/omarchy/powerprofiles/ac
powerprofilesctl configure-action --disable amdgpu_panel_power
sudo cp /boot/limine.conf.bak.pretune /boot/limine.conf
sudo systemctl enable --now cups.service cups.socket avahi-daemon.service

# Nuclear
omarchy refresh hyprland && omarchy refresh shell
```
