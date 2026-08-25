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
