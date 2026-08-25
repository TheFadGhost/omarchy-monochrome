import QtQuick
import Quickshell
import qs.Ui
import qs.Commons

// Focus timer. Click to pick a duration and lock in.
// Matches the sysmon pill so the two read as one system.
//
// Popup built on Omarchy's own PopupCard / PanelSectionHeader / PanelSeparator
// / Button instead of hand-rolled chrome -- see mediapill.qml and the battery
// panel (power/Panel.qml)'s power-profile row, which the duration pills copy.
Item {
  id: root

  property var bar
  property string moduleName
  property var settings

  property int remaining: 0
  property int sessionLength: 0
  property bool running: false
  property bool menuOpen: false
  property int completed: 0

  readonly property color fg: bar ? bar.barForeground : "#dfe3e6"
  readonly property color bg: bar ? bar.background : "#0a0a0b"
  readonly property string mono: bar ? bar.fontFamily : "monospace"
  readonly property real progress: sessionLength > 0 ? 1 - (remaining / sessionLength) : 0

  readonly property var choices: [
    { label: "15m", secs: 900 },
    { label: "25m", secs: 1500 },
    { label: "45m", secs: 2700 },
    { label: "60m", secs: 3600 },
    { label: "90m", secs: 5400 }
  ]

  // Omarchy's bar README documents bar.shellQuote(), but Bar.qml does not
  // actually implement it -- calling it throws. Local POSIX single-quote
  // escaper instead.
  function sq(s) { return "'" + String(s).replace(/'/g, "'\\''") + "'" }
  function alpha(a) { return Qt.rgba(fg.r, fg.g, fg.b, a) }
  function close() { menuOpen = false }

  // Pill geometry must fit INSIDE the island plate, not the bar band.
  // The band is Style.bar.size-horizontal (44); ghost.barisland insets it by
  // 7px top and bottom, leaving ~30px of plate. Sizing off the band directly
  // makes the pill overflow the plate. Keep this in sync with Island.qml inset.
  readonly property int islandInset: Style.space(7)
  readonly property int pillH: Math.max(14, (bar ? bar.barSize : 26) - (islandInset * 2) - 4)

  // Bar.qml's open-panel mark defaults to 55% of the slot, which on a wide pill
  // paints a long accent bar instead of a dot. Hint the extent it should use.
  readonly property real openPanelIndicatorWidth: Style.space(18)

  function pad(n) { return n < 10 ? "0" + n : "" + n }
  function clock(s) { return pad(Math.floor(s / 60)) + ":" + pad(s % 60) }

  function start(secs) {
    sessionLength = secs; remaining = secs; running = true; menuOpen = false
    if (bar && bar.run)
      bar.run("notify-send -a Focus 'Locked in' " + sq(clock(secs) + " of focus"))
  }
  function stop() { running = false; remaining = 0; sessionLength = 0; menuOpen = false }
  function finish() {
    running = false; remaining = 0; completed += 1
    if (bar && bar.run)
      bar.run("notify-send -u critical -a Focus 'Session complete' 'Take a break.'")
  }

  implicitWidth: pill.implicitWidth
  implicitHeight: bar ? bar.barSize : 26

  Timer {
    interval: 1000
    running: root.running
    repeat: true
    onTriggered: root.remaining > 1 ? root.remaining -= 1 : root.finish()
  }

  Rectangle {
    id: pill
    anchors.centerIn: parent
    implicitWidth: inner.implicitWidth + 22
    implicitHeight: root.pillH
    radius: height / 2
    clip: true
    color: (hover.hovered || root.menuOpen) ? root.alpha(0.10) : "transparent"
    border.width: 1
    border.color: root.alpha((hover.hovered || root.menuOpen) ? 0.18 : 0.00)

    Behavior on color { ColorAnimation { duration: 160; easing.type: Easing.OutCubic } }
    Behavior on border.color { ColorAnimation { duration: 160 } }

    HoverHandler { id: hover }

    // Progress fill sweeping across the pill as the session burns down.
    //
    // NOTE: clip:true on a rounded Rectangle clips to the BOUNDING BOX, not the
    // rounded corners -- a square-cornered child pokes out of the pill's ends.
    // So this carries its own matching radius instead of relying on the clip.
    Rectangle {
      visible: root.running
      anchors.left: parent.left
      anchors.verticalCenter: parent.verticalCenter
      height: parent.height
      width: Math.max(height, parent.width * root.progress)
      radius: height / 2
      color: root.alpha(0.10)
      Behavior on width { NumberAnimation { duration: 900; easing.type: Easing.Linear } }
    }

    Row {
      id: inner
      anchors.centerIn: parent
      spacing: 6

      // Pulsing dot while a session runs.
      Rectangle {
        width: 5; height: 5; radius: 2.5
        anchors.verticalCenter: parent.verticalCenter
        color: root.fg
        opacity: root.running ? 0.9 : 0.35
        SequentialAnimation on opacity {
          running: root.running
          loops: Animation.Infinite
          NumberAnimation { to: 0.30; duration: 1400; easing.type: Easing.InOutSine }
          NumberAnimation { to: 0.90; duration: 1400; easing.type: Easing.InOutSine }
        }
      }

      Text {
        anchors.verticalCenter: parent.verticalCenter
        text: root.running ? root.clock(root.remaining) : "focus"
        color: root.fg
        opacity: root.running ? 1.0 : 0.55
        font.family: root.mono
        font.pixelSize: Style.font.bodySmall
        font.bold: root.running && root.remaining <= 60
        Behavior on opacity { NumberAnimation { duration: 200 } }
      }

      // Completed-session tally.
      Text {
        anchors.verticalCenter: parent.verticalCenter
        visible: root.completed > 0
        text: "·" + root.completed
        color: root.fg
        opacity: 0.40
        font.family: root.mono
        font.pixelSize: Style.font.caption
      }
    }

    MouseArea {
      anchors.fill: parent
      acceptedButtons: Qt.LeftButton | Qt.RightButton
      onClicked: function(m) {
        if (m.button === Qt.RightButton) root.stop()
        else root.menuOpen = !root.menuOpen
      }
    }
  }

  // =====================================================================
  //  Control panel
  //
  //  Built on Omarchy's own PopupCard / PanelSectionHeader / PanelSeparator /
  //  Button instead of hand-rolled chrome. That buys Color.popups.*,
  //  Style.cornerRadius, the shared 140ms fade, focus-grab dismissal,
  //  bar-position-aware anchoring and the popout coordinator for free -- and
  //  means this panel re-themes with every other Omarchy popup rather than
  //  drifting away from them.
  // =====================================================================

  PopupCard {
    id: pop
    anchorItem: root
    bar: root.bar
    owner: root
    open: root.menuOpen
    contentWidth: pop.fittedContentWidth(Style.space(230))
    contentHeight: pop.fittedContentHeight(col.implicitHeight)

    Column {
      id: col
      anchors.fill: parent
      spacing: Style.space(14)

      PanelSectionHeader {
        text: root.running ? "IN SESSION" : "LOCK IN FOR"
        foreground: root.fg
      }

      // ---- duration pills ----
      // Mirrors the battery panel's power-profile row: one even-width Button
      // per choice, bordered, with the running length highlighted as active.
      Row {
        id: choiceRow
        width: parent.width
        spacing: Style.space(6)

        readonly property real cellWidth: root.choices.length > 0
          ? (width - spacing * (root.choices.length - 1)) / root.choices.length
          : 0

        Repeater {
          model: root.choices

          Button {
            required property var modelData
            width: choiceRow.cellWidth
            text: modelData.label
            fontSize: Style.font.bodySmall
            foreground: root.fg
            horizontalPadding: Style.spacing.controlPaddingX
            verticalPadding: Style.spacing.controlPaddingY
            bordered: true
            active: root.running && root.sessionLength === modelData.secs
            onClicked: root.start(modelData.secs)
          }
        }
      }

      PanelSeparator { foreground: root.fg; visible: root.running }

      Button {
        width: parent.width
        visible: root.running
        leftAlign: true
        text: "Stop"
        fontSize: Style.font.bodySmall
        foreground: root.fg
        onClicked: root.stop()
      }

      Text {
        width: parent.width
        visible: root.completed > 0
        text: root.completed + " done today"
        color: root.fg
        opacity: 0.45
        font.family: root.mono
        font.pixelSize: Style.font.caption
        horizontalAlignment: Text.AlignHCenter
      }
    }
  }
}
