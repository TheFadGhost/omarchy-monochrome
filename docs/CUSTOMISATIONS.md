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

All were verified free before binding (`hyprctl binds -j`). The `hl.unbind`
calls that DO exist: `PRINT` (Omarchy binds it too; both would fire), and a
conditional `SUPER + CTRL + V` (only when the `disable-omarchy-clipboard`
flag file exists — see below).

| Key | Action |
|---|---|
| `SUPER + E` | nautilus |
| `SUPER + N` | Obsidian (also on stock `SUPER+SHIFT+O`) |
| `SUPER + M` | btop |
| `SUPER + ALT + M` | cava |
| `SUPER + ALT + C` | cmatrix |
| `SUPER + ALT + P` | pipes.sh |
| `SUPER + ALT + T` | tty-clock |
| `SUPER + SHIFT + V` | Sill panel toggle (skipped if `sill.keybind_toggle=false`) |
| `SUPER + SHIFT + Delete` | `sill purge` — wipe clipboard history |

**Flag files** (`~/.config/ghost/flags/`): a Hyprland bind cannot read
`settings.toml`, so Sill mirrors bind-affecting booleans as flag files
(existence = non-default) and runs `hyprctl reload` when they change;
`bindings.lua` checks them with `io.open` at config parse (verified: `io` IS
available in the Lua sandbox). `disable-omarchy-clipboard` unbinds
`SUPER+CTRL+V` **only** — the Quickshell clipboard plugin must stay loaded,
it owns the `wl-paste` capture watchers Sill's Clipboard tab depends on.
`sill-no-toggle-bind` suppresses the `SUPER+SHIFT+V` bind.

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
| `drawer.qml` | right | Icon drawer: collapses the wifi / sound / bluetooth / display bar icons into one chevron pill that fans the four icons out on hover and re-collapses on leave (eased 220ms width clips, mediapill idiom). Does **not** reimplement the panels: the four first-party widgets (`omarchy.network`, `omarchy.audio`, `omarchy.bluetooth`, `omarchy.monitor`) STAY in `shell.json` — the drawer finds their live instances via `bar.moduleSlots` and collapses their bar buttons to invisible 1px slivers with restorable `Binding`s (implicitWidth/Height 1, opacity 0, enabled false); its own cells mirror their live state (`item.icon`, `outputIcon()`, `outputMuted`, `connectedDevices`) and a click calls the live widget's `toggle()`, opening the REAL first-party panel, which anchors correctly because the 1px slot keeps its layout position beside the drawer. Non-default states stay fanned out while collapsed: muted output, disconnected network, bluetooth connected or radio off, and any cell whose panel is open. Right-click mirrors the stock icons (audio mute toggle, bluetooth radio toggle); scroll = volume on the audio cell, brightness on the display cell. Config per shell.json entry settings: `components` (widget id list) and `hover` (false = expand only on chevron click); a `ghost-settings` hook (`externalConfig`) is stubbed but unwired — the CLI did not exist at build time. If the module dies, the Bindings die with it and the stock icons return. |

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

- **Row/Column positioners skip zero-size items.** Hiding a first-party widget
  with `visible: false` collapses its ModuleSlot to 0x0 (`implicitWidth` is
  gated on `activeItem.visible`), and the positioner then never places the
  slot — it strands at the section origin (measured x=1395 via `omarchy-shell
  shell debugBarGeometry`), and the widget's panel, which anchors to its bar
  button, opens centered there instead of under the drawer. `drawer.qml`
  therefore collapses the buttons to a **1px transparent disabled sliver**
  (Bindings: implicitWidth/Height 1, opacity 0, enabled false), which keeps the
  slot positioned beside the drawer so summoned panels drop in the right place.
  Item `opacity`/`enabled` do not propagate into the panels — they are
  separate popup surfaces, not visual children.
- **`Instantiator` resolved every delegate's context `modelData` to the FIRST
  model entry** when fed a JS array of QObjects — only one of the drawer's four
  hide-Bindings took effect, silently. A `Repeater` with
  `required property var modelData` injects per-delegate correctly; the
  wrapper Items are zero-size, invisible hosts for the Bindings.
- **Summoning first-party panels — what exists (reusable knowledge):**
  `shell.summon(id)` / `toggle(id)` (also via IPC: `omarchy-shell shell
  toggle omarchy.bluetooth`) routes bar-widget panels through
  `bar.summonBarWidget(id)`, which needs a **live slot in the bar layout**
  whose activeItem has `open()`/`close()`/`opened` — remove the widget from
  `shell.json` and summoning fails with "no live bar widget". Each panel also
  answers its own IPC target directly: `omarchy-shell omarchy.bluetooth
  toggle` (plus `toggleBluetooth` on that one). In-process, a custom module
  can simply call the live item's `toggle()` — that is what `drawer.qml`
  does. This is why the drawer keeps the four widgets registered instead of
  replacing their entries.
- **`Binding { restoreMode: Binding.RestoreBindingOrValue }` on another
  widget's property is a safe, reversible override** — the target's own
  binding (e.g. bluetooth's `visible: adapter !== null`) comes back when the
  Binding is destroyed, so a failed/removed drawer degrades to stock icons.
- **A cell that must stay visible while its panel is open needs its own open
  mark**: Bar.qml's accent `openPanelIndicator` draws on the (now 1px) hidden
  slot, so `drawer.qml` paints its own dot under the open cell.

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

### 6e. Sill — clipboard + screenshot + stash panel — `~/.local/share/sill/`

**Supersedes `ghost-shotshelf`, which is retired and deleted.** Sill is the same
GTK4 toplevel approach (the reasoning below still applies verbatim) with tabs,
a Pinned stash, a drop target, and a TOML config at `~/.config/ghost/settings.toml`
that live-reloads. Supervised by `sill.service` (`Restart=on-failure`).
`ghost-capture` now shadows `omarchy-notification-send` from
`~/.local/share/sill/shim/`. Health check: `sill doctor --self-test`, which
re-verifies the drag providers actually put mime types on the wire.

Migration done-condition met: no `shotshelf` references remain outside
historical comments. Everything below describes the design Sill inherited.

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

**The three drag-out providers, measured on this machine.** Each content type
needs a different provider, and two of the three have a silent-failure mode
where the drag advertises ZERO mime types and every drop does nothing:

```
new_for_value("hello")                 -> ['text/plain;charset=utf-8','text/plain']  OK
new_for_value(texture)                 -> []                          <-- TRAP
new_for_value(GObject.Value(Gdk.Texture, tex)) -> 16 image mimes       OK
new_for_value(Gdk.FileList([gfile]))   -> uri-list + portal filetransfer  OK
union(file + Value(Texture) + str)     -> 21 mimes   <-- "target chooses"
```

Same root cause both times: PyGObject types the GValue with the *concrete*
class (`GLocalFile`, `GdkMemoryTexture`) while GDK registers its serialisers
against the *abstract* type (`GFile`, `GdkTexture`), so nothing matches. Plain
strings work naively because `gchararray` is already final. Always verify with
`provider.ref_formats().union_serialize_mime_types().get_mime_types()`.

**Receiving is the mirror image and reads as broken when it is fine.** A
correctly configured `Gtk.DropTarget` reports an EMPTY
`get_formats().get_mime_types()`; check `get_gtypes()` instead. Construct it as
`Gtk.DropTarget.new(GObject.TYPE_NONE, Gdk.DragAction.COPY)` — PyGObject
rejects the documented `G_TYPE_INVALID` idiom with `ValueError`.

**Staying awake.** `omarchy-toggle-idle stay-awake` touches
`~/.local/state/omarchy/indicators/stay-awake`; the shell watches that file and
logs `idle-cycle-cancel: stay-awake`. Note the CLI prints the state of *idle*,
so `disabled` means stay-awake is ON, and `--status` reports
`{"enabled":true}` with a tooltip describing what a click would do NEXT, not
the current state. Both readings invert easily.

**Placing an overlay window: a size rule on a non-resizable client is refused,
and Hyprland drops the paired `move` with it.** Sill's window is
`set_resizable(False)`, so a windowrule asking for a different size is ignored —
and the window then lands *centred*, because the `move` in the same rule is
discarded too. The symptom is a rule that silently stops applying with no config
error. Keep the rule's size identical to the client's own, or don't set size.

Also: `hyprctl reload` does not re-place already-mapped windows — rules apply at
map time. Sill regenerates `~/.config/hypr/sill-position.lua` (atomic
`os.replace`), calls `hyprctl reload`, then bounces its own surface visibility to
force a re-map. And the position cannot be applied by dispatcher instead:
`hl.dsp.window.move` acts on the FOCUSED window and ignores a window selector,
while Sill deliberately never takes focus.

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

**Nor can a modifier chord be synthesised.** `wtype -M logo -M shift -k v`
does NOT trigger the compositor bind — virtual-keyboard modifiers don't merge
with the injected key at the seat (the same reason Omarchy's own
`clipboard.lua` uses `hl.dsp.send_key_state` instead of wtype for its
universal shortcuts, and that dispatcher sends to the focused *surface*, not
to the compositor's bind table). The bare key leaks into whatever window has
focus instead. Keybind-fires-action must be verified by a human; verify the
bind is *registered* with `hyprctl binds -j`.

#### Phase 2 — the Clipboard tab (2026-08-25)

Sill's Clipboard tab is a **read-only renderer of Omarchy's clipboard store**
(`~/.local/state/omarchy/clipboard-history.json` + content-hashed images in
`clipboard-images/`). Sill never runs its own `wl-paste --watch`: the
Quickshell clipboard plugin owns both watchers and resurrects them; a second
reader races for the same selection and doubles the secret-snapshot surface.

Facts about that store that will bite anyone touching this code:

- **`capturedAt` is a DISPLAY STRING** ("Tuesday 03:45"), not a timestamp,
  and text entries carry no time at all. Real times: image file mtimes +
  `~/.local/share/sill/seen.json` (content-key hash → first-seen epoch,
  pruned with the store). Without this, TTL maths would be fiction.
- It is **private, undocumented state with no stability contract**, so
  `store_clipboard.py` ports `ClipboardHistory.js::normalizeEntry` tolerantly
  and runs a schema guard: file missing / unreadable (retry once at 250 ms
  for torn mid-write reads, then keep the in-memory last-good) / parses-but-
  recognises-nothing ("drift") each show a one-line banner in the tab. A
  silently empty panel is the failure mode this exists to avoid. The
  last-good snapshot is never persisted — that would duplicate secrets past
  a purge. `sill doctor` prints state + raw/recognised counts.
- Omarchy's own UI reorders on copy: clicking a Sill row copies, the watcher
  re-captures it, and `addEntry` dedupes it to the top. Normal, not a bug.

Row rendering is type-aware but strictly offline: a hex colour becomes a
swatch (the one sanctioned colour exception — the colour IS the content), a
single-line URL renders domain-bold/path-dim, images render pre-scaled
thumbnails. **Nothing is ever fetched from the network.** Click = copy +
close; drag out = the union provider (target chooses among ~21 mimes); `+`
pins the content into Sill's own store (pins survive eviction, TTL and
purges by copying content into `blobs/`).

Privacy (the honest version — limits documented, not hidden):

- **Reactive denylist** (`[sill.privacy] denylist`): each entry is a
  case-insensitive regex full-matched against the focused window class when
  a NEW entry lands (~300 ms after capture). Match → the entry is deleted
  from the store and never rendered, logged to the journal. Limits: if focus
  moved within that window the check misses; the secret existed on disk
  briefly and in the Wayland selection regardless; a re-copy of content
  already in the store (dedupe) is not re-checked. True exclusion needs the
  capture side, which is pacman-owned and not forked. Default denylist:
  password managers + terminals (Alacritty/kitty/foot/ghostty/wezterm/
  org.omarchy.terminal/TUI.*). **`org.omarchy.agent` (Claude windows) is
  deliberately NOT denied** — agent output is the main thing copied on this
  machine; add it to the list if that changes. Apps setting
  `CLIPBOARD_STATE=sensitive` / `x-kde-passwordManagerHint` are already
  excluded upstream by `capture.sh` and never reach the store.
- **`sill purge`** (also `SUPER+SHIFT+Delete`): atomically writes `[]`,
  empties `clipboard-images/`, clears the sidecar. GTK-free and
  instance-free, so it works from a keybind or a dead session; a running
  Sill notices via its file monitor. Pins untouched by design.
- **`purge_on_lock`** (default off): logind session `Lock` signal /
  `LockedHint` property via the system bus. `GetSessionByPID` fails for a
  user-manager service (NoSessionForPID), so the proxy falls back to the
  seated session of our uid via `ListSessions`. Off by default because the
  screensaver locks at 10 min idle and purging every lock would gut the
  feature.
- **Perms re-asserted every reload**: store 600, images dir 700 (Omarchy
  recreates at 644).
- **TTL + orphan prune** (startup + daily): entries older than
  `sill.max_age_days` dropped from the store; image files referenced by no
  entry AND older than max(24 h grace, TTL — 7-day fallback when TTL=0,
  since an orphan is unreachable by any consumer) deleted. Omarchy never
  prunes `clipboard-images/` itself — orphans otherwise accumulate forever.
  All store writes are read-modify-`os.replace`; the ms-scale race with the
  Quickshell writer can lose at most one concurrent capture — accepted and
  documented in exchange for not forking the pacman-owned pipeline.

`sill.max_items` / `sill.max_age_days` also act as a display filter, applied
live. Tests: `python3 ~/.local/share/sill/test_store_clipboard.py` (41
asserts over the normaliser, schema guard, prune, purge, denylist matcher;
uses env-seam temp dirs, never the real store).

**THE PyGObject LEAK (found at a 1.4 GB memory peak, 8 GB machine).** A row
widget re-rendered on every clipboard event leaked ~1.7 MB *per render* and
`gc.collect()` reclaimed nothing. Cause: an event-controller closure that
references the widget it is attached to (the drag-begin handler captured
`widget` for `Gtk.WidgetPaintable.new(widget)`). The cycle is
widget →(C ref)→ controller →(closure)→ widget-wrapper →(toggle ref)→ widget;
Python's GC cannot traverse the C edges, so removed rows lived forever. Two
rules, now applied in all three tabs:
1. a controller closure must never capture its own widget — use
   `controller.get_widget()` inside the handler instead;
2. when clearing a list, call `child.run_dispose()` after `remove(child)` —
   it drops the controllers and breaks any remaining cycle deterministically
   (that is what `run_dispose` is for in language bindings).
Verified: 30 forced store reloads, RSS flat (was +70 MB), object-count delta
zero. Watch `systemctl --user status sill` — the "Memory:" line creeping is
the symptom.


#### Phase 5 — hover-to-expand (2026-08-25)

`sill.expand_on_hover`: the panel expands when the pointer **rests** on the
bar's empty space beside the chip, `sill.hover_delay_ms` (default 300 ms)
later. It is an *auto* expansion: `sill.collapse_s` folds it back, moving
into the panel holds it open (existing GTK enter/leave), and it never fires
while a Sill drag is in flight.

Detection is the **`ghost.barhover`** service plugin (the sill-plan and the
settings schema doc-string call it `ghost.sillhover` — same thing, renamed)
plus a watched state file. Dead ends first, so nobody re-derives them:

- **An overlay surface with `MouseArea { acceptedButtons: Qt.NoButton }`
  swallows clicks.** Wayland input regions are per-SURFACE; `Qt.NoButton`
  only re-routes clicks within one scene. And `Bar.qml`'s
  `CenterGestureArea` — a MouseArea filling the ENTIRE bar background —
  owns left-press-drag = move-bar-to-another-edge and double-click =
  transparency toggle on exactly the empty space such a strip would cover.
  The plan's R8 check ("bar icons still take clicks") would have *passed*
  while both background gestures silently died inside the strip.
- Enlarging Sill's own input region: dead — the layer-`top` bar stacks
  above every xdg_toplevel and gets the pointer first.
- Hyprland socket2: carries no pointer-motion event (sampled live).
- Polling `hyprctl cursorpos`: ~7 ms per fork vs 0.04 ms on the raw
  socket (~170x); kept out entirely, not even as a fallback.

What ships takes **no input at all**. The shell host injects `shell` into
service plugins; `shell.bar.barHovered` is the bar's own HoverHandler
state — an event, not a poll. Only while it is true (and the bar's own
reorder/move drags are not in flight — `barDragSource`/`barMoveActive`)
the plugin samples `/cursorpos` on Hyprland's request socket every 100 ms
and classifies the point against the bar's *live layout*: ModuleList /
ModuleSlot items carry `region` ("left"/"center"/"right"), so the real
gaps between sections are computed per screen, tracking layout changes
automatically. Zero wakeups while the pointer is anywhere but the bar;
zero clicks touched, ever; bar gestures untouched by construction.

Zone transitions land in `$XDG_RUNTIME_DIR/ghost/sill-hover.state` (tmpfs,
atomic writes) as one JSON line `{"zone":"right-gap|left-gap|none",
"bar":<bar edge>,"monitor":...}`; Sill watches it with `Gio.FileMonitor`
(WATCH_MOVES, to see the renames) and applies all policy on its side:
`expand_on_hover`, `hover_delay_ms`, position adjacency, the drag guard.
**File-watch, not a unix socket, on purpose**: the file is *state*, not an
event stream — either side can restart in any order and the truth is still
on disk; inotify delivery (~1 ms) is noise against a >=100 ms hover delay.

**Where it applies.** `sill.position`'s row must match the bar's edge:
`top-right` arms the right gap (between the center and right sections),
`top-left` the left gap, `top` either flank; `bottom-*` mirror on a
bottom bar. Middle-row positions (`left`/`center`/`right`) never
hover-expand — the chip is not on the bar, and no behaviour was invented
for them. Vertical bars: not supported. Only bar-at-top with `top-*` is
exercised on this machine.

Sill-side drag bookkeeping: tabs now call `app.drag_began()` /
`app.drag_ended()` around GTK drags (instead of raw
`cancel_collapse`/`schedule_collapse`) so a hover-expand can never re-cut
the window's input region mid-drag.

Verified end-to-end with `hl.dsp.cursor.move` sweeps (the §6b technique;
no input synthesis): gaps classify at their true pixel ranges, right-gap
rest expands after the delay, `collapse_s` folds it back, left-gap does
NOT expand a top-right chip. **Fragility:** the plugin reads the bar scene
read-only (`Variants.instances`, items with `region`); an omarchy update
renaming those internals makes every lookup fail *soft* — hover-expand
silently stops while click/keybind expansion keep working. After a major
update, hover the gap left of `sysmon` and watch the state file.

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

## 8a. Luna — assistant daemon (Phase 0)

A resident personal assistant. Code in `~/Work/luna`, state in
`~/.local/share/luna`, design in `~/Work/luna/docs/ARCHITECTURE.md`.
Phase 0 is text only: no voice, no workspace dispatch, no bar widget.

- `lunad` runs as a systemd **user** unit, `PartOf=graphical-session.target`,
  set up the same way as `voxtype.service`. ~12 MB resident.
- IPC is one Unix socket, `$XDG_RUNTIME_DIR/luna/luna.sock`, mode 0600,
  newline-delimited JSON. Client is `~/Work/luna/bin/luna`.
- Python 3 stdlib only, no dependencies, no packages installed.

Gotchas found building it:

- **`claude -p` inherits `~/.claude/CLAUDE.md`.** Without `--safe-mode` every
  Luna turn loads the global memory file — ~22k extra cached tokens and, worse,
  a competing set of standing instructions fighting the persona spec. Symptom:
  Luna answering like a coding agent and talking about subagents. `--safe-mode`
  also drops skills, plugins, hooks and MCP, which is what we want here.
- **Do not invoke `~/.local/bin/claude`** from a daemon: that shim runs
  `mise use -g claude`, mutating the global mise config on every call. Call
  `~/.local/share/mise/installs/claude/latest/claude` directly.
- **`logging` refuses `extra={"message": ...}`** — any key shadowing a
  LogRecord attribute raises `KeyError: Attempt to overwrite 'message'`.
  Structured payloads built from exceptions hit this constantly.
  `lunad/log.py:safe_extra()` prefixes the colliding keys.
- **`sqlite3.version` was removed in Python 3.14.** Use `sqlite3.sqlite_version`.
- Arch's Python does ship FTS5; `lunad` still probes for it at start and
  refuses to run without it, because tier-2 recall has no useful fallback.
- The agent subprocess gets `start_new_session=True` and is cancelled with
  `killpg` on **its own** group only. This is the session firewall in its
  smallest form: Luna signals what she spawned and nothing else.

Deliberately NOT done in Phase 0: `codex` adapter (flags unverified — it is a
stub that refuses loudly), tier-3 `profile.json`, semantic recall, TTS,
voxtype routing. `~/.config/voxtype/config.toml` was not touched.

---

### 8a.1 Luna voice (Phase 1 groundwork, 2026-08-25)

- **Piper TTS installed into a project venv, NOT system-wide.** `~/Work/luna/.venv`
  (198 MB) via `pip install piper-tts`. Reason: `sudo` requires a password on this
  machine, so an unattended AUR build is impossible. Revert with `rm -rf ~/Work/luna/.venv`.
- **Voice**: `en_GB-jenny_dioco-medium` in `~/.local/share/luna/voices/`
  (61 MB `.onnx` + 4.8 KB `.onnx.json`). Fallback choice: `en_GB-alba-medium`.
- **Measured on this hardware**: cold model load 1.12 s; warm synth 0.41 s for
  6.75 s of audio; **RTF 0.061 (16.4x real time)**; **peak RSS 331 MB**.
- **GOTCHA - the 331 MB.** The ARCHITECTURE.md budget originally said ~60 MB for
  the TTS process; that was wrong by 5x. It is python + onnxruntime, not the
  model file. Consequence: piper must NOT be held resident on a 7 GB machine.
  It lazy-loads and unloads after 5 min idle; cold start is only 1.12 s so the
  cost is one extra second on the first sentence after a lull.
- **GOTCHA - upstream moved.** `rhasspy/piper` went read-only Oct 2025; live repo
  is `OHF-Voice/piper1-gpl` (GPL-3.0). AUR `piper-tts-bin` still tracks the DEAD
  repo - do not use it. `piper-tts-git` is the correct AUR package if ever
  installing system-wide. Also `pacman -Ss piper` matches an unrelated GTK mouse
  tool; ignore it.
- **GOTCHA - `/usr/bin/time` does not exist here** (bash builtin `time` only).
  Benchmark from inside python with `resource.getrusage`.
- Model and its `.onnx.json` must share a basename and directory or piper fails
  silently / sounds wrong.
- Licence: piper is GPL-3.0 but is invoked as a separate binary over a pipe, so
  it does not affect Luna's MIT licence.

### 8a.2 Luna voice pipeline (Phase 1, 2026-08-25)

Voice out (piper -> aplay) and voice in (voxtype `luna` profile -> `lunad`).
Keybind **SUPER+ALT+L** = `voxtype record toggle --profile luna`. Plain
dictation (F9, SUPER+CTRL+X) is untouched and was regression-tested.

Files: `~/Work/luna/lunad/{speech,piper_worker,session}.py`,
`~/Work/luna/bin/luna-voice-router`, `[profiles.luna]` appended to
`~/.config/voxtype/config.toml` (backup at `config.toml.pre-luna`),
one bind appended to `~/.config/hypr/bindings.lua`.

**GOTCHA - voxtype does not re-read its config.** Symptom: you add
`[profiles.luna]`, `voxtype record start --profile luna` succeeds, and the
journal then says `Profile 'luna' not found in config, using default settings`
- so the transcript is TYPED into the focused window instead of going to Luna.
The CLI reads config.toml live (it will list the profile), but the *daemon*
only reads it at startup. `systemctl --user restart voxtype` after any config
edit. This silently degrades to plain dictation; nothing errors.

**GOTCHA - `voxtype config` never prints profiles.** Symptom: you add a profile,
`voxtype config` looks identical, and you conclude it was ignored. It was not.
The only CLI proof that a profile exists is
`voxtype record start --profile __nonexistent__`, which answers with
`Available profiles: luna`.

**GOTCHA - `fallback_on_empty` cannot be turned off for a profile.** Symptom:
the post-process hook returns nothing (correct for Luna, whose reply is spoken,
not typed) and voxtype delivers the ORIGINAL transcript anyway:
`Post-process command returned empty output, using original text`. `struct
Profile` in voxtype 0.7.5 carries only `post_process_command`,
`post_process_timeout_ms` and `output_mode`. Adding a global
`[output.post_process] fallback_on_empty = false` fails outright -
`missing field 'command'` - and supplying a global command would route plain
dictation through Luna too. **The fallback cannot be disabled; it can only be
aimed somewhere harmless.** That is why the profile sets
`output_mode = "clipboard"`: the fallback transcript lands on the clipboard
instead of being typed into whatever window has focus. Verified: 66 chars to
clipboard, 0 bytes typed.

**GOTCHA - a stale `cancel` trigger file eats the NEXT recording.** Symptom:
`voxtype record start` is immediately followed by `Recording cancelled` 0.1 s
later, with no explanation. Cause: `voxtype record cancel` while idle leaves
`$XDG_RUNTIME_DIR/voxtype/cancel` behind, and the daemon consumes it on the
next start. Fix: `rm -f /run/user/1000/voxtype/cancel`. The profile is passed
the same way, via `$XDG_RUNTIME_DIR/voxtype/profile_override` (deleted on read).

**GOTCHA - the voice router must never fail.** voxtype types the raw transcript
on non-zero exit, spawn failure, or timeout. `bin/luna-voice-router` therefore
catches `BaseException`, always exits 0, prints nothing, strips C0 control
bytes, and hands off to `lunad` with `detach` rather than waiting for a reply
(post_process_timeout_ms is 2000; Luna takes seconds). Measured hand-off: 30 ms.

**GOTCHA - piper streams one audio chunk per sentence, not continuously.**
Symptom: a long single sentence produces no audio until it is fully
synthesised. `PiperVoice.synthesize()` yields one `AudioChunk` per sentence, so
sentence splitting is what makes streaming work at all. Luna caps a unit at 260
chars. Measured warm: first audio at **45 ms** for a 14.3 s reply.

**GOTCHA - the sample rate lives in the voice's `.onnx.json`,** under
`audio.sample_rate`. Hard-coding 22050 works for jenny_dioco and silently
pitch-shifts the next voice. `aplay -r <rate> -f S16_LE -c 1 -t raw -`.

**GOTCHA - `lunad`'s cgroup memory jumps to ~470 MB while speaking.** That is
the piper child (331 MB of python + onnxruntime) plus page cache for the 61 MB
model, not a leak. It returns to ~13 MB after the five-minute idle unload,
which is logged as `unloading piper reason=idle 303s`.

**GOTCHA - `pkill -f <string>` kills your own shell** when the string appears in
the shell's own command line. Cost a session mid-test. Use `hyprctl clients` to
find a window and kill by its PID.

**Cost correction, and it is a big one.** The Phase 0 note "separate processes
never share a prompt cache, so every ask costs ~$0.05" was **wrong about the
cause**. Anthropic's prompt cache is keyed on the prompt *prefix* and is shared
across processes; a fresh `claude -p` gets a cache read (measured:
`cache_read_input_tokens: 4510` on a brand-new session id). The real fault was
that tier-2 recall was appended to the *end of the system prompt*, so the whole
~5.5k-token cached prefix was invalidated and re-created on every single ask.
Moving recall into the user message fixed it: **$0.0513/ask before (n=7),
$0.0096/ask after (n=13)**. Session resume (`--session-id`/`--resume`) was also
implemented and is on by default, but its own effect is within noise
($0.0232 vs $0.0289 over three turns) - it is kept for conversational
continuity, not for the money.

## 8b. Ghost Settings — the settings TUI (`ghost-settings`)

One curses TUI for every custom piece of the desktop: Sill (position, expand
behaviour, screenshots, privacy denylist) and the four bar widgets + drawer.
Python 3 **stdlib only** (`curses` + `tomllib`) — no Textual/Rich/urwid.

- **Code** `~/.local/share/ghost-settings/` — `main.py` (CLI), `schema.py`
  (SPEC, the single source of truth, 55 keys), `config.py` (load / clamp /
  atomic save / TOML emitter), `theme.py`, `tui/{app,draw,widgets,screens}.py`.
  `schema.py` + `config.py` are ALSO imported by Sill's
  `~/.local/share/sill/config.py` shim — changing their API breaks Sill.
- **Config** `~/.config/ghost/settings.toml`. The TUI stages edits in memory;
  `s` saves everything atomically (temp file + `os.replace`, one inotify
  event). The emitter regenerates the file with comments from the schema;
  unknown keys are preserved in a trailing block. Every save refreshes
  `settings.toml.bak` (last-known-good) first.
- **Launch** three ways, all one window (same app-id, float rule in
  `windows.lua`): `ghost-settings` in a terminal · **SUPER+COMMA**
  (launch-or-focus) · "Ghost Settings" in the app launcher (.desktop entry).
  **Trade-off:** SUPER+COMMA was Omarchy's "Dismiss last notification" — it
  is `hl.unbind`-ed in `bindings.lua`; dismiss-all stays on SUPER+SHIFT+COMMA.
- **CLI** `ghost-settings get|set|dump --json|check|keys`. `set` validates and
  clamps exactly like the TUI; `dump --json` is what QML bar modules should
  consume (no TOML parser in QML). `check` exits 1 with the parse-error line.
- **Live apply**: save *is* apply — Sill (and later the bar) watch the file.
  The position picker's Space preview writes the candidate through the normal
  save path and restores the previous bytes on release, so the real desktop
  jumps and returns.
- **Robustness**: three layouts (full ≥84×24, stacked ≥60×18, tiny = notice);
  corrupt config opens a recovery screen (edit in $EDITOR / restore backup /
  stage defaults) and never touches the broken file until an explicit save;
  out-of-range values clamp on load; NO_COLOR / 8-colour / non-UTF-8 degrade
  to attributes and ASCII glyphs; Ctrl+C never leaves a broken terminal.
- Single instance via `$XDG_RUNTIME_DIR/ghost/ghost-settings.pid`.

Undo: see §10 — delete the three installed paths and the two Lua blocks.

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
~/.config/omarchy/bar/modules/drawer.qml      icon drawer (wifi/sound/bt/display) (NEW)
~/.local/share/sill/                  Sill: clipboard + screenshots + pins (NEW)
~/.local/share/sill/seen.json         text first-seen sidecar (TTL)   (NEW)
~/.local/bin/{sill,ghost-capture}                                     (NEW)
~/.config/ghost/settings.toml        Sill config, live-reloaded      (NEW)
~/.config/ghost/flags/               bind flag files, written by Sill (NEW)
~/.config/hypr/windows.lua           Sill behaviour rules            (NEW)
~/.config/hypr/sill-position.lua     generated by Sill on position change (NEW)
~/.config/hypr/bindings.lua          PRINT rebound; SUPER+SHIFT+V Sill;
                                     SUPER+SHIFT+Delete purge; flag-gated
                                     SUPER+CTRL+V unbind
~/.config/hypr/autostart.lua         starts ghost-shotshelf.service
~/.config/systemd/user/sill.service                                   (NEW)
~/.config/omarchy/bar/scripts/sysmon                                  (NEW)
~/.config/omarchy/plugins/ghost.barisland/                            (NEW)
~/.config/omarchy/plugins/ghost.barhover/     hover-to-expand for Sill (NEW)
~/.local/state/omarchy/powerprofiles/ac                               (NEW)
/boot/limine.conf                    timeout 5 -> 2
~/Work/luna/                          Luna: lunad package, bin/luna, tests (NEW)
~/.local/share/luna/                  Luna state: memory/, luna.log          (NEW)
~/.config/systemd/user/lunad.service                                        (NEW)
~/Work/luna/lunad/speech.py           piper worker, stripper, sentence split (NEW)
~/Work/luna/lunad/piper_worker.py     runs under .venv python, framed audio   (NEW)
~/Work/luna/lunad/session.py          conversation session reuse              (NEW)
~/Work/luna/bin/luna-voice-router     voxtype post_process hook, always exit 0 (NEW)
~/.local/share/luna/voice-router.log  router breadcrumbs                      (NEW)
~/.config/voxtype/config.toml         + [profiles.luna] ONLY (additive)
~/.config/voxtype/config.toml.pre-luna  byte-identical backup                 (NEW)
~/.config/hypr/bindings.lua           + SUPER+ALT+L "Talk to Luna"
~/.local/share/ghost-settings/       settings TUI + schema + CLI (Sill imports schema/config) (NEW)
~/.local/bin/ghost-settings          launcher                        (NEW)
~/.local/share/applications/ghost-settings.desktop                   (NEW)
~/.config/hypr/bindings.lua          + SUPER+COMMA Ghost Settings (Omarchy
                                     dismiss-last-notification unbound)
~/.config/hypr/windows.lua           + ghost-settings float rule
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
systemctl --user disable --now sill.service
rm -f ~/.config/systemd/user/sill.service
rm -rf ~/.local/share/sill ~/.local/bin/sill ~/.local/bin/ghost-capture ~/.config/ghost
rm -f ~/.config/hypr/windows.lua   # and drop require("hypr.windows") from hyprland.lua
omarchy restart shell

# Ghost Settings TUI
rm -rf ~/.local/share/ghost-settings ~/.local/bin/ghost-settings
rm -f ~/.local/share/applications/ghost-settings.desktop
# then delete the SUPER+COMMA block at the end of bindings.lua (restores
# Omarchy's dismiss-last-notification) and the ghost-settings rule at the
# end of windows.lua; hyprctl reload

# Theme
omarchy theme set "Matte Black"
rm -rf ~/.config/omarchy/themes/monochrome

# Power
rm -f ~/.local/state/omarchy/powerprofiles/ac
powerprofilesctl configure-action --disable amdgpu_panel_power
sudo cp /boot/limine.conf.bak.pretune /boot/limine.conf
sudo systemctl enable --now cups.service cups.socket avahi-daemon.service

# Luna (Phase 0)
systemctl --user disable --now lunad.service
rm -f ~/.config/systemd/user/lunad.service && systemctl --user daemon-reload
rm -rf ~/.local/share/luna          # memory + log; ~/Work/luna is the source, keep it

# Luna voice (Phase 1) -- do this BEFORE the Phase 0 block if undoing both
cp ~/.config/voxtype/config.toml.pre-luna ~/.config/voxtype/config.toml
rm -f ~/.config/voxtype/config.toml.pre-luna
systemctl --user restart voxtype    # REQUIRED: the daemon never re-reads config
# then delete the SUPER+ALT+L "Talk to Luna" bind at the end of bindings.lua
hyprctl reload
rm -rf ~/Work/luna/.venv            # 198 MB piper install
rm -rf ~/.local/share/luna/voices   # 61 MB voice model

# Nuclear
omarchy refresh hyprland && omarchy refresh shell
```
