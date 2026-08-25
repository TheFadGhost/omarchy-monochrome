-- Personal window rules.

-- Screenshot shelf (ghost-shotshelf).
--
-- This is a real xdg_toplevel rather than a layer-shell surface, because a
-- layer surface cannot originate a drag: wlroots validates a drag against the
-- seat's last pointer-button serial and requires the origin surface to hold
-- pointer focus. Made to behave like an overlay here instead. Same pattern as
-- Omarchy's own webcam-overlay.lua.
--
-- The window is a fixed 1000x300 transparent canvas with the card drawn at its
-- top-centre; the app sets a Wayland input region so the empty area stays
-- click-through. Keeping the window size constant means Hyprland never has to
-- reposition it as the card expands and collapses.
local shelf = "^dev\\.ghost\\.shotshelf$"

o.window(shelf, {
  size = { "1000", "300" },
  move = { "(monitor_w/2-500)", "52" },
})

o.window({ class = shelf }, {
  tag = "-default-opacity",
  float = true,
  pin = true,
  no_initial_focus = true,  -- never take focus away from what you were typing in
  no_follow_mouse = true,   -- ...and don't grab it on hover either
  no_anim = true,           -- the app animates its own expand/collapse
  no_dim = true,
  no_blur = true,
  no_shadow = true,
  border_size = 0,
  rounding = 0,             -- the card draws its own corners in CSS
  opacity = "1 1",
})
