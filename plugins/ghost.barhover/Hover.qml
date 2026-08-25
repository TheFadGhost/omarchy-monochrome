import QtQuick
import Quickshell
import Quickshell.Io
import qs.Commons

// ghost.barhover -- tells Sill when the pointer is resting on the bar's
// EMPTY space (the gap between module sections), so Sill can hover-expand.
//
// WHY NOT AN OVERLAY SURFACE WITH A MouseArea (the obvious design):
// Wayland input regions are per-SURFACE. A separate PanelWindow above the
// bar would receive every pointer event inside its input region, and
// `acceptedButtons: Qt.NoButton` only re-routes clicks within the same
// scene -- across surfaces the click is simply consumed and lost. Bar.qml's
// CenterGestureArea (a MouseArea filling the ENTIRE bar background) owns
// left-press-drag = move-bar-to-another-edge and double-click = toggle
// transparency, on exactly the empty space such a surface would cover, so
// an overlay strip would silently break both gestures inside it. Verified
// against /usr/share/omarchy/shell/plugins/bar/Bar.qml (CenterGestureArea,
// `component ModuleSlot`'s modulePointer). Dead end -- do not resurrect.
//
// WHAT THIS DOES INSTEAD (no surface, no input taken, zero idle wakeups):
//  1. The shell host injects `shell` into service plugins; `shell.bar`
//     (the live Bar.qml root) exposes `barHovered` -- true while the
//     pointer is over any bar surface, maintained by the bar's own
//     HoverHandler. Binding to it costs nothing while the pointer is
//     elsewhere, which is ~all the time.
//  2. Only while barHovered (and no bar drag is in flight) a 100ms Timer
//     asks Hyprland's request socket for `/cursorpos` (~0.04ms per query
//     measured here, vs ~7ms for a hyprctl fork -- the reason polling
//     hyprctl was rejected).
//  3. The cursor is classified against the bar's real layout, read from
//     the live scene: ModuleList/ModuleSlot items carry `region`
//     ("left"/"center"/"right"), so the gaps BETWEEN sections -- the only
//     restable empty space -- are computed exactly, per screen.
//  4. Zone transitions are published to a state file that Sill watches
//     with Gio.FileMonitor.
//
// IPC: a state file, not a unix socket, on purpose. The file is state
// ("latest wins"), not an event stream: either side can restart in any
// order and the truth is still on disk (tmpfs -- no SSD writes); a socket
// needs a listener lifecycle, reconnect logic in both directions, and
// still has to answer "what was the state before I connected". inotify
// delivery is ~1ms, far under the >=100ms hover delays this gates, so the
// file pattern is not too slow -- matching the house pattern (FileView +
// file watches) used by the shell itself and by Sill's theme watcher.
//
// Applicability: hover-expand only makes sense while Sill's chip actually
// sits against the bar. This plugin reports which gap the pointer rests in
// plus the bar's edge; Sill (which knows `sill.position`) decides whether
// that gap is "near its chip". Vertical bars have no chip-adjacent gap
// semantics and report nothing.
Item {
  id: root

  // Injected by the shell host (shell.qml ensureService()).
  property var shell

  readonly property string runDir: Quickshell.env("XDG_RUNTIME_DIR")
  readonly property string ghostDir: runDir + "/ghost"
  readonly property string statePath: ghostDir + "/sill-hover.state"
  readonly property string hyprSocketPath:
    runDir + "/hypr/" + Quickshell.env("HYPRLAND_INSTANCE_SIGNATURE")
      + "/.socket.sock"

  readonly property var barObj: shell ? shell.bar : null

  // Sample only while the bar itself says the pointer is on it, never
  // during the bar's own drag gestures (reorder or move-bar), never while
  // the bar is hide-parked off screen, and only for horizontal bars.
  readonly property bool sampling: {
    var b = root.barObj
    if (!b) return false
    if (b.barHidden || b.vertical) return false
    if (b.barDragSource || b.barMoveActive) return false
    return b.barHovered === true
  }

  // A gap narrower than this is not a restable target (and guards against
  // a mis-read layout collapsing the gap to a sliver). Font-scaled, like
  // every size on this machine (CUSTOMISATIONS.md section 6d).
  readonly property real minGap: Style.space(48)
  // Keep a small dead margin so grazing a module's edge doesn't count.
  readonly property real edgePad: Style.space(4)

  property string zone: "none"          // none | left-gap | right-gap
  property string zoneMonitor: ""

  onSamplingChanged: if (!sampling) setZone("none", "")

  function setZone(z, mon) {
    if (z === zone && mon === zoneMonitor) return
    zone = z
    zoneMonitor = mon
    publish()
  }

  function publish() {
    var b = root.barObj
    stateFile.setText(JSON.stringify({
      zone: zone,
      bar: b ? String(b.position) : "",
      monitor: zoneMonitor,
      t: Date.now()
    }) + "\n")
  }

  // ---- bar scene readout -------------------------------------------------
  // The bar's per-screen windows live in a Variants inside Bar.qml. The
  // ghost overlays (drag ghost, move ghost) are also Variants of windows;
  // they declare `ghostScreen`, the real BarPanel does not. Read-only
  // traversal; if an omarchy update changes the internals every lookup
  // fails soft and hover-expand silently stops (click/keybind still work).
  function barWindows() {
    var out = []
    var b = root.barObj
    if (!b || !b.data) return out
    for (var i = 0; i < b.data.length; i++) {
      var v = b.data[i]
      if (!v || v.instances === undefined) continue
      for (var j = 0; j < v.instances.length; j++) {
        var w = v.instances[j]
        if (w && w.contentItem && w.screen && w.ghostScreen === undefined)
          out.push(w)
      }
    }
    return out
  }

  // Visible items that declare a bar section: ModuleList (region+entries)
  // and ModuleSlot (region+entry). `visible` is effective visibility, so
  // the center section's hidden alternate arrangement is skipped.
  function collectRegionItems(node, out, depth) {
    if (!node || depth > 12) return
    var kids = node.children
    if (!kids) return
    for (var i = 0; i < kids.length; i++) {
      var c = kids[i]
      if (!c) continue
      if (c.visible === true && typeof c.region === "string"
          && (c.entries !== undefined || c.entry !== undefined)
          && c.width > 0)
        out.push(c)
      collectRegionItems(c, out, depth + 1)
    }
  }

  function gapAt(w, lx) {
    var items = []
    collectRegionItems(w.contentItem, items, 0)
    var leftEnd = -1
    var rightStart = Number.MAX_VALUE
    var centerStart = Number.MAX_VALUE
    var centerEnd = -1
    for (var i = 0; i < items.length; i++) {
      var it = items[i]
      var p = it.mapToItem(w.contentItem, 0, 0)
      if (it.region === "left") leftEnd = Math.max(leftEnd, p.x + it.width)
      else if (it.region === "right") rightStart = Math.min(rightStart, p.x)
      else if (it.region === "center") {
        centerStart = Math.min(centerStart, p.x)
        centerEnd = Math.max(centerEnd, p.x + it.width)
      }
    }
    // right-gap: between the center section's end (or the left section's
    // end when there is no center) and the right section's start.
    var rEdge = centerEnd > -1 ? centerEnd : leftEnd
    if (rightStart < Number.MAX_VALUE && rEdge > -1
        && rightStart - rEdge >= root.minGap
        && lx >= rEdge + root.edgePad && lx <= rightStart - root.edgePad)
      return "right-gap"
    var lEdge = centerStart < Number.MAX_VALUE ? centerStart : rightStart
    if (leftEnd > -1 && lEdge < Number.MAX_VALUE
        && lEdge - leftEnd >= root.minGap
        && lx >= leftEnd + root.edgePad && lx <= lEdge - root.edgePad)
      return "left-gap"
    return "none"
  }

  function classify(gx, gy) {
    var b = root.barObj
    if (!b) { setZone("none", ""); return }
    var wins = barWindows()
    for (var i = 0; i < wins.length; i++) {
      var w = wins[i]
      var scr = w.screen
      if (!scr) continue
      var bandTop = b.position === "bottom"
        ? scr.y + scr.height - b.barSize : scr.y
      if (gy < bandTop || gy > bandTop + b.barSize) continue
      var z = gapAt(w, gx - scr.x)
      setZone(z, z === "none" ? "" : String(scr.name || ""))
      return
    }
    setZone("none", "")
  }

  // ---- cursor sampling ---------------------------------------------------
  Timer {
    interval: 100
    repeat: true
    running: root.sampling
    triggeredOnStart: true
    onTriggered: {
      if (cursorSock.connected) return    // previous query still in flight
      cursorSock.pending = ""
      cursorSock.connected = true
    }
  }

  // Hyprland request socket (socket1): write the command, read one reply,
  // the server closes. Reply format measured live: "1436, 817".
  Socket {
    id: cursorSock
    path: root.hyprSocketPath
    property string pending: ""
    parser: SplitParser {
      splitMarker: ""    // deliver chunks as they arrive
      onRead: function (chunk) {
        cursorSock.pending += chunk
        var m = /^\s*(-?\d+)\s*,\s*(-?\d+)/.exec(cursorSock.pending)
        if (m) {
          root.classify(parseInt(m[1], 10), parseInt(m[2], 10))
          cursorSock.pending = ""
          cursorSock.connected = false
        }
      }
    }
    onConnectionStateChanged: {
      if (connected) { write("/cursorpos"); flush() }
    }
  }

  // ---- publishing --------------------------------------------------------
  FileView {
    id: stateFile
    path: root.statePath
    printErrors: false
    atomicWrites: true    // pairs with Sill's Gio WATCH_MOVES monitor
  }

  // Sill's pidfile normally creates the directory first, but don't depend
  // on start order.
  Process {
    running: true
    command: ["mkdir", "-p", root.ghostDir]
  }

  // Reset whatever a previous shell instance left behind ("in" written,
  // then crashed). Delayed so the mkdir above has landed.
  Timer {
    interval: 1500
    running: true
    onTriggered: root.publish()
  }
}
