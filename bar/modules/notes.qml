import QtQuick
import Quickshell
import Quickshell.Io
import Quickshell.Wayland
import qs.Ui
import qs.Commons

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

  readonly property color fg: bar ? bar.barForeground : "#dfe3e6"
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
  readonly property int islandInset: Style.space(7)
  readonly property int pillH: Math.max(14, (bar ? bar.barSize : 26) - (islandInset * 2) - 4)

  // Bar.qml's open-panel mark defaults to 55% of the slot, which on a wide pill
  // paints a long accent bar instead of a dot. Hint the extent it should use.
  readonly property real openPanelIndicatorWidth: Style.space(18)


  // PopupCard owns popout coordination for every other module; this one keeps
  // its layer-shell window (see the header note), so it registers by hand.
  function close() { save(); open = false }

  onOpenChanged: {
    if (open) Qt.callLater(sheet.relocate)
    if (!bar) return
    if (open) bar.requestPopout(root)
    else if (bar.activePopout === root) bar.releasePopout(root)
  }

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
        font.pixelSize: Style.font.bodySmall
        Behavior on opacity { NumberAnimation { duration: 200 } }
      }
    }

    MouseArea {
      anchors.fill: parent
      onClicked: { if (root.open) root.close(); else root.open = true }
    }
  }

  // ---- editor surface ----
  //
  // Stays a layer-shell PanelWindow on purpose (see the header note); only the
  // card inside it is built from the design system.
  PanelWindow {
    id: sheet
    // NOT `visible: root.open`: destroying the surface the instant `open` goes
    // false kills the card before its opacity/scale Behaviors can run, so the
    // close animation never plays. Same guard PopupCard.qml uses.
    visible: root.open || card.opacity > 0
    color: "transparent"
    exclusionMode: ExclusionMode.Ignore
    WlrLayershell.layer: WlrLayer.Overlay
    WlrLayershell.keyboardFocus: root.open ? WlrKeyboardFocus.OnDemand : WlrKeyboardFocus.None
    anchors { top: true; left: true; right: true; bottom: true }

    readonly property int margin: Style.gapsOut
    readonly property string barPos: root.bar ? root.bar.position : "top"
    readonly property real barPx: root.bar ? root.bar.barSize : 26

    // Re-map the pill into screen space. Called whenever anything that could
    // move it changes: the layer surface being configured to its real size,
    // the bar edge moving, the card resizing, or the sheet opening.
    function relocate() {
      var p = root.mapToItem(null, 0, 0)
      var ox = sheet.barPos === "right" ? sheet.width - sheet.barPx : 0
      var oy = sheet.barPos === "bottom" ? sheet.height - sheet.barPx : 0
      card.origin = Qt.point(p.x + ox, p.y + oy)
    }

    onWidthChanged: relocate()
    onHeightChanged: relocate()
    onBarPosChanged: relocate()
    onBarPxChanged: relocate()
    Component.onCompleted: Qt.callLater(relocate)

    // Click anywhere outside the card to dismiss.
    MouseArea {
      anchors.fill: parent
      onClicked: root.close()
    }

    BorderSurface {
      id: card
      width: Style.space(380)
      height: Style.space(260)
      radius: Style.cornerRadius
      color: Color.popups.background
      borderSpec: Border.localOrSurfaceSpec("popups", "border", Color.popups.border,
                                            Color.popups.border, Math.max(1, Style.space(2)))
      padding: Style.spacing.popupPadding

      // Four-edge placement, mirroring PopupCard.qml's onAnchoring. The pill's
      // position is mapped out of the BAR window, then shifted by that window's
      // own screen offset, because this sheet spans the whole screen.
      //
      // `origin` is a plain property refreshed by relocate(), NOT a binding:
      // mapToItem() is a function call, so a binding around it would capture no
      // dependencies and keep the very first (pre-layout) answer forever.
      property point origin: Qt.point(0, 0)

      x: {
        var localX = root.width / 2 - width / 2
        if (sheet.barPos === "left") localX = root.width + sheet.margin
        else if (sheet.barPos === "right") localX = -width - sheet.margin
        var v = origin.x + localX
        if (sheet.barPos === "top" || sheet.barPos === "bottom")
          v = Math.max(sheet.margin, Math.min(v, sheet.width - width - sheet.margin))
        return Math.round(v)
      }

      y: {
        var localY = root.height + sheet.margin
        if (sheet.barPos === "bottom") localY = -height - sheet.margin
        else if (sheet.barPos === "left" || sheet.barPos === "right")
          localY = root.height / 2 - height / 2
        var v = origin.y + localY
        if (sheet.barPos === "left" || sheet.barPos === "right")
          v = Math.max(sheet.margin, Math.min(v, sheet.height - height - sheet.margin))
        return Math.round(v)
      }

      onWidthChanged: sheet.relocate()
      onHeightChanged: sheet.relocate()

      opacity: root.open ? 1 : 0
      scale: root.open ? 1 : 0.96
      Behavior on opacity { NumberAnimation { duration: 140; easing.type: Easing.OutCubic } }
      Behavior on scale { NumberAnimation { duration: 180; easing.type: Easing.OutBack } }

      // Swallow clicks so they don't hit the dismiss layer underneath.
      MouseArea { anchors.fill: parent; onClicked: editor.forceActiveFocus() }

      Item {
        id: content
        anchors.fill: parent
        anchors.topMargin: card.contentTopInset
        anchors.rightMargin: card.contentRightInset
        anchors.bottomMargin: card.contentBottomInset
        anchors.leftMargin: card.contentLeftInset

        PanelSectionHeader {
          id: heading
          anchors.top: parent.top
          anchors.left: parent.left
          text: "SCRATCHPAD"
          foreground: root.fg
          fontFamily: root.mono
        }

        Text {
          anchors.top: parent.top
          anchors.right: parent.right
          text: root.dirty ? "saving" : "saved"
          color: Qt.darker(root.fg, 1.4)
          opacity: root.dirty ? 1.0 : 0.45
          font.family: root.mono
          font.pixelSize: Style.font.caption
          font.bold: true
          font.letterSpacing: 1.2
          Behavior on opacity { NumberAnimation { duration: 250 } }
        }

        Flickable {
          anchors.top: heading.bottom
          anchors.left: parent.left
          anchors.right: parent.right
          anchors.bottom: parent.bottom
          anchors.topMargin: Style.spacing.xl
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
            font.pixelSize: Style.font.body
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
              font.family: root.mono
              font.pixelSize: Style.font.body
            }
          }
        }
      }

      Keys.onEscapePressed: root.close()
    }

    onVisibleChanged: if (visible) Qt.callLater(function() { editor.forceActiveFocus() })
  }
}
