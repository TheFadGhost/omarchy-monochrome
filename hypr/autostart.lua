-- ============================================================================
-- Extra autostart processes.
--
-- Deliberately minimal: this machine has 8 GB of RAM, and every autostarted
-- app is memory that never comes back. A terminal is near-free.
-- ============================================================================

-- A terminal, ready on the workspace you log in to (workspace 1).
o.launch_on_start("omarchy-launch-terminal")

-- Screenshot shelf. Idles at a few MB and only draws a window when there is a
-- screenshot to show, so it stays within the RAM budget noted above.
-- Supervised by systemd (sill.service) rather than launch_on_start: its
-- predecessor died once with nothing to restart it. See CUSTOMISATIONS.md §6e.
o.exec_on_start("systemctl --user start sill.service")
