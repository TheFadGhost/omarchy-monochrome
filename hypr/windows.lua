-- Personal window rules.

-- Sill (dev.ghost.sill) — successor to the shelf: screenshots + pinned stash
-- (clipboard in Phase 2). Same xdg_toplevel-faking-an-overlay pattern, same
-- reasons (a layer surface cannot originate a drag; the bar stacks above all
-- toplevels so attachment below y=44 is faked). Fixed 560x720 transparent
-- canvas at the top-right; y = reserved-top (44) + 2. The app cuts a Wayland
-- input region to the visible chip/panel, so the empty canvas stays
-- click-through.
local sill = "^dev\\.ghost\\.sill$"

o.window(sill, {
  size = { "560", "720" },
  move = { "(monitor_w-560)", "46" },
})

o.window({ class = sill }, {
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
  rounding = 0,             -- the panel draws its own corners in CSS
  opacity = "1 1",
})
