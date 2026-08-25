import QtQuick
import Quickshell
import Quickshell.Io
import Quickshell.Wayland
import qs.Ui
import qs.Commons

// Screenshot shelf.
//
// Omarchy's own screenshot toast is a 5s notification: by the time you decide
// to do something with the shot, it is gone. This replaces that with a shelf
// that stays until dismissed and collapses to a chip instead of vanishing.
//
// WHY THE CLIPBOARD AND NOT A DRAG. Two routes were tried and both are dead
// ends on this machine:
//
//   1. Real drag-out. QtQuick's `Drag` is scene-local only -- its DragType
//      enum is None/Automatic/Internal, there is no External -- and Quickshell
//      registers no DnD types at all (`grep -ir drag` over its qmltypes
//      returns nothing). Genuine cross-app drag needs C++ calling
//      QDrag::exec() on an xdg_toplevel; a layer-shell surface driven from a
//      QML-only config cannot reach it.
//
//   2. Synthesising the paste. `wtype` exits 0 here but delivers nothing --
//      verified by typing into a focused throwaway foot window and screen-
//      grabbing it: the terminal stayed empty. Hyprland 0.56 does expose a
//      `hl.dsp.send_shortcut` dispatcher, but its Lua table signature rejects
//      {mods=,key=} with "key not found" and the correct field name is not
//      documented. Not worth shipping on a guess.
//
// So the clipboard does the work -- which IS verified: wl-copy/wl-paste
// round-trips cleanly. Copy the path, then Ctrl+Shift+V wherever you need it.
//
// Detection is inotify on the screenshot directory rather than a wrapper
// around the capture script, so every capture route is covered: the PRINT
// key, the region picker, and the Omarchy menu alike.
Item {
  id: root

  readonly property string home: Quickshell.env("HOME") || ""
  readonly property string dir: (Quickshell.env("OMARCHY_SCREENSHOT_DIR") || (home + "/Pictures"))
  readonly property string editor: Quickshell.env("OMARCHY_SCREENSHOT_EDITOR") || "tensaku-edit"

  // Newest first. Capped so a screenshotting spree cannot grow the strip
  // without bound.
  property var shots: []
  property int selected: 0
  property bool expanded: false
  readonly property int maxShots: 6

  readonly property string current: (selected >= 0 && selected < shots.length) ? shots[selected] : ""
  readonly property bool active: shots.length > 0

  readonly property color fg: Color.popups.text
  readonly property string mono: Style.font.family
  readonly property var borderSpec: Border.localOrSurfaceSpec(
    "popups", "border", Color.popups.border, Color.popups.border, Math.max(1, Style.space(2)))

  // Style.bar.sizeHorizontal follows the [bar] size-horizontal override in
  // ~/.config/omarchy/shell.toml, so a taller bar pushes the shelf down with it.
  readonly property int barClearance: Style.bar.sizeHorizontal + Style.space(8)

  function alpha(a) { return Qt.rgba(fg.r, fg.g, fg.b, a) }
  function sq(s) { return "'" + String(s).replace(/'/g, "'\\''") + "'" }

  function basename(p) {
    var s = String(p || "")
    var i = s.lastIndexOf("/")
    return i < 0 ? s : s.slice(i + 1)
  }

  // screenshot-2026-08-25_02-06-08.png -> "02:06:08"
  function stamp(p) {
    var m = /_(\d{2})-(\d{2})-(\d{2})\.png$/.exec(basename(p))
    return m ? (m[1] + ":" + m[2] + ":" + m[3]) : ""
  }

  function add(path) {
    if (!/screenshot-.*\.png$/.test(path)) return
    var next = shots.slice()
    var existing = next.indexOf(path)
    if (existing >= 0) next.splice(existing, 1)
    next.unshift(path)
    while (next.length > maxShots) next.pop()
    shots = next
    selected = 0
    expanded = true
    collapseTimer.restart()
  }

  function drop(index) {
    var next = shots.slice()
    next.splice(index, 1)
    shots = next
    if (selected >= shots.length) selected = Math.max(0, shots.length - 1)
    if (shots.length === 0) expanded = false
  }

  function clearAll() {
    shots = []
    selected = 0
    expanded = false
  }

  // ---- actions ----
  function copyPath() {
    if (!current) return
    Util.execDetached("printf %s " + sq(current) + " | wl-copy")
    collapseTimer.restart()
  }

  function copyImage() {
    if (!current) return
    Util.execDetached("wl-copy --type image/png < " + sq(current))
    collapseTimer.restart()
  }

  function openEditor() {
    if (!current) return
    Util.execDetached(sq(editor) + " " + sq(current))
  }

  // ---- detection ----
  // -m keeps it running, close_write fires once the file is fully written
  // (unlike `create`, which would race grim's own write), moved_to catches
  // tools that write to a temp file and rename into place.
  Process {
    id: watcher
    running: true
    command: ["inotifywait", "-m", "-q", "-e", "close_write", "-e", "moved_to", "--format", "%w%f", root.dir]
    stdout: SplitParser {
      splitMarker: "\n"
      onRead: function (line) {
        var p = String(line).trim()
        if (p) root.add(p)
      }
    }
  }

  // inotifywait dying (directory removed and recreated, OOM kill) would
  // silently stop the whole feature, so bring it back.
  Timer {
    interval: 5000
    repeat: true
    running: true
    onTriggered: if (!watcher.running) watcher.running = true
  }

  Timer {
    id: collapseTimer
    interval: 6000
    onTriggered: root.expanded = false
  }

  Variants {
    model: Quickshell.screens

    PanelWindow {
      id: win
      required property var modelData
      screen: modelData

      visible: root.active
      color: "transparent"
      exclusionMode: ExclusionMode.Ignore
      WlrLayershell.namespace: "ghost-shotshelf"
      WlrLayershell.layer: WlrLayer.Overlay
      WlrLayershell.keyboardFocus: WlrKeyboardFocus.None

      anchors { top: true; left: true; right: true }
      implicitHeight: root.barClearance + Style.space(240)

      // Everything outside the card stays click-through, so the shelf never
      // eats a click meant for the window underneath it.
      mask: Region { item: shell }

      Item {
        id: shell
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.top: parent.top
        // Clear the bar. The window is an Overlay layer anchored to the screen
        // top, so without this the card renders on top of the bar itself.
        anchors.topMargin: root.barClearance
        // Deliberately NOT animated: this Item is the window's input mask, and
        // animating it re-sends a Wayland input region every frame. The
        // expand/collapse motion lives on the card and chip instead.
        implicitWidth: root.expanded ? card.implicitWidth : chip.implicitWidth
        implicitHeight: root.expanded ? card.implicitHeight : chip.implicitHeight

        // ---------------- collapsed chip ----------------
        BorderSurface {
          id: chip
          anchors.centerIn: parent
          implicitWidth: chipRow.implicitWidth + Style.space(20)
          implicitHeight: Style.space(34)
          radius: Style.cornerRadius
          color: Color.popups.background
          borderSpec: root.borderSpec

          visible: opacity > 0
          opacity: root.expanded ? 0 : 1
          scale: root.expanded ? 0.96 : 1
          Behavior on opacity { NumberAnimation { duration: 140; easing.type: Easing.OutCubic } }
          Behavior on scale { NumberAnimation { duration: 160; easing.type: Easing.OutBack } }

          Row {
            id: chipRow
            anchors.centerIn: parent
            spacing: Style.space(8)

            Rectangle {
              width: Style.space(30)
              height: Style.space(18)
              radius: Style.space(3)
              anchors.verticalCenter: parent.verticalCenter
              color: root.alpha(0.10)
              clip: true

              Image {
                anchors.fill: parent
                source: root.current ? "file://" + root.current : ""
                fillMode: Image.PreserveAspectCrop
                sourceSize.width: 160
                asynchronous: true
              }
            }

            Text {
              anchors.verticalCenter: parent.verticalCenter
              text: root.shots.length > 1 ? ("Screenshots · " + root.shots.length) : "Screenshot"
              color: root.fg
              opacity: 0.75
              font.family: root.mono
              font.pixelSize: Style.font.bodySmall
            }
          }

          MouseArea {
            anchors.fill: parent
            acceptedButtons: Qt.LeftButton | Qt.RightButton
            cursorShape: Qt.PointingHandCursor
            onClicked: function (mouse) {
              if (mouse.button === Qt.RightButton) root.clearAll()
              else { root.expanded = true; collapseTimer.restart() }
            }
          }
        }

        // ---------------- expanded card ----------------
        BorderSurface {
          id: card
          anchors.centerIn: parent
          implicitWidth: Style.space(430)
          implicitHeight: body.implicitHeight + Style.spacing.popupPadding * 2
          radius: Style.cornerRadius
          color: Color.popups.background
          borderSpec: root.borderSpec

          visible: opacity > 0
          opacity: root.expanded ? 1 : 0
          scale: root.expanded ? 1 : 0.96
          Behavior on opacity { NumberAnimation { duration: 140; easing.type: Easing.OutCubic } }
          Behavior on scale { NumberAnimation { duration: 160; easing.type: Easing.OutBack } }

          // Hovering the card should not have it collapse out from under the
          // cursor mid-reach.
          HoverHandler {
            id: cardHover
            onHoveredChanged: {
              if (hovered) collapseTimer.stop()
              else if (root.expanded) collapseTimer.restart()
            }
          }

          Column {
            id: body
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.top: parent.top
            anchors.margins: Style.spacing.popupPadding
            spacing: Style.space(12)

            // header
            Item {
              width: parent.width
              implicitHeight: heading.implicitHeight

              PanelSectionHeader {
                id: heading
                anchors.left: parent.left
                text: "SCREENSHOT"
                foreground: root.fg
              }

              Text {
                anchors.right: closeBtn.left
                anchors.rightMargin: Style.space(8)
                anchors.verticalCenter: heading.verticalCenter
                text: root.stamp(root.current)
                color: Qt.darker(root.fg, 1.4)
                font.family: root.mono
                font.pixelSize: Style.font.caption
              }

              Text {
                id: closeBtn
                anchors.right: parent.right
                anchors.verticalCenter: heading.verticalCenter
                text: "✕"
                color: root.fg
                opacity: closeHover.hovered ? 1.0 : 0.45
                font.family: root.mono
                font.pixelSize: Style.font.bodySmall
                Behavior on opacity { NumberAnimation { duration: 130 } }

                HoverHandler { id: closeHover }
                MouseArea {
                  anchors.fill: parent
                  anchors.margins: -Style.space(6)
                  cursorShape: Qt.PointingHandCursor
                  onClicked: root.clearAll()
                }
              }
            }

            // preview + filename
            Row {
              width: parent.width
              spacing: Style.space(12)

              Rectangle {
                id: preview
                width: Style.space(150)
                height: Math.round(width * 9 / 16)
                radius: Style.space(6)
                color: root.alpha(0.08)
                clip: true

                Image {
                  anchors.fill: parent
                  anchors.margins: 1
                  source: root.current ? "file://" + root.current : ""
                  fillMode: Image.PreserveAspectFit
                  sourceSize.width: 600
                  asynchronous: true
                  cache: false
                }
              }

              Column {
                width: parent.width - preview.width - Style.space(12)
                anchors.verticalCenter: parent.verticalCenter
                spacing: Style.space(4)

                Text {
                  width: parent.width
                  text: root.basename(root.current)
                  color: root.fg
                  font.family: root.mono
                  font.pixelSize: Style.font.bodySmall
                  elide: Text.ElideMiddle
                }

                Text {
                  width: parent.width
                  text: "Ctrl+Shift+V pastes. The image itself is already on the clipboard."
                  color: root.fg
                  opacity: 0.55
                  font.family: root.mono
                  font.pixelSize: Style.font.caption
                  wrapMode: Text.WordWrap
                }
              }
            }

            // actions
            Flow {
              width: parent.width
              spacing: Style.space(6)

              Button {
                iconText: "󰅍"
                text: "Copy path"
                foreground: root.fg
                bordered: true
                fontSize: Style.font.bodySmall
                iconSize: Style.font.iconSmall
                onClicked: root.copyPath()
              }
              Button {
                iconText: "󰋩"
                text: "Copy image"
                foreground: root.fg
                bordered: true
                fontSize: Style.font.bodySmall
                iconSize: Style.font.iconSmall
                onClicked: root.copyImage()
              }
              Button {
                iconText: "󰏫"
                text: "Edit"
                foreground: root.fg
                bordered: true
                fontSize: Style.font.bodySmall
                iconSize: Style.font.iconSmall
                onClicked: root.openEditor()
              }
            }

            // recent strip
            Row {
              width: parent.width
              spacing: Style.space(6)
              visible: root.shots.length > 1

              Repeater {
                model: root.shots

                Rectangle {
                  id: thumb
                  required property var modelData
                  required property int index

                  width: Style.space(52)
                  height: Style.space(30)
                  radius: Style.space(4)
                  color: index === root.selected
                    ? Style.selectedFillFor(root.fg, Color.accent)
                    : root.alpha(0.06)
                  border.width: 1
                  border.color: index === root.selected ? root.alpha(0.35) : "transparent"
                  clip: true
                  Behavior on color { ColorAnimation { duration: 130 } }

                  Image {
                    anchors.fill: parent
                    anchors.margins: 2
                    source: "file://" + thumb.modelData
                    fillMode: Image.PreserveAspectCrop
                    sourceSize.width: 200
                    asynchronous: true
                  }

                  MouseArea {
                    anchors.fill: parent
                    acceptedButtons: Qt.LeftButton | Qt.RightButton
                    cursorShape: Qt.PointingHandCursor
                    onClicked: function (mouse) {
                      if (mouse.button === Qt.RightButton) root.drop(thumb.index)
                      else root.selected = thumb.index
                      collapseTimer.restart()
                    }
                  }
                }
              }
            }
          }
        }
      }
    }
  }
}
