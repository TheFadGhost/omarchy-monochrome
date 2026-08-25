# Sill — implementation plan

One GTK4/Python panel merging **clipboard history**, **screenshot history**, and a
**pinned drag-stash** on Hyprland/Omarchy. Everything drags OUT in native format;
things drag IN. Greyscale, JetBrainsMono, 8 GB laptop. This document synthesises
the four review passes (UX, settings-TUI, architecture, adversarial) into the
single buildable plan. Settled user decisions are not relitigated here; where
reviewers disagreed, the resolution is stated in one line with the reason.

Companion documents, both authoritative:

- `docs/ghost-settings-design.md` — the settings TUI, adopted as designed (schema
  updated per §"Contradictions resolved" below).
- `~/.config/omarchy/CUSTOMISATIONS.md` §6d/§6e — the design-system rule and the
  drag/layer/theming gotchas. Every one of them applies to Sill unchanged.

---

## 0 · Contradictions resolved

| # | Disagreement | Resolution |
|---|--------------|------------|
| 1 | Build order: stash-first (the novel thing) vs screenshots-first | **Screenshots first.** The code exists and works; clipboard data already exists on disk; the stash is novel, gated on an untested compositor behaviour, and has the least proven demand. Ship risk last. |
| 2 | Cut the settings TUI ("a 43-key curses TUI is more code than the panel it configures; a commented TOML file already *is* the UI") | **Objection recorded, overruled by user decision.** Mitigation: the TUI is scheduled last (Phase 4), and the schema/config substrate it shares ships in Phase 1 — so hand-editing the TOML works from day one and the TUI never blocks the panel. |
| 3 | Own clipboard watcher vs reading Omarchy's store | **Read Omarchy's store.** Two `wl-paste` readers of one selection race, and each reader is another chance to snapshot a secret. Sill is a *renderer* of `~/.local/state/omarchy/clipboard-history.json`, with a schema guard (§4). |
| 4 | Merge for RAM savings | **Merge, but not for RAM** — marginal cost of a second GTK4 process is ~28 MB. Merge for lifecycle: one process, one systemd unit, one journal, one theme watcher. |
| 5 | Panel drawn in the bar vs faked attachment | **Faked.** `omarchy-bar` is a layer-shell surface at level `top` and stacks above every xdg_toplevel; and a drag cannot originate from a layer surface anyway. Sill is an xdg_toplevel pinned below the bar line, same illusion `ghost.barisland` runs from the other side. |
| 6 | Hover-near-bar detection: enlarged input region vs socket polling vs Quickshell plugin | **Quickshell service plugin** (`MouseArea { acceptedButtons: Qt.NoButton }` over the bar's empty space, reporting via IPC — mirrors `ghost.barisland`). Raw-socket cursor polling (0.041 ms) stays as a config-gated fallback; `hyprctl` polling (7 ms) never. |
| 7 | Design doc's stash tabs (clips/files/images/links) vs settled tabs | Settled wins: **Clipboard · Screenshots · Pinned**. Links tab cut. |
| 8 | Design doc `max_age_days = 14` vs brief "7 days" | Brief wins: **7**. Ditto history **200** items, both configurable. |
| 9 | Design doc `[stash.capture]` toggles (text/images/files/dedupe/min-len) | **Cut.** Sill does not capture — Omarchy does. Capture toggles would be lies; display filters are out of v1 scope. |
| 10 | `hyprctl keyword windowrule` for the new window rules | **Never.** On this Hyprland it exits 0 and silently does nothing. All rules go in `~/.config/hypr/windows.lua`; keybinds in `bindings.lua`. |

One consequence of #3 that the brief's "disable Omarchy's SUPER+CTRL+V" option
must respect: **the `wl-paste` watchers are owned by the Omarchy clipboard
plugin** (`Clipboard.qml:266,301` starts and resurrects them). Disabling the
Omarchy clipboard therefore means **unbinding the key only** — the plugin stays
loaded, or capture dies and Sill's Clipboard tab starves.

---

## 1 · Phasing

Each phase is independently shippable, with an explicit stop line.

### Phase 0 — Gates (≈ half a day, throwaway code only)
Run every runtime check in §2 and build the two prototypes (drag-out mime
verification, drag-IN gate). Nothing ships; every later phase consumes a
Phase 0 answer. **Stop here and it's still worth having:** knowledge — you know
whether the stash is buildable before writing Sill line one.

### Phase 1 — Sill shell + Screenshots tab (the merge)
Port `shotshelf.py` into a new single-instance app `sill`: one fixed-size
transparent toplevel canvas at the top-right, input region cut to the visible
chip/panel (the exact shotshelf pattern), a tab bar (Clipboard and Pinned tabs
present but empty-stubbed), and the Screenshots tab carrying everything the
shelf does today plus the new behaviours: **15 s auto-collapse**, collapsed pill
**draggable** with **✕ on hover**, **click-to-rename** the filename (renames the
file on disk; the directory monitor's `MOVED_*` handling already copes).
`SUPER+SHIFT+V` toggles. `sill.service` with `Restart=on-failure` replaces
`ghost-shotshelf.service`. Migration per §5. `ghost-settings` **schema.py +
config.py only** land now (no TUI): Sill loads `~/.config/ghost/settings.toml`,
clamps, and live-applies via file watch — hand-editing works from day one.
**Stop here:** a supervised, keybound, tabbed screenshot shelf — everything the
old shelf did, run properly.

### Phase 2 — Clipboard tab + privacy hardening
Read-only renderer of the Omarchy store with the schema guard (§4). Rows show
text previews / image thumbnails (pre-scaled, never full-res — 8 GB rule).
**Drag out offers all formats** via a union provider; **click = copy + close**.
Privacy: `sill purge` command + `SUPER+SHIFT+DELETE` bind; text TTL + orphan
image pruning (§4); `chmod 600` the store / `700` the images dir on every
reload; optional purge-on-lock via logind `LockedHint` (default off — the
screensaver locks at 10 min idle and purging on every lock would gut the
feature; the TTL and purge key are the defaults); reactive source-exclusion
(§4, with its honest race documented). The `disable_omarchy_clipboard` option
lands here (unbind-only, flag-file mechanism, §3). **Stop here:** Sill's core
value delivered — this is the 80 % product.

### Phase 3 — Pinned tab (gated on check R7)
Only if the Phase 0 drag-IN gate passed. Drop target on chip and panel,
pin store (§4), context-aware default tab (just dropped → Pinned; screenshot
< 60 s ago → Screenshots; else last used). A **pin button on every clipboard
and screenshot row ships regardless of the gate** — so Pinned is useful even
if cross-app drag-in is degraded or cut. **Stop here:** the complete
three-tab Sill.

### Phase 4 — `ghost-settings` TUI
The design doc, built as written, on the schema/config modules already running
since Phase 1: curses TUI, `get/set/dump --json/check` CLI, desktop entry,
`SUPER+comma`, nine-point picker with live preview. **Stop here:** everything
configurable from one place, live.

### Phase 5 — Hover-expand plugin
`ghost.sillhover` Quickshell service plugin reporting pointer-over-empty-bar
via IPC; Sill expands on it (toggleable, per settled decisions). Drag-start
expansion via `Gtk.DropControllerMotion` on the chip's own surface (no
compositor tricks needed). Raw-socket polling fallback behind a config flag.

### Phase 6 — Bar drawer (independent, gated on check R10)
Collapse wifi/bluetooth/sound/display into one bar group expanding on hover.
Pure Quickshell; touches no Sill code; can be built any time after R10.

---

## 2 · Runtime checks BEFORE writing code

In execution order. Each names what it decides. R1–R6 gate Phase 1–2, R7/R9
gate Phase 3, R8 gates Phase 5, R10 gates Phase 6, R12 gates purge-on-lock.

**R1 — store schema baseline** *(known-good as of 2026-08-25; builder re-runs)*
```bash
jq -e 'type=="array" and all(.[]; .type=="text" or .type=="image")' \
  ~/.local/state/omarchy/clipboard-history.json
```
Pass → reader as designed (§4). Fail → the store drifted since this plan;
re-derive the normaliser from `ClipboardHistory.js` before coding.

**R2 — capture watchers alive**
```bash
pgrep -af 'wl-paste.*--watch.*clipboard/capture\.sh'
```
Expect two processes (text + image). Confirms Sill can rely on Omarchy's
capture, and that the watchers belong to the Quickshell plugin — hence
unbind-only for the disable option.

**R3 — image drag mimes (the finding-3 trap)**
```bash
python3 - <<'EOF'
import gi, glob
gi.require_version("Gtk","4.0"); gi.require_version("Gdk","4.0")
from gi.repository import Gdk, Gtk, GObject
Gtk.init()
png = glob.glob(f"{__import__('os').path.expanduser('~')}/.local/state/omarchy/clipboard-images/*.png")[0]
tex = Gdk.Texture.new_from_filename(png)
bad  = Gdk.ContentProvider.new_for_value(tex)                       # zero mimes
v = GObject.Value(); v.init(Gdk.Texture); v.set_object(tex)
good = Gdk.ContentProvider.new_for_value(v)                         # ~16 mimes
for name, p in (("bad", bad), ("good", good)):
    print(name, p.ref_formats().union_serialize_mime_types().get_mime_types())
EOF
```
`good` must list ~16 `image/*` mimes; empty → blocker, investigate before
Phase 2. This snippet becomes the permanent `sill doctor --self-test`.

**R4 — text drag mimes** — same script pattern with
`Gdk.ContentProvider.new_for_value("probe")`; require
`text/plain;charset=utf-8` on the wire. Third provider path, same trap class.

**R5 — union provider** — `Gdk.ContentProvider.new_union([file_list_p, texture_p])`
must advertise the union (uri-list + portal + image mimes). This is the
"drag out offers all formats, target chooses" mechanism. Empty/partial →
fall back to per-kind single providers and drop the all-formats claim.

**R6 — bar geometry for the fake attachment**
```bash
hyprctl monitors -j | jq '.[0] | {reserved, width, scale}'
```
Decides the chip's `move` rule (y = reserved-top + 2, x = right edge − chip −
margin). Re-read at runtime on `monitoradded`/config-reload events — the bar
height is themed, not constant.

**R7 — drag-IN gate (the highest-risk unknown; 30-line throwaway)**
GTK toplevel at the chip's position with a `Gtk.DropTarget` accepting
`Gdk.FileList`, `str`, `Gdk.Texture`. Human drags in: text selection from the
browser, an image from a page, a link from the address bar, a file from the
file manager. Outcomes: all land → Pinned as designed. Browser drags die
crossing the tab strip → move the drop zone / expanded panel lower and accept
the longer drag path. Nothing lands → **cut drag-in**; Pinned becomes
pin-button-only (which ships anyway).

**R8 — hover plugin probe** — minimal `ghost.sillhover` service plugin:
`MouseArea { acceptedButtons: Qt.NoButton }` over the bar's empty-space region,
writing enter/leave to a UNIX socket. Verify (a) events fire, (b) bar icons
still take clicks. Fail → hover-expand ships only in raw-socket-polling mode,
default off.

**R9 — input-region growth mid-drag** — inside the R7 prototype, call
`surface.set_input_region()` to a larger rect while a drag is latched over the
window. Works → generous drop zone during drags. Undefined/broken → the drop
target stays chip-sized (still fine — R7's chip-sized target is the design).

**R10 — bar drawer feasibility** — probe user module attempting
`Qt.createComponent` on the shell's network/audio/bluetooth bar widgets
(namespace visible under `/usr/share/omarchy/shell/bar/`); §6d proves `qs.*`
resolves from user modules, but not that these particular components accept
external instantiation. Works → drawer wraps the real widgets. Fails → drawer
shows its own glyphs and toggles the corresponding `omarchy-shell` panels.

**R11 — session target** — `systemctl --user is-active graphical-session.target`.
Known good (ghost-shotshelf.service already rides it); skip unless migrating a
new machine.

**R12 — lock signal for purge-on-lock**
```bash
gdbus monitor -y -d org.freedesktop.login1 | grep -i --line-buffered locked &
loginctl lock-session
```
`LockedHint` flips → subscribe via `Gio.DBusProxy` in-process. Doesn't → hook
the hypridle lock command instead (wrapper script calls `sill purge --lock`).

---

## 3 · File-by-file inventory

### Created

| Path | Phase | Purpose |
|---|---|---|
| `~/.local/share/sill/main.py` | 1 | Single-instance `Adw.Application` (`dev.ghost.sill`); window + chip on one fixed transparent canvas; input-region sync; expand/collapse; tab host; context-aware tab pick; `toggle`/`purge` D-Bus actions; logind lock watch (P2) |
| `~/.local/share/sill/screenshots_tab.py` | 1 | Ported shotshelf: dir monitor (`CHANGES_DONE_HINT`), fan, pill, 15 s collapse, rename-on-click (`os.rename` + monitor reconciliation), ✕-on-hover |
| `~/.local/share/sill/theme.py` | 1 | Ported `read_theme`/`current_font`/CSS build + the parent-dir theme watch (the `rm -rf current/theme` gotcha) |
| `~/.local/share/sill/providers.py` | 1 | The only place drag providers are constructed: `Gdk.FileList` for files, `GObject.Value(Gdk.Texture)` for images, str for text, `new_union` for all-formats; plus `self_test()` asserting on-wire mimes |
| `~/.local/share/sill/config.py` | 1 | Thin shim: adds `~/.local/share/ghost-settings` to `sys.path`, imports its `schema`/`config`, arms the `Gio.FileMonitor` + 100 ms debounce, dispatches per-key APPLY handlers |
| `~/.local/share/ghost-settings/schema.py` | 1 | `SPEC` — single source of truth, per design doc, with the merged `[sill]` sections (§"schema delta" below) |
| `~/.local/share/ghost-settings/config.py` | 1 | load/clamp/diff/atomic-save/TOML emitter, per design doc |
| `~/.local/bin/sill` | 1 | Launcher: `sill` (run) · `toggle` · `purge` · `doctor [--self-test]` |
| `~/.config/systemd/user/sill.service` | 1 | `Restart=on-failure`, `RestartSec=3`, `PartOf=graphical-session.target` — clone of the existing ghost-shotshelf unit |
| `~/.local/share/sill/shim/omarchy-notification-send` | 1 | Toast shim, moved from ghost-shotshelf |
| `~/.config/ghost/settings.toml` | 1 | The config (generated with defaults on first save; absent file = defaults) |
| `~/.local/share/sill/store_clipboard.py` | 2 | Omarchy-store reader: tolerant normaliser, schema guard, debounced reload, perms hardening, TTL/orphan prune, purge |
| `~/.local/share/sill/clipboard_tab.py` | 2 | List UI, drag-out union providers, click = copy + close |
| `~/.config/ghost/flags/disable-omarchy-clipboard` | 2 | Flag file (existence = on) read by `bindings.lua` at config parse; written by settings save, which then runs `hyprctl reload` |
| `~/.local/share/sill/store_pins.py` | 3 | `pins.json` + `blobs/` content store (§4) |
| `~/.local/share/sill/pinned_tab.py` | 3 | Drop targets, pin rows, unpin |
| `~/.local/share/ghost-settings/main.py`, `theme.py`, `tui/*` | 4 | The TUI per design doc, unchanged |
| `~/.local/bin/ghost-settings` | 4 | Launcher |
| `~/.local/share/applications/ghost-settings.desktop` | 4 | Omarchy menu entry (`xdg-terminal-exec --app-id=ghost-settings`) |
| `~/.config/omarchy/plugins/ghost.sillhover/{manifest.json,Hover.qml}` | 5 | Hover-over-empty-bar service plugin → UNIX socket |
| `~/.config/omarchy/bar/modules/drawer.qml` | 6 | The wifi/bt/audio/display drawer |

### Modified

| Path | Phase | Change |
|---|---|---|
| `~/.config/hypr/windows.lua` | 1 | Shelf rules re-pointed at `^dev\\.ghost\\.sill$` (same body: float, pin, no_initial_focus, no_follow_mouse, no_anim, border 0, rounding 0, fixed size/move from R6); canvas sized for the panel (~560×720, top-right) |
| `~/.config/hypr/bindings.lua` | 1,2,4 | P1: `o.bind("SUPER + SHIFT + V", "Sill", "sill toggle")`. P2: purge bind + conditional `hl.unbind("SUPER + CTRL + V")` on the flag file. P4: `SUPER + comma` → ghost-settings via `omarchy-launch-or-focus-tui` |
| `~/.config/hypr/autostart.lua` | 1 | `systemctl --user start sill.service` (replaces ghost-shotshelf line) |
| `~/.local/bin/ghost-capture` | 1 | Shim `PATH` re-pointed at `~/.local/share/sill/shim`; `PRINT` binding itself unchanged |
| `~/.config/omarchy/bar/modules/notes.qml` | 1 | Glyph → pencil (settled decision; one-line) |
| `~/.config/omarchy/shell.json` | 6 | Remove individual wifi/bt/audio/display entries; add drawer module |
| `~/.config/omarchy/CUSTOMISATIONS.md` | each | §6e rewritten as the Sill section; drawer + hover plugin documented when they land |

### Retired (Phase 1, after hand-verification passes)

`~/.local/share/ghost-shotshelf/` (git history keeps it),
`~/.config/systemd/user/ghost-shotshelf.service` (`disable` + delete). See §5.

### Settings schema delta vs the design doc

`[shelf]`+`[stash]` merge into `[sill]` (the doc predates the merge):
`position` (nine-point, default top-right) · `margin` · `keybind_toggle` on ·
`expand_on_hover` on · `expand_on_drag` on · `expand_on_click` on ·
`hover_delay_ms` 300 · `collapse_s` 15 · `max_items` 200 · `max_age_days` 7 ·
`disable_omarchy_clipboard` off · `purge_on_lock` off ·
`[sill.screenshots] max_history` 10 + the action toggles ·
`[sill.privacy] denylist` (KeePassXC, 1Password). `[stash.capture]`, links tab,
and the separate `[shelf]` section are deleted. Bar sections unchanged.

---

## 4 · Data layer

One in-memory model, three sources of truth:

```python
@dataclass
class Item:
    kind: str          # "text" | "image" | "file"
    title: str; when: float
    payload: str       # text content, or absolute path
    origin: str        # "clipboard" | "screenshot" | "pin"
    # providers() -> Gdk.ContentProvider (union, via providers.py)
    # paintable(w,h) -> pre-scaled texture (never full-res; 8 GB rule)
```

| Tab | Source of truth | Sill writes? | Eviction |
|---|---|---|---|
| Clipboard | `~/.local/state/omarchy/clipboard-history.json` + `clipboard-images/` | Prune/purge only (below) | Display: newest 200 within 7 days. Store: Omarchy's own 300-cap + Sill's prune |
| Screenshots | The screenshot directory itself | Rename on user click; delete only via explicit trash action | Display: last `max_history`; files never auto-deleted |
| Pinned | `~/.local/share/sill/pins/` — `pins.json` index + `blobs/` | Yes — Sill's own store | Never; manual unpin only |

**Clipboard reader.** `Gio.FileMonitor` on the JSON, 250 ms debounce. The
normaliser is a Python port of `ClipboardHistory.js::normalizeEntry`: accepts
bare strings and `{type: text|image}` objects, skips unknown types, tolerates
missing `capturedAt` (the store's `"Tuesday 03:45"` stamps are display-only;
Sill orders by array position and uses image-file mtimes for TTL; text entries
carry no timestamp, so text TTL keys on a sidecar `~/.local/share/sill/seen.json`
mapping content-hash → first-seen, pruned with the store).

**Schema guard** (the Omarchy-update tripwire):
- File missing → empty tab + banner `clipboard store missing`.
- JSON parse failure → retry once after 250 ms (mid-write), then keep the
  **in-memory** last-good snapshot + banner `clipboard store unreadable —
  Omarchy update? showing session cache`. Never persisted to disk — a
  last-good file would duplicate secrets past a purge.
- Parses, but > 0 raw entries yield 0 recognised → schema drift: same banner
  path. `sill doctor` prints store path, raw/recognised counts, watcher pids,
  unit status, and runs the provider mime self-test.

**Pins.** Pinning **text or an image copies the content** into `blobs/`
(content-hash filename) so the pin survives clipboard eviction and purges.
Pinning a **file records the path** (a stash must not duplicate a 2 GB file);
a dead path renders greyed with the path still draggable as text. `pins.json`
is written atomically (temp + `os.replace`), same discipline as the config.

**Prune & purge (the only writes to Omarchy's store — deliberate, bounded):**
- `sill purge` / `SUPER+SHIFT+DELETE` / optional on-lock: atomically write
  `[]`, delete `clipboard-images/*`, clear memory. Pins untouched.
- TTL prune (startup + daily timer): drop entries older than `max_age_days`,
  delete image files not referenced by the surviving JSON **and** older than
  24 h (grace window against racing an in-flight capture — this closes the
  never-pruned `clipboard-images` leak). Read-modify-`os.replace` in
  milliseconds; the theoretical race with the Quickshell writer can lose at
  most one concurrent capture and only while pruning old entries — accepted
  and documented, in exchange for not forking Omarchy's pacman-owned pipeline.
- Perms hardening on every reload: `chmod 600` the JSON, `700` the images dir
  (Omarchy recreates at 644; re-asserting is one cheap syscall).

**Source-based exclusion (honest version).** True exclusion needs the capture
side, which is pacman-owned — not forked (§7). Sill's denylist is *reactive*:
on each new entry, if `hyprctl activewindow -j | jq .class` at event time
matches the denylist, the entry is deleted from the store and never rendered.
The secret exists on disk for ~1 s and in the Wayland selection regardless —
documented in the settings About text, not hidden. Apps that set
`x-kde-passwordManagerHint` are already excluded upstream by `capture.sh`.

---

## 5 · Migration (retiring ghost-shotshelf)

Per the house rule (*verify dependent state*): every consumer of the old app id
and paths, checked off. Sequence, all in Phase 1:

1. `systemctl --user disable --now ghost-shotshelf.service`; install + enable
   `sill.service`.
2. `windows.lua`: the shelf rule block re-pointed at `^dev\\.ghost\\.sill$`,
   geometry updated from R6. Grep for `shotshelf` afterwards — zero hits
   outside git history is the done condition.
3. `autostart.lua`: swap the `systemctl --user start` target.
4. Keybinds: `PRINT` → `ghost-capture` **unchanged** (only the shim path inside
   `ghost-capture` moves). The shelf never had a toggle bind; `SUPER+SHIFT+V`
   is new, no collision (verified: nothing binds it today).
5. `ghost-shotshelf.service` and `~/.local/share/ghost-shotshelf/` deleted
   **after** the Phase 1 hand-verification list passes.
6. Docs: CUSTOMISATIONS.md §6e rewritten as "Sill" — the drag-provider,
   input-region, theme-watch and natural-size gotchas all carry over verbatim.
7. Not migrated: shelf thumbnails/state (none persisted — nothing to move).

Rollback at any point: re-enable `ghost-shotshelf.service`, revert the three
Lua files (git-tracked). Keep the old tree until step 5.

---

## 6 · Test strategy

Hard constraint: **pointer input cannot be synthesised here** (`wtype` and
`hl.dsp.send_key_state` are keyboard-only; `BTN_LEFT` returns ok and does
nothing). So: automate everything that isn't a pointer, and keep the hand list
short and phase-scoped.

**Automated (pytest, runs inside the session; no pointer needed):**
- `store_clipboard` fixtures: current schema, bare-string legacy entries,
  unknown `type`, truncated JSON, empty file, 1 MB text entry, missing image
  file → normaliser + schema-guard state machine assertions.
- Prune: TTL boundary, referenced vs orphan images, 24 h grace, purge leaves
  pins.
- Pins: atomic write, blob dedupe, dead-path rendering state.
- Config: load/clamp/round-trip, unknown-key preservation, `.bak` fallback —
  per the design doc.
- **Provider mime self-test** (`sill doctor --self-test`): for text, image and
  file items, assert the exact on-wire mime lists from
  `ref_formats().union_serialize_mime_types()`. This is the permanent
  regression net for the zero-mime trap — a provider refactor cannot silently
  ship an empty drag.
- TUI: drive `Screen.handle()` with synthetic key sequences; assert staged
  state and emitted TOML. No terminal, no curses init needed.
- Keyboard-level integration (wtype works for keys): `SUPER+SHIFT+V` toggle
  round-trip asserted via the app's own D-Bus action log.

**Human hand-verification (the complete list — once per phase that touches it):**
1. *(P1)* Screenshot arrives → panel expands, focus stays in the terminal;
   pill ✕ appears on hover; drag from the collapsed pill lands in a browser
   upload field; rename-click renames the file on disk.
2. *(P2)* Drag a text row into a textarea; an image row into an image-accepting
   target; verify the target got its preferred format. Click a row → paste
   lands, panel closed.
3. *(P0/P3)* The R7 drag-IN matrix (text / page image / link / file), repeated
   once on the finished Pinned tab; drag a pin back out.
4. *(P5)* Hover empty bar space → expand after delay; bar icons still click.
5. *(P6)* Drawer expands on hover, icons inside still work.

Five items; nothing else requires a pointer.

---

## 7 · Risk register

| Risk | Trigger | How the user notices | Mitigation |
|---|---|---|---|
| Omarchy changes the private store schema | pacman update | Banner in Clipboard tab (never a silent empty panel) | Tolerant normaliser; in-memory last-good; `sill doctor`; pins unaffected by design |
| Two writers race on the store (Sill prune vs Quickshell) | Capture during a prune tick | At worst one lost clipboard entry, rarely | Prune only old entries, atomic `os.replace`, ms-scale window; documented accepted risk |
| Drag-in unbuildable/flaky across the browser tab strip | R7 gate fails | Feature absent, not broken | Gate before build; pin-button path ships regardless |
| Input-region growth mid-drag undefined | R9 fails | Drop zone is chip-sized only | Designed-in fallback; never depended on |
| Bar-attachment illusion drifts | Theme/bar-height change, monitor events | Chip floats off the bar line | Geometry from `hyprctl monitors -j` reserved area at start + on monitor/config events, never hardcoded |
| omarchy-shell update breaks `ghost.sillhover` | Shell update | Hover-expand stops; click/keybind still work | Degrades gracefully; hover is one of four expand triggers, all toggleable |
| Sill dies silently (shotshelf precedent) | Any crash | It doesn't stay dead | `sill.service` `Restart=on-failure` + `journalctl --user -u sill`; `diagnose-crash` skill for cores |
| A provider refactor ships zero mimes again | Any drag-code edit | Drag looks perfect, drops nothing | Automated mime self-test in CI-path and `sill doctor` |
| `hyprctl keyword windowrule` silently no-ops | Any tempted shortcut | Rules don't apply, exit 0 lies | Rules only ever in `windows.lua`; noted in CUSTOMISATIONS |
| Secrets linger (644 store, unpruned images, plaintext) | Normal use | — (that's the problem) | chmod 600/700 each reload; TTL 7 d; orphan-image prune; purge bind; optional purge-on-lock; reactive denylist with documented limits |
| Disabling Omarchy clipboard kills capture | User flips the option | Clipboard tab starves | Option unbinds the key **only**; plugin (which owns the watchers) stays loaded; `sill doctor` checks watcher pids |
| 8 GB memory pressure | Long sessions, many images | Sluggishness | Pre-scaled textures only (shotshelf discipline), bounded thumb cache, single process |

---

## 8 · Explicitly NOT being built

- **A second clipboard watcher / cliphist** — cliphist isn't installed; two
  readers of one selection race and double the secret-snapshot surface.
- **Forking or overriding `capture.sh`** — pacman-owned; a fork diverges
  silently on every Omarchy update. Hence "reactive" exclusion, honestly
  documented, instead of capture-side exclusion.
- **Rendering inside the bar / as a layer-shell surface** — the bar stacks
  above all toplevels, and a layer surface cannot originate a drag (wlroots
  serial + focus validation; KWin bug 502497). Faked attachment only.
- **Quickshell drag of any kind** — proven impossible (`Drag` is scene-local,
  no External type); the panel is GTK4 forever.
- **Search/filter in the panel** — Omarchy's own clipboard UI has search;
  Sill v1 is a drag surface, not a browser. Revisit on demand.
- **Links tab, capture toggles, multi-monitor per-output anchoring,
  encryption at rest, sync** — cut for scope; none blocks a later add
  (schema-driven settings make each a one-line schema change plus UI).
- **A settings daemon / D-Bus config bus** — atomic file replace + per-app
  file watch won that comparison in the design doc; nothing here changes it.
