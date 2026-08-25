# omarchy-monochrome

A greyscale [Omarchy](https://omarchy.org) desktop: a floating rounded bar,
four custom Quickshell bar widgets, and a screenshot shelf that does not
disappear before you have decided what to do with the screenshot.

Built natively on Omarchy rather than by dropping in foreign dotfiles — nothing
here forks or patches `/usr/share/omarchy/`, so `omarchy update` stays safe.

![bar](docs/preview-bar.png)

## What's in here

### Bar widgets — `bar/modules/`

| Module | What it does |
|---|---|
| `mediapill.qml` | Now-playing. Idle it is an animated equaliser glyph and an elided track label over a progress hairline. Hover fills the pill in, slides out prev / play-pause / next, and marquees the label. Click opens a panel with artwork, a scrubbable timeline, shuffle/repeat, volume and a source switcher. |
| `sysmon.qml` | CPU / GPU / RAM / temperature with a CPU sparkline, and a detail pop-out. |
| `pomodoro.qml` | Focus timer — 15/25/45/60/90. |
| `notes.qml` | Scratchpad that saves itself 900ms after you stop typing. |

### Plugins — `plugins/`

| Plugin | What it does |
|---|---|
| `ghost.barisland` | Paints a rounded floating plate behind the bar. Omarchy's bar cannot be detached from the screen edge, so the bar is made taller and transparent and this draws an island inside that band, on the layer below. |
| `ghost.shotshelf` | Persistent screenshot shelf. Replaces the 5-second toast with a card that stays until dismissed and collapses to a chip instead of vanishing. Copy path, copy image, or open in an editor; a strip holds the last six. |

### Theme — `themes/monochrome/`

Forked from Omarchy's **Vantablack**. Total greyscale, no colour in any ANSI
slot. Near-black `#0a0a0b` base, cool ash `#dfe3e6` foreground.

## Install

Requires Omarchy 4.x (Hyprland + Quickshell). `ghost.shotshelf` also needs
`inotify-tools` and `wl-clipboard`.

```bash
git clone https://github.com/TheFadGhost/omarchy-monochrome
cd omarchy-monochrome

# Back up what you have first.
cp ~/.config/omarchy/shell.json ~/.config/omarchy/shell.json.bak

mkdir -p ~/.config/omarchy/bar/modules ~/.config/omarchy/bar/scripts
cp bar/modules/*.qml   ~/.config/omarchy/bar/modules/
cp bar/scripts/sysmon  ~/.config/omarchy/bar/scripts/
chmod +x ~/.config/omarchy/bar/scripts/sysmon
cp -r plugins/ghost.*  ~/.config/omarchy/plugins/
cp -r themes/monochrome ~/.config/omarchy/themes/

# The bar is made 44px tall so the island has room to float inside it.
cp examples/shell.toml ~/.config/omarchy/shell.toml

omarchy restart shell
omarchy theme set Monochrome
```

Then register the widgets. `examples/shell.json` is a complete working file you
can copy wholesale, or crib the relevant bits: each custom module goes in
`bar.layout.<section>` as `{"id": "<name>", "type": "qml"}`, and each plugin as
`{"id": "ghost.<name>"}` in the top-level `plugins[]` array.

`mediapill` is intended to replace the first-party `omarchy.media` widget —
drop `{"id": "omarchy.media"}` when you add it, or you will have two.

## Design

Everything here is built from Omarchy's own UI components — `PopupCard`,
`BorderSurface`, `PanelSectionHeader`, `PanelSeparator`, `PanelSlider`,
`Ui/Button` — with sizes from `Style.space()`, fonts from `Style.font.*` and
colours from `Color.*`. Nothing is a hardcoded pixel value or hex literal, so
all of it re-themes with the rest of the shell.

That works because user QML can `import qs.Ui` and `import qs.Commons` even
from outside `/usr/share/omarchy/shell`: the shell is one Quickshell engine,
that path is the `qs` module namespace, and `qs.*` resolves against the engine
rather than the importing file's directory.

## Notes on the screenshot shelf

It cannot drag a file out, and that is not an oversight:

- QtQuick's `Drag` is scene-local only. Its `DragType` enum is
  `None`/`Automatic`/`Internal` — there is no `External` — and Quickshell
  registers no drag-and-drop types at all. Real cross-application drag needs
  C++ calling `QDrag::exec()` on an `xdg_toplevel`, which a layer-shell surface
  driven from QML cannot reach. A helper toplevel window is the only route, and
  is how Flameshot does it.
- Synthesising a paste does not work either, at least on Hyprland 0.56: `wtype`
  exits 0 and delivers nothing.

So the clipboard does the work, which is reliable. `wl-copy` puts the path or
the PNG where you need it and you paste normally.

## Documentation

[`docs/CUSTOMISATIONS.md`](docs/CUSTOMISATIONS.md) is the full recovery
reference for the machine this came from — every change, why it was made, and
the QML/Quickshell gotchas found the hard way (§6b and §6d are the useful ones
if you are writing your own widgets).

## Licence

MIT — see [LICENSE](LICENSE). The wallpaper in `themes/monochrome/backgrounds/`
came with Omarchy and keeps whatever licence it had there.
