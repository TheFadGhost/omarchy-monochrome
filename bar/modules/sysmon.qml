import QtQuick
import Quickshell
import Quickshell.Io
import Quickshell.Hyprland

// Live CPU / GPU / RAM / temperature, with a CPU sparkline.
// Draws its own rounded pill so it reads as a floating module on the
// transparent bar. All colour comes from the bar, so it follows the theme.
Item {
  id: root

  property var bar
  property string moduleName
  property var settings

  property int cpu: 0
  property int gpu: 0
  property int mem: 0
  property int temp: 0
  property string memUsed: "0"
  property string memTotal: "0"
  property int swap: 0
  property string load: "0"
  property string topProcs: ""
  property var cpuHistory: []
  property bool menuOpen: false

  readonly property int histLen: 22
  readonly property color fg: bar ? bar.foreground : "#dfe3e6"
  readonly property color bg: bar ? bar.background : "#0a0a0b"
  readonly property string mono: bar ? bar.fontFamily : "monospace"
  readonly property var myWindow: root.QsWindow ? root.QsWindow.window : null

  function alpha(a) { return Qt.rgba(fg.r, fg.g, fg.b, a) }

  // Pill geometry must fit INSIDE the island plate, not the bar band.
  // The band is Style.bar.size-horizontal (44); ghost.barisland insets it by
  // 7px top and bottom, leaving ~30px of plate. Sizing off the band directly
  // makes the pill overflow the plate. Keep this in sync with Island.qml inset.
  readonly property int islandInset: 7
  readonly property int pillH: Math.max(14, (bar ? bar.barSize : 26) - (islandInset * 2) - 4)


  implicitWidth: pill.implicitWidth
  implicitHeight: bar ? bar.barSize : 26

  Process {
    id: proc
    command: [Qt.resolvedUrl("../scripts/sysmon").toString().replace("file://", "")]
    stdout: StdioCollector {
      onStreamFinished: {
        try {
          var d = JSON.parse(text)
          root.cpu = d.cpu; root.gpu = d.gpu; root.mem = d.mem; root.temp = d.temp
          root.memUsed = d.memUsed; root.memTotal = d.memTotal
          root.swap = d.swap; root.load = d.load; root.topProcs = d.top

          var h = root.cpuHistory.slice()
          h.push(d.cpu)
          while (h.length > root.histLen) h.shift()
          root.cpuHistory = h
        } catch (e) { /* transient read; keep last good values */ }
      }
    }
  }

  Timer {
    interval: 3000
    running: true
    repeat: true
    triggeredOnStart: true
    onTriggered: if (!proc.running) proc.running = true
  }

  // ---- pill ----
  Rectangle {
    id: pill
    anchors.centerIn: parent
    implicitWidth: row.implicitWidth + 20
    implicitHeight: root.pillH
    radius: height / 2
    color: hover.hovered ? root.alpha(0.10) : "transparent"
    border.width: 1
    border.color: root.alpha(hover.hovered ? 0.18 : 0.00)

    Behavior on color { ColorAnimation { duration: 160; easing.type: Easing.OutCubic } }
    Behavior on border.color { ColorAnimation { duration: 160 } }

    HoverHandler { id: hover }

    Row {
      id: row
      anchors.centerIn: parent
      spacing: 9

      // CPU sparkline -- 22 samples, ~66s of history.
      Row {
        anchors.verticalCenter: parent.verticalCenter
        spacing: 1
        Repeater {
          model: root.histLen
          Rectangle {
            required property int index
            readonly property int val: index < root.cpuHistory.length ? root.cpuHistory[index] : 0
            width: 2
            radius: 1
            height: Math.max(1, Math.round((val / 100) * 12))
            y: 12 - height
            color: root.fg
            opacity: 0.25 + (val / 100) * 0.55
            Behavior on height { NumberAnimation { duration: 450; easing.type: Easing.OutCubic } }
            Behavior on opacity { NumberAnimation { duration: 450 } }
          }
        }
        height: 12
      }

      Repeater {
        model: [
          { k: "CPU", v: root.cpu },
          { k: "GPU", v: root.gpu },
          { k: "RAM", v: root.mem }
        ]
        Row {
          required property var modelData
          anchors.verticalCenter: parent.verticalCenter
          spacing: 3
          Text {
            text: parent.modelData.k
            color: root.fg
            opacity: 0.40
            font.family: root.mono
            font.pixelSize: 9
            font.letterSpacing: 0.5
            anchors.verticalCenter: parent.verticalCenter
          }
          Text {
            text: parent.modelData.v + "%"
            color: root.fg
            opacity: parent.modelData.v > 85 ? 1.0 : 0.88
            font.family: root.mono
            font.pixelSize: 11
            font.bold: parent.modelData.v > 85
            anchors.verticalCenter: parent.verticalCenter
            Behavior on opacity { NumberAnimation { duration: 250 } }
          }
        }
      }

      Text {
        text: root.temp + "°"
        color: root.fg
        opacity: root.temp > 80 ? 0.95 : 0.55
        font.family: root.mono
        font.pixelSize: 10
        anchors.verticalCenter: parent.verticalCenter
        visible: root.temp > 0
      }
    }

    MouseArea {
      anchors.fill: parent
      acceptedButtons: Qt.LeftButton | Qt.RightButton
      onClicked: function(m) {
        if (m.button === Qt.RightButton) {
          if (root.bar && root.bar.run) root.bar.run("omarchy-launch-or-focus-tui --app-id=btop btop")
        } else root.menuOpen = !root.menuOpen
      }
    }
  }

  // ---- detail pop-out ----
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
      implicitWidth: 240
      implicitHeight: col.implicitHeight + 22
      color: root.bg
      radius: 12
      border.width: 1
      border.color: root.alpha(0.18)

      opacity: root.menuOpen ? 1 : 0
      scale: root.menuOpen ? 1 : 0.96
      Behavior on opacity { NumberAnimation { duration: 130; easing.type: Easing.OutCubic } }
      Behavior on scale { NumberAnimation { duration: 160; easing.type: Easing.OutBack } }

      Column {
        id: col
        anchors.centerIn: parent
        width: parent.width - 24
        spacing: 5

        Text {
          text: "SYSTEM"
          color: root.fg; opacity: 0.40
          font.family: root.mono; font.pixelSize: 9; font.letterSpacing: 1.2
          bottomPadding: 4
        }

        Repeater {
          model: [
            { k: "CPU",  v: root.cpu + "%   load " + root.load, p: root.cpu },
            { k: "GPU",  v: root.gpu + "%", p: root.gpu },
            { k: "RAM",  v: root.mem + "%   " + root.memUsed + " / " + root.memTotal + " GiB", p: root.mem },
            { k: "Swap", v: root.swap + "%", p: root.swap },
            { k: "Temp", v: root.temp + " °C", p: Math.min(100, root.temp) }
          ]
          Item {
            required property var modelData
            width: col.width
            height: 26

            Text {
              anchors.left: parent.left
              y: 0
              text: parent.modelData.k
              color: root.fg; opacity: 0.45
              font.family: root.mono; font.pixelSize: 10
            }
            Text {
              anchors.right: parent.right
              y: 0
              text: parent.modelData.v
              color: root.fg; opacity: 0.9
              font.family: root.mono; font.pixelSize: 10
            }
            // usage rule
            Rectangle {
              anchors.bottom: parent.bottom
              anchors.bottomMargin: 5
              width: parent.width
              height: 2
              radius: 1
              color: root.alpha(0.08)
              Rectangle {
                width: parent.width * (Math.max(0, Math.min(100, parent.parent.modelData.p)) / 100)
                height: parent.height
                radius: 1
                color: root.fg
                opacity: 0.55
                Behavior on width { NumberAnimation { duration: 500; easing.type: Easing.OutCubic } }
              }
            }
          }
        }

        Text {
          text: "TOP BY MEMORY"
          color: root.fg; opacity: 0.40
          font.family: root.mono; font.pixelSize: 9; font.letterSpacing: 1.2
          topPadding: 6; bottomPadding: 2
        }
        Text {
          text: root.topProcs
          color: root.fg; opacity: 0.7
          font.family: root.mono; font.pixelSize: 10
          lineHeight: 1.3
        }
        Text {
          text: "click again to close  ·  right click: btop"
          color: root.fg; opacity: 0.30
          font.family: root.mono; font.pixelSize: 8
          topPadding: 8
        }
      }
    }
  }
}
