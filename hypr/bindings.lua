-- ============================================================================
-- Personal keybindings
--
-- All keys below were verified free against `omarchy menu keybindings --print`
-- before being bound, so no hl.unbind() calls are needed.
-- ============================================================================

-- Apps
o.bind("SUPER + E", "File manager", { launch = "nautilus" })
o.bind("SUPER + N", "Notes (Obsidian)", { launch = "obsidian" })

-- TUI eye-candy / monitoring.
-- launch-or-focus-tui reuses an existing window instead of spawning duplicates.
o.bind("SUPER + M", "System monitor (btop)", "omarchy-launch-or-focus-tui --app-id=btop btop")
o.bind("SUPER + ALT + M", "Audio visualiser (cava)", "omarchy-launch-or-focus-tui --app-id=cava cava")
o.bind("SUPER + ALT + C", "Matrix", "omarchy-launch-or-focus-tui --app-id=cmatrix cmatrix -ab")
o.bind("SUPER + ALT + P", "Pipes", "omarchy-launch-or-focus-tui --app-id=pipes pipes.sh")
o.bind("SUPER + ALT + T", "TTY clock", "omarchy-launch-or-focus-tui --app-id=ttyclock tty-clock -c -C 7")

-- Screenshots go through ghost-capture, which runs Omarchy's own capture with
-- its five-second toast suppressed -- Sill shows a persistent, draggable
-- panel instead. See CUSTOMISATIONS.md §6e.
-- Omarchy already binds PRINT, and Hyprland keeps BOTH binds otherwise --
-- which would fire two captures. Drop theirs before adding ours.
hl.unbind("PRINT")
o.bind("PRINT", "Screenshot", "ghost-capture")

-- Sill panel (CUSTOMISATIONS.md §6e). SUPER+SHIFT+V verified free before
-- binding (hyprctl binds: modmask 65 + V unbound). Boolean settings that
-- affect binds are mirrored by Sill as flag files (existence = non-default
-- state) because a bind cannot read the TOML; Sill rewrites the flags and
-- runs `hyprctl reload` when ~/.config/ghost/settings.toml changes.
local function ghost_flag(name)
  local f = io.open((os.getenv("HOME") or "") .. "/.config/ghost/flags/" .. name)
  if f then
    f:close()
    return true
  end
  return false
end

if not ghost_flag("sill-no-toggle-bind") then -- sill.keybind_toggle = false
  o.bind("SUPER + SHIFT + V", "Sill panel", "sill toggle")
end

-- Wipe clipboard history (Sill + Omarchy share one store; pins survive).
o.bind("SUPER + SHIFT + Delete", "Purge clipboard history", "sill purge")

-- sill.disable_omarchy_clipboard: unbind SUPER+CTRL+V ONLY. Never unload the
-- Quickshell clipboard plugin -- it owns the wl-paste capture watchers that
-- feed Sill's own Clipboard tab (sill-plan §0/#3).
if ghost_flag("disable-omarchy-clipboard") then
  hl.unbind("SUPER + CTRL + V")
end

-- Luna, the assistant daemon (~/Work/luna). Voice in goes through voxtype's
-- `luna` profile, which pipes the transcript to lunad instead of typing it.
-- Plain dictation is deliberately untouched: F9 and SUPER+CTRL+X name no
-- profile, so they keep voxtype's default output mode and post-processing.
-- SUPER+ALT+L was verified free against `hyprctl binds` before binding.
o.bind("SUPER + ALT + L", "Talk to Luna", "voxtype record toggle --profile luna")

-- Ghost Settings TUI (CUSTOMISATIONS.md §9). SUPER+COMMA was bound by
-- Omarchy to "Dismiss last notification" -- deliberately traded for the
-- settings key (notifications keep SUPER+SHIFT+COMMA for dismiss-all).
hl.unbind("SUPER + COMMA")
o.bind("SUPER + COMMA", "Ghost settings",
       "omarchy-launch-or-focus-tui --app-id=ghost-settings ghost-settings")
