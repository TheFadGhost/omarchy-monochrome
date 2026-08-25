import QtQuick
import Quickshell
import Quickshell.Io
import Quickshell.Wayland

// Scratchpad. Click the pill, type, it saves itself.
//
// Uses a layer-shell PanelWindow with WlrKeyboardFocus.OnDemand rather than a
// PopupWindow: xdg-popups only receive key events after focus routes through
// their parent surface, which makes them unreliable for anything you type into.
Item {
  id: root

  property var bar
  property string moduleName
  property var settings

  property bool open: false
  property string body: ""
  property bool loaded: false
  property bool dirty: false

  readonly property color fg: bar ? bar.foreground : "#dfe3e6"
  readonly property color bg: bar ? bar.background : "#0a0a0b"
  readonly property string mono: bar ? bar.fontFamily : "monospace"
  readonly property string storePath: (Quickshell.env("HOME") || "~") + "/.local/state/omarchy/scratchpad.txt"

  // Omarchy's bar README documents bar.shellQuote(), but Bar.qml does not
  // actually implement it -- calling it throws. Local POSIX single-quote
  // escaper instead.
  function sq(s) { return "'" + String(s).replace(/'/g, "'\\''") + "'" }
  function alpha(a) { return Qt.rgba(fg.r, fg.g, fg.b, a) }

  // Pill geometry must fit INSIDE the island plate, not the bar band.
  // The band is Style.bar.size-horizontal (44); ghost.barisland insets it by
  // 7px top and bottom, leaving ~30px of plate. Sizing off the band directly
  // makes the pill overflow the plate. Keep this in sync with Island.qml inset.
  readonly property int islandInset: 7
  readonly property int pillH: Math.max(14, (bar ? bar.barSize : 26) - (islandInset * 2) - 4)


  function save() {
    if (!bar || !bar.run || !loaded) return
    bar.run("mkdir -p " + sq(Quickshell.env("HOME") + "/.local/state/omarchy") +
            " && printf '%s' " + sq(root.body) + " > " + sq(root.storePath))
    dirty = false
  }

  implicitWidth: pill.implicitWidth
  implicitHeight: bar ? bar.barSize : 26

  FileView {
    id: store
    path: root.storePath
    printErrors: false
    onLoaded: { root.body = text(); root.loaded = true }
    onLoadFailed: { root.body = ""; root.loaded = true }
  }

  // Debounced write -- one save 900ms after you stop typing, not per keystroke.
  Timer {
    id: saveTimer
    interval: 900
    onTriggered: root.save()
  }

  Rectangle {
    id: pill
    anchors.centerIn: parent
    implicitWidth: inner.implicitWidth + 20
    implicitHeight: root.pillH
    radius: height / 2
    color: (hover.hovered || root.open) ? root.alpha(0.10) : "transparent"
    border.width: 1
    border.color: root.alpha((hover.hovered || root.open) ? 0.18 : 0.00)
    Behavior on color { ColorAnimation { duration: 160; easing.type: Easing.OutCubic } }
    Behavior on border.color { ColorAnimation { duration: 160 } }

    HoverHandler { id: hover }

    Row {
      id: inner
      anchors.centerIn: parent
      spacing: 6

      Rectangle {
        width: 5; height: 5; radius: 1
        anchors.verticalCenter: parent.verticalCenter
        color: root.fg
        opacity: root.body.length > 0 ? 0.75 : 0.3
        Behavior on opacity { NumberAnimation { duration: 200 } }
      }
      Text {
        anchors.verticalCenter: parent.verticalCenter
        text: "notes"
        color: root.fg
        opacity: root.open ? 1.0 : 0.55
        font.family: root.mono
        font.pixelSize: 11
        Behavior on opacity { NumberAnimation { duration: 200 } }
      }
    }

    MouseArea {
      anchors.fill: parent
      onClicked: root.open = !root.open
    }
  }

  // ---- editor surface ----
  PanelWindow {
    id: sheet
    visible: root.open
    color: "transparent"
    exclusionMode: ExclusionMode.Ignore
    WlrLayershell.layer: WlrLayer.Overlay
    WlrLayershell.keyboardFocus: root.open ? WlrKeyboardFocus.OnDemand : WlrKeyboardFocus.None
    anchors { top: true; left: true; right: true; bottom: true }

    // Click anywhere outside the card to dismiss.
    MouseArea {
      anchors.fill: parent
      onClicked: { root.save(); root.open = false }
    }

    Rectangle {
      id: card
      width: 380
      height: 260
      radius: 12
      color: root.bg
      border.width: 1
      border.color: root.alpha(0.18)

      x: {
        var p = root.mapToItem(null, 0, 0)
        return Math.round(Math.max(8, Math.min(sheet.width - width - 8, p.x + root.width / 2 - width / 2)))
      }
      y: (root.bar && root.bar.position === "bottom")
        ? sheet.height - height - (root.bar.barSize + 8)
        : (root.bar ? root.bar.barSize : 26) + 8

      opacity: root.open ? 1 : 0
      scale: root.open ? 1 : 0.96
      Behavior on opacity { NumberAnimation { duration: 140; easing.type: Easing.OutCubic } }
      Behavior on scale { NumberAnimation { duration: 180; easing.type: Easing.OutBack } }

      // Swallow clicks so they don't hit the dismiss layer underneath.
      MouseArea { anchors.fill: parent; onClicked: editor.forceActiveFocus() }

      Text {
        id: heading
        anchors.top: parent.top
        anchors.left: parent.left
        anchors.margins: 14
        text: "SCRATCHPAD"
        color: root.fg; opacity: 0.40
        font.family: root.mono; font.pixelSize: 9; font.letterSpacing: 1.2
      }

      Text {
        anchors.top: parent.top
        anchors.right: parent.right
        anchors.margins: 14
        text: root.dirty ? "saving" : "saved"
        color: root.fg
        opacity: root.dirty ? 0.55 : 0.25
        font.family: root.mono; font.pixelSize: 9
        Behavior on opacity { NumberAnimation { duration: 250 } }
      }

      Flickable {
        anchors.top: heading.bottom
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        anchors.margins: 14
        anchors.topMargin: 10
        contentWidth: width
        contentHeight: editor.implicitHeight
        clip: true

        TextEdit {
          id: editor
          width: parent.width
          text: root.body
          color: root.fg
          opacity: 0.92
          font.family: root.mono
          font.pixelSize: 12
          wrapMode: TextEdit.Wrap
          selectByMouse: true
          selectionColor: root.alpha(0.25)
          persistentSelection: true

          onTextChanged: {
            if (!root.loaded || text === root.body) return
            root.body = text
            root.dirty = true
            saveTimer.restart()
          }

          Text {
            anchors.fill: parent
            visible: editor.text.length === 0
            text: "jot something…"
            color: root.fg; opacity: 0.22
            font.family: root.mono; font.pixelSize: 12
          }
        }
      }

      Keys.onEscapePressed: { root.save(); root.open = false }
    }

    onVisibleChanged: if (visible) Qt.callLater(function() { editor.forceActiveFocus() })
  }
}
