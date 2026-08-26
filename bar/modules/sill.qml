import QtQuick
import Quickshell
import Quickshell.Io
import qs.Ui
import qs.Commons

// Sill toggle — an icon-only bar button that opens/closes the Sill shelf,
// plus the ONLY on-screen signal that a screenshot has landed.
//
// `ghost-capture` deliberately suppresses Omarchy's five-second screenshot
// toast, and Sill's floating chip is going away, so if this dot does not
// appear nothing tells you a capture happened. Treat it as load-bearing.
//
// Built on BarIconButton (not a hand-rolled pill) so it is byte-identical in
// slot width, optical glyph centring, tooltip and pointer-cursor behaviour to
// the first-party icons it sits beside — tray, agents, network, power. The
// user pill modules (notes, drawer) paint their own hover fill because they
// are pills; the icon buttons in this section do NOT, and neither does this.
BarWidget {
  id: root

  moduleName: "sill"

  // ---- pending screenshots -----------------------------------------------
  // Contract owned by the Sill side: a single ASCII integer, the number of
  // screenshots sitting in Sill undismissed. Missing or unparseable == 0.
  readonly property string stateDir: (Quickshell.env("HOME") || "~") + "/.local/state/ghost"
  readonly property string statePath: stateDir + "/sill-pending"

  property int pending: 0
  readonly property bool hasPending: pending > 0

  // GOTCHA (measured, not assumed): Quickshell's FileView arms its inotify
  // watch against the file's PARENT DIRECTORY. If that directory does not
  // exist when `path` is first assigned, the watch never arms and the file
  // appearing later is NEVER noticed — `onLoadFailed` fires once and the
  // module stays silently dead forever. `~/.local/state/ghost/` may well not
  // exist at shell start (Sill creates it on first capture), so the path is
  // withheld until a one-shot mkdir has returned. Once the directory exists,
  // the watch survives create, in-place write, atomic rename-replace
  // (repeatedly) and delete-then-recreate — all verified against a throwaway
  // quickshell instance, which is why this watches the single FILE and not
  // the directory.
  property bool watchArmed: false

  function parsePending(raw) {
    var n = parseInt(String(raw).trim(), 10)
    return isFinite(n) && n > 0 ? n : 0
  }

  implicitWidth: button.implicitWidth
  implicitHeight: button.implicitHeight

  Process {
    running: true
    command: ["mkdir", "-p", root.stateDir]
    onExited: root.watchArmed = true
  }

  FileView {
    id: pendingFile
    path: root.watchArmed ? root.statePath : ""
    watchChanges: true
    printErrors: false
    // `watchChanges` only SIGNALS the change; it does not re-read. Without an
    // explicit reload() the text stays at whatever was there when the view
    // first loaded, so the dot would arrive once and never move again.
    onFileChanged: reload()
    onLoaded: root.pending = root.parsePending(text())
    onLoadFailed: root.pending = 0
  }

  // ---- the button --------------------------------------------------------
  BarIconButton {
    id: button
    anchors.fill: parent
    bar: root.bar

    // nf-md-inbox (U+F0687) — a tray things land in, at the same solid weight
    // as the neighbouring icons and the same Material Design family (󰤨 wifi,
    // 󰂯 bluetooth, 󰍹 display). nf-md-tray, the obvious pick, is an outline
    // that renders as a thin bracket at Style.bar.iconFont and reads as nothing.
    text: "󰚇"
    tooltipText: "Sill"

    onPressed: function (mouseButton) {
      if (mouseButton !== Qt.LeftButton) return
      if (root.bar) root.bar.run("sill toggle")
    }

    // Pending badge. Sits on the top-right of the icon's optical canvas, not
    // of the 44px bar slot — anchoring to the slot would fling the dot up
    // against (and past) the island plate's inset edge.
    Item {
      anchors.centerIn: parent
      width: button.opticalSize
      height: button.opticalSize

      Rectangle {
        id: badge
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.rightMargin: -Style.spacing.hairline
        anchors.topMargin: Style.spacing.hairline
        width: Style.spacing.sm
        height: width
        radius: width / 2
        color: Color.accent
        opacity: root.hasPending ? 1 : 0
        visible: opacity > 0
        Behavior on opacity { NumberAnimation { duration: 160; easing.type: Easing.OutCubic } }
      }
    }
  }
}
