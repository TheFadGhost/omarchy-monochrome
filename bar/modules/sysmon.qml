import QtQuick
import Quickshell
import Quickshell.Io
import qs.Ui
import qs.Commons

// Live CPU / GPU / RAM / temperature, with a CPU sparkline.
// Draws its own rounded pill so it reads as a floating module on the
// transparent bar. All colour comes from the bar, so it follows the theme.
//
// The detail pop-out is built on Omarchy's own PopupCard / PanelSectionHeader
// / PanelSeparator instead of hand-rolled chrome -- see mediapill.qml for the
// idiom this copies. That buys Color.popups.*, Style.cornerRadius, the
// shared 140ms fade, focus-grab dismissal, bar-position-aware anchoring and
// the popout coordinator for free, and means this panel re-themes with every
// other Omarchy popup instead of drifting away from them.
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
  readonly property color fg: bar ? bar.barForeground : "#dfe3e6"
  readonly property color bg: bar ? bar.background : "#0a0a0b"
  readonly property string mono: bar ? bar.fontFamily : "monospace"

  function close() { menuOpen = false }
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
            font.pixelSize: Style.font.caption
            font.letterSpacing: 0.5
            anchors.verticalCenter: parent.verticalCenter
          }
          Text {
            text: parent.modelData.v + "%"
            color: root.fg
            opacity: parent.modelData.v > 85 ? 1.0 : 0.88
            font.family: root.mono
            font.pixelSize: Style.font.bodySmall
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
        font.pixelSize: Style.font.caption
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

  // =====================================================================
  //  Detail pop-out
  //
  //  Mirrors the battery popup's structure: a hero row (stacked labels,
  //  big right-aligned number), a full-width usage bar, and a two-column
  //  key/value grid for the remaining figures.
  // =====================================================================

  PopupCard {
    id: pop
    anchorItem: root
    bar: root.bar
    owner: root
    open: root.menuOpen
    contentWidth: pop.fittedContentWidth(Style.space(300))
    contentHeight: pop.fittedContentHeight(col.implicitHeight)

    Column {
      id: col
      anchors.fill: parent
      spacing: Style.space(14)

      // ---------- Hero: stacked labels · big right-aligned CPU number ----------
      Item {
        width: parent.width
        implicitHeight: Math.max(heroLabels.implicitHeight, heroPercent.implicitHeight)

        Column {
          id: heroLabels
          anchors.left: parent.left
          anchors.right: heroPercent.left
          anchors.rightMargin: Style.space(10)
          anchors.verticalCenter: parent.verticalCenter
          spacing: Style.space(2)

          Text {
            text: "CPU"
            color: root.fg
            font.family: root.mono
            font.pixelSize: Style.font.title
            font.bold: true
            elide: Text.ElideRight
            width: parent.width
          }

          Text {
            text: ("load " + root.load).toUpperCase()
            color: Qt.darker(root.fg, 1.4)
            font.family: root.mono
            font.pixelSize: Style.font.caption
            font.bold: true
            font.letterSpacing: 1.2
            elide: Text.ElideRight
            width: parent.width
          }
        }

        Text {
          id: heroPercent
          text: root.cpu + "%"
          color: root.fg
          font.family: root.mono
          font.pixelSize: Style.font.displayLarge
          font.bold: true
          anchors.right: parent.right
          anchors.verticalCenter: parent.verticalCenter
        }
      }

      // ---------- CPU usage bar ----------
      Item {
        width: parent.width
        implicitHeight: Style.space(8)

        Rectangle {
          id: cpuTrack
          anchors.fill: parent
          radius: height / 2
          color: root.alpha(0.12)
        }

        Rectangle {
          anchors.left: cpuTrack.left
          anchors.verticalCenter: cpuTrack.verticalCenter
          height: cpuTrack.height
          radius: cpuTrack.radius
          color: root.fg
          width: Math.max(cpuTrack.height, cpuTrack.width * (root.cpu / 100))
          Behavior on width { NumberAnimation { duration: 320; easing.type: Easing.OutCubic } }
        }
      }

      // ---------- CPU sparkline ----------
      Row {
        id: sparkRow
        width: parent.width
        height: Style.space(24)
        spacing: Style.space(2)

        Repeater {
          model: root.histLen
          Rectangle {
            required property int index
            readonly property int val: index < root.cpuHistory.length ? root.cpuHistory[index] : 0
            width: (sparkRow.width - (root.histLen - 1) * sparkRow.spacing) / root.histLen
            radius: 1
            height: Math.max(1, Math.round((val / 100) * sparkRow.height))
            anchors.bottom: sparkRow.bottom
            color: root.fg
            opacity: 0.25 + (val / 100) * 0.55
            Behavior on height { NumberAnimation { duration: 450; easing.type: Easing.OutCubic } }
            Behavior on opacity { NumberAnimation { duration: 450 } }
          }
        }
      }

      PanelSeparator { foreground: root.fg }

      // ---------- Two-column key/value grid ----------
      Row {
        width: parent.width
        spacing: Style.space(20)

        Column {
          width: (parent.width - parent.spacing) / 2
          spacing: Style.spacing.labelGap
          InfoPair { label: "RAM"; value: root.mem + "%  " + root.memUsed + "/" + root.memTotal + " GiB" }
          InfoPair { label: "GPU"; value: root.gpu + "%" }
          InfoPair { label: "Load"; value: root.load }
        }

        Column {
          width: (parent.width - parent.spacing) / 2
          spacing: Style.spacing.labelGap
          InfoPair { label: "Swap"; value: root.swap + "%" }
          InfoPair { label: "Temp"; value: root.temp > 0 ? (root.temp + " °C") : "—" }
        }
      }

      // ---------- Top processes ----------
      PanelSeparator { foreground: root.fg }
      PanelSectionHeader { text: "TOP BY MEMORY"; foreground: root.fg; fontFamily: root.mono }

      Text {
        width: parent.width
        text: root.topProcs
        color: root.fg
        opacity: 0.7
        font.family: root.mono
        font.pixelSize: Style.font.bodySmall
        lineHeight: 1.3
        wrapMode: Text.NoWrap
        // Long process names otherwise run out under the card border.
        elide: Text.ElideRight
      }
    }
  }

  component InfoPair: Row {
    property string label: ""
    property string value: ""

    width: parent.width
    spacing: Style.space(8)

    InfoLabel { text: label }
    Item { width: Math.max(0, parent.width - parent.children[0].implicitWidth - parent.children[2].implicitWidth - parent.spacing * 2); height: 1 }
    InfoValue { text: value }
  }

  component InfoLabel: Text {
    color: root.fg
    opacity: 0.6
    font.family: root.mono
    font.pixelSize: Style.font.bodySmall
  }

  component InfoValue: Text {
    color: root.fg
    font.family: root.mono
    font.pixelSize: Style.font.bodySmall
  }
}
