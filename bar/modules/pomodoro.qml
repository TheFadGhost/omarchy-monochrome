import QtQuick
import Quickshell
import Quickshell.Io
import Quickshell.Hyprland

// Focus timer. Click to pick a duration and lock in.
// Matches the sysmon pill so the two read as one system.
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

  readonly property color fg: bar ? bar.foreground : "#dfe3e6"
  readonly property color bg: bar ? bar.background : "#0a0a0b"
  readonly property string mono: bar ? bar.fontFamily : "monospace"
  readonly property var myWindow: root.QsWindow ? root.QsWindow.window : null
  readonly property real progress: sessionLength > 0 ? 1 - (remaining / sessionLength) : 0

  readonly property var choices: [
    { label: "15 min", secs: 900 },
    { label: "25 min", secs: 1500 },
    { label: "45 min", secs: 2700 },
    { label: "60 min", secs: 3600 },
    { label: "90 min", secs: 5400 }
  ]

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
        font.pixelSize: 11
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
        font.pixelSize: 9
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

  HyprlandFocusGrab {
    active: root.menuOpen
    windows: root.myWindow ? [pop, root.myWindow] : [pop]
    onCleared: root.menuOpen = false
  }

  PopupWindow {
    id: pop
    visible: root.menuOpen && root.myWindow !== null
    color: "transparent"
    implicitWidth: card.implicitWidth
    implicitHeight: card.implicitHeight

    anchor {
      window: root.myWindow
      adjustment: PopupAdjustment.Slide
      edges: Edges.Top | Edges.Left
      gravity: Edges.Bottom | Edges.Right
      rect.width: 1
      rect.height: 1
      onAnchoring: {
        var p = root.mapToItem(null, 0, 0)
        pop.anchor.rect.x = Math.round(p.x + root.width / 2 - pop.implicitWidth / 2)
        pop.anchor.rect.y = Math.round(p.y + root.height + 6)
      }
    }

    Rectangle {
      id: card
      implicitWidth: 168
      implicitHeight: col.implicitHeight + 20
      color: root.bg
      radius: 12
      border.width: 1
      border.color: root.alpha(0.18)

      opacity: root.menuOpen ? 1 : 0
      scale: root.menuOpen ? 1 : 0.95
      Behavior on opacity { NumberAnimation { duration: 130; easing.type: Easing.OutCubic } }
      Behavior on scale { NumberAnimation { duration: 170; easing.type: Easing.OutBack } }

      Column {
        id: col
        anchors.centerIn: parent
        width: parent.width - 18
        spacing: 1

        Text {
          text: root.running ? "IN SESSION" : "LOCK IN FOR"
          color: root.fg; opacity: 0.40
          font.family: root.mono; font.pixelSize: 9; font.letterSpacing: 1.2
          bottomPadding: 7
          anchors.horizontalCenter: parent.horizontalCenter
        }

        Repeater {
          model: root.choices
          Rectangle {
            required property var modelData
            width: col.width
            height: 27
            radius: 7
            color: ma.containsMouse ? root.alpha(0.12) : "transparent"
            Behavior on color { ColorAnimation { duration: 110 } }

            Text {
              anchors.verticalCenter: parent.verticalCenter
              anchors.left: parent.left
              anchors.leftMargin: ma.containsMouse ? 14 : 11
              text: parent.modelData.label
              color: root.fg
              opacity: ma.containsMouse ? 1.0 : 0.72
              font.family: root.mono
              font.pixelSize: 12
              Behavior on anchors.leftMargin { NumberAnimation { duration: 110; easing.type: Easing.OutCubic } }
              Behavior on opacity { NumberAnimation { duration: 110 } }
            }
            MouseArea {
              id: ma
              anchors.fill: parent
              hoverEnabled: true
              onClicked: root.start(parent.modelData.secs)
            }
          }
        }

        Rectangle {
          visible: root.running
          width: col.width
          height: 27
          radius: 7
          color: sma.containsMouse ? root.alpha(0.12) : "transparent"
          Behavior on color { ColorAnimation { duration: 110 } }
          Text {
            anchors.verticalCenter: parent.verticalCenter
            anchors.left: parent.left
            anchors.leftMargin: 11
            text: "stop"
            color: root.fg
            opacity: sma.containsMouse ? 1.0 : 0.45
            font.family: root.mono
            font.pixelSize: 12
          }
          MouseArea { id: sma; anchors.fill: parent; hoverEnabled: true; onClicked: root.stop() }
        }

        Text {
          visible: root.completed > 0
          text: root.completed + " done today"
          color: root.fg; opacity: 0.35
          font.family: root.mono; font.pixelSize: 9
          topPadding: 8
          anchors.horizontalCenter: parent.horizontalCenter
        }
      }
    }
  }
}
