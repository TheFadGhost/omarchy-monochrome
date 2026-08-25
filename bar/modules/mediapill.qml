import QtQuick
import QtQuick.Effects
import Quickshell
import Quickshell.Services.Mpris
import qs.Ui
import qs.Commons

// Now-playing pill with a hover state and a click-through control panel.
//
// Replaces the first-party `omarchy.media` widget.
//
//   idle    animated equaliser glyph + elided track label over a hairline
//   hover   pill fills in, transport slides out of the right edge, label marquees
//   click   panel with artwork, scrubbable timeline, volume, shuffle/repeat
//           and a source switcher
//
// All colour comes from `bar.foreground` / `bar.background`, so it re-tints
// itself whenever the Omarchy theme changes -- nothing is hardcoded except the
// no-bar fallbacks. Artwork is desaturated to stay inside the greyscale rice
// and only returns to full colour while the cursor is on it.
//
// Playback goes through the first-party media service so the OSD and player
// preference logic stay shared with the rest of the shell. `activePlayer` is a
// raw Quickshell MprisPlayer, which is where position, length, volume, shuffle
// and loop come from -- the Omarchy service implements none of those itself.
Item {
  id: root

  property var bar
  property string moduleName
  property var settings

  readonly property var mediaService: (bar && bar.shell && bar.shell.firstPartyServiceFor)
    ? bar.shell.firstPartyServiceFor("omarchy.media")
    : null
  readonly property var player: mediaService ? mediaService.activePlayer : null
  readonly property var sources: (mediaService && mediaService.sourcePlayers)
    ? mediaService.sourcePlayers : []

  readonly property string title: player && player.trackTitle ? player.trackTitle : ""
  readonly property string artist: player && player.trackArtist ? player.trackArtist : ""
  readonly property string album: player && player.trackAlbum ? player.trackAlbum : ""
  readonly property string artUrl: player && player.trackArtUrl ? player.trackArtUrl : ""
  readonly property bool playing: player ? !!player.isPlaying : false
  readonly property bool hasMedia: !!player && (title !== "" || artist !== "")

  property bool hovered: false
  property bool menuOpen: true
  readonly property bool expanded: (hovered || menuOpen) && hasMedia

  readonly property color fg: bar ? bar.foreground : "#dfe3e6"
  readonly property color bg: bar ? bar.background : "#0a0a0b"
  readonly property string mono: bar ? bar.fontFamily : "monospace"
  readonly property var myWindow: root.QsWindow ? root.QsWindow.window : null

  function close() { menuOpen = false }
  function alpha(a) { return Qt.rgba(fg.r, fg.g, fg.b, a) }
  function clamp01(v) { return Math.max(0, Math.min(1, v)) }

  function sourceLabel(p) {
    if (!p) return "Player"
    var name = p.identity || p.desktopEntry || "Player"
    var track = p.trackTitle || ""
    if (!track) return name
    var room = 34 - name.length
    if (room < 6) return name
    if (track.length > room) track = track.slice(0, room - 1).trim() + "…"
    return name + "  ·  " + track
  }

  // Pill geometry must fit INSIDE the island plate, not the bar band.
  // The band is Style.bar.size-horizontal (44); ghost.barisland insets it by
  // 7px top and bottom, leaving ~30px of plate. Sizing off the band directly
  // makes the pill overflow the plate. Keep this in sync with Island.qml inset.
  readonly property int islandInset: 7
  readonly property int pillH: Math.max(14, (bar ? bar.barSize : 26) - (islandInset * 2) - 4)

  readonly property int labelWidth: expanded ? 130 : 168

  // ---- playback position ----
  // Quickshell refreshes MprisPlayer.position only when positionChanged() is
  // emitted, so it has to be pumped on a timer. Guarded because a player that
  // does not implement the Position property throws on the call.
  property real posSec: 0
  readonly property real lenSec: (player && player.length > 0) ? player.length : 0
  readonly property real progress: lenSec > 0 ? clamp01(posSec / lenSec) : 0
  readonly property bool seekable: !!player && lenSec > 0
    && (player.canSeek === undefined || !!player.canSeek)

  function fmt(s) {
    if (!s || s < 0 || !isFinite(s)) return "0:00"
    var t = Math.floor(s)
    var m = Math.floor(t / 60)
    var r = t % 60
    return m + ":" + (r < 10 ? "0" : "") + r
  }

  // Prefer the in-process service so the OSD and player-preference bookkeeping
  // run; fall back to the shell's `media` IPC target if it is not reachable.
  function act(name) {
    if (mediaService && mediaService.runAction) {
      mediaService.runAction(name, false)
      return
    }
    if (bar && bar.run) bar.run("omarchy-shell media " + name)
  }

  function seekSeconds(sec) {
    if (!seekable) return
    seekTo(sec / Math.max(1, lenSec))
  }

  function seekTo(fraction) {
    if (!seekable) return
    var target = clamp01(fraction) * lenSec
    try { player.position = target } catch (e) {}
    posSec = target
  }

  Timer {
    interval: 1000
    repeat: true
    running: root.hasMedia
    triggeredOnStart: true
    onTriggered: {
      var p = root.player
      if (!p) { root.posSec = 0; return }
      try { p.positionChanged() } catch (e) {}
      root.posSec = p.position || 0
    }
  }

  onPlayerChanged: posSec = 0

  Timer {
    id: emptyGrace
    interval: 3000
    running: root.menuOpen && !root.hasMedia
    onTriggered: root.menuOpen = false
  }

  // ---- shared icon button ----
  // Used by both the pill's inline transport and the panel, so the two never
  // drift apart visually.
  component IconButton: Rectangle {
    id: ib
    property string glyph: ""
    property int glyphSize: Style.font.body
    property int diameter: 20
    property bool allowed: true
    property bool active: false
    signal activated

    width: diameter
    height: diameter
    radius: diameter / 2
    color: ibHover.hovered && allowed ? root.alpha(0.14) : "transparent"
    Behavior on color { ColorAnimation { duration: 130 } }

    HoverHandler { id: ibHover; enabled: ib.allowed }

    Text {
      anchors.centerIn: parent
      text: ib.glyph
      color: root.fg
      opacity: !ib.allowed ? 0.22 : (ib.active ? 1.0 : (ibHover.hovered ? 1.0 : 0.68))
      font.family: root.mono
      font.pixelSize: ib.glyphSize
      Behavior on opacity { NumberAnimation { duration: 130 } }
    }

    // Small dot under an engaged toggle -- reads as "on" without needing colour.
    Rectangle {
      visible: ib.active
      anchors.horizontalCenter: parent.horizontalCenter
      anchors.bottom: parent.bottom
      anchors.bottomMargin: -1
      width: 3; height: 3; radius: 1.5
      color: root.fg
      opacity: 0.8
    }

    MouseArea {
      anchors.fill: parent
      enabled: ib.allowed
      cursorShape: Qt.PointingHandCursor
      onClicked: ib.activated()
    }
  }

  visible: hasMedia
  // No Behavior here: the inner clips already ease their own widths, so the
  // pill grows smoothly. Animating this too would double-ease and lag.
  implicitWidth: hasMedia ? pill.implicitWidth : 0
  implicitHeight: bar ? bar.barSize : 26

  // ---- pill body interaction ----
  // Declared BEFORE the pill so it sits underneath: the transport buttons and
  // the scrub strip are later siblings and win the click. It stays the only
  // hoverEnabled area, and the areas above it leave hover events alone, so
  // `hovered` still tracks the whole widget.
  MouseArea {
    anchors.fill: parent
    hoverEnabled: true
    cursorShape: root.hasMedia ? Qt.PointingHandCursor : Qt.ArrowCursor
    acceptedButtons: Qt.LeftButton | Qt.RightButton | Qt.MiddleButton

    onEntered: root.hovered = true
    onExited: root.hovered = false

    onClicked: function (mouse) {
      if (!root.hasMedia) return
      if (mouse.button === Qt.MiddleButton) root.act("next")
      else if (mouse.button === Qt.RightButton) root.act("playPause")
      else root.menuOpen = !root.menuOpen
    }

    onWheel: function (wheel) {
      if (!root.hasMedia) return
      root.act(wheel.angleDelta.y > 0 ? "previous" : "next")
    }
  }

  Rectangle {
    id: pill
    anchors.centerIn: parent
    implicitWidth: row.implicitWidth + 20
    implicitHeight: root.pillH
    radius: height / 2
    clip: true

    color: root.expanded ? root.alpha(0.10) : "transparent"
    border.width: 1
    border.color: root.alpha(root.expanded ? 0.18 : 0.00)
    Behavior on color { ColorAnimation { duration: 160; easing.type: Easing.OutCubic } }
    Behavior on border.color { ColorAnimation { duration: 160 } }

    Row {
      id: row
      // Above the scrub strip below, so the bottom edge of a transport button
      // is still a button and not a seek. The Row's own children are inert, so
      // scrubbing under the label still reaches the strip.
      z: 1
      anchors.verticalCenter: parent.verticalCenter
      anchors.left: parent.left
      anchors.leftMargin: 10
      spacing: 7

      // ---- equaliser glyph ----
      // Three bars that bounce out of phase while playing and settle flat when
      // paused, so play state reads without a separate icon.
      Item {
        id: eq
        width: 10
        height: 11
        anchors.verticalCenter: parent.verticalCenter

        Repeater {
          model: 3

          Rectangle {
            id: barItem
            required property int index

            property real bounce: 0

            x: index * 4
            width: 2
            radius: 1
            anchors.bottom: parent.bottom
            color: root.fg
            opacity: root.playing ? 0.85 : 0.40
            height: 3 + (root.playing ? bounce : 0)

            SequentialAnimation on bounce {
              running: root.playing
              loops: Animation.Infinite
              NumberAnimation { to: 8; duration: 360 + barItem.index * 140; easing.type: Easing.InOutSine }
              NumberAnimation { to: 0; duration: 400 + barItem.index * 100; easing.type: Easing.InOutSine }
            }

            // Only smooth the settle back to flat -- smoothing the bounce too
            // would fight the animation and turn it to mush.
            Behavior on height {
              enabled: !root.playing
              NumberAnimation { duration: 220; easing.type: Easing.OutCubic }
            }
            Behavior on opacity { NumberAnimation { duration: 220 } }
          }
        }
      }

      // ---- track label ----
      Item {
        id: labelClip
        width: Math.min(root.labelWidth, label.implicitWidth)
        height: eq.height
        clip: true
        anchors.verticalCenter: parent.verticalCenter

        Behavior on width { NumberAnimation { duration: 220; easing.type: Easing.OutCubic } }

        Text {
          id: label
          text: root.title + (root.artist ? "  ·  " + root.artist : "")
          color: root.fg
          opacity: root.expanded ? 0.95 : 0.70
          font.family: root.mono
          font.pixelSize: Style.font.bodySmall
          anchors.verticalCenter: parent.verticalCenter
          Behavior on opacity { NumberAnimation { duration: 200 } }

          // Idle: ellipsis, so a long title never ends on a sliced glyph.
          // Hovered: full width and no elide, which is what the marquee scrolls.
          width: root.expanded ? implicitWidth : labelClip.width
          elide: root.expanded ? Text.ElideNone : Text.ElideRight

          readonly property bool overflows: implicitWidth > labelClip.width

          NumberAnimation on x {
            running: label.overflows && root.expanded
            loops: Animation.Infinite
            duration: Math.max(5000, label.implicitWidth * 28)
            from: 0
            to: -label.implicitWidth - 24
            easing.type: Easing.Linear
            onRunningChanged: if (!running) label.x = 0
          }
        }
      }

      // ---- elapsed / total ----
      Item {
        width: root.expanded && root.lenSec > 0 ? time.implicitWidth + 4 : 0
        height: eq.height
        clip: true
        anchors.verticalCenter: parent.verticalCenter
        opacity: root.expanded && root.lenSec > 0 ? 1 : 0

        Behavior on width { NumberAnimation { duration: 220; easing.type: Easing.OutCubic } }
        Behavior on opacity { NumberAnimation { duration: 180 } }

        Text {
          id: time
          anchors.right: parent.right
          anchors.rightMargin: 4
          anchors.verticalCenter: parent.verticalCenter
          text: root.fmt(root.posSec) + " / " + root.fmt(root.lenSec)
          color: root.fg
          opacity: 0.42
          font.family: root.mono
          font.pixelSize: Style.font.caption
        }
      }

      // ---- transport controls ----
      Item {
        id: controlsClip
        width: root.expanded ? controls.implicitWidth + 4 : 0
        height: root.pillH
        clip: true
        opacity: root.expanded ? 1 : 0
        anchors.verticalCenter: parent.verticalCenter

        Behavior on width { NumberAnimation { duration: 240; easing.type: Easing.OutCubic } }
        Behavior on opacity { NumberAnimation { duration: 170 } }

        Row {
          id: controls
          anchors.right: parent.right
          anchors.rightMargin: 4
          anchors.verticalCenter: parent.verticalCenter
          spacing: 2

          IconButton {
            anchors.verticalCenter: parent.verticalCenter
            glyph: "󰒮"; glyphSize: Style.font.bodySmall
            allowed: !!root.player && !!root.player.canGoPrevious
            onActivated: root.act("previous")
          }
          IconButton {
            anchors.verticalCenter: parent.verticalCenter
            glyph: root.playing ? "󰏤" : "󰐊"
            allowed: !!root.player && !!(root.player.canTogglePlaying || root.player.canPlay || root.player.canPause)
            onActivated: root.act("playPause")
          }
          IconButton {
            anchors.verticalCenter: parent.verticalCenter
            glyph: "󰒭"; glyphSize: Style.font.bodySmall
            allowed: !!root.player && !!root.player.canGoNext
            onActivated: root.act("next")
          }
        }
      }
    }

    // ---- progress hairline ----
    // Sits on the pill's bottom edge; thickens on hover and becomes a scrub
    // target. Inset horizontally so it stays inside the rounded corners.
    Item {
      id: track
      anchors.left: parent.left
      anchors.right: parent.right
      anchors.bottom: parent.bottom
      anchors.leftMargin: 10
      anchors.rightMargin: 10
      anchors.bottomMargin: 3
      height: root.expanded ? 3 : 2
      visible: root.lenSec > 0

      Behavior on height { NumberAnimation { duration: 160 } }

      Rectangle {
        anchors.fill: parent
        radius: height / 2
        color: root.alpha(root.expanded ? 0.16 : 0.08)
        Behavior on color { ColorAnimation { duration: 160 } }
      }

      Rectangle {
        width: parent.width * root.progress
        height: parent.height
        radius: height / 2
        color: root.fg
        opacity: root.expanded ? 0.80 : 0.34
        Behavior on width { NumberAnimation { duration: 900; easing.type: Easing.Linear } }
        Behavior on opacity { NumberAnimation { duration: 160 } }
      }
    }

    // Scrub strip: the bottom 9px of the pill, above the body click area so a
    // seek never lands as an accidental play/pause.
    MouseArea {
      anchors.left: parent.left
      anchors.right: parent.right
      anchors.bottom: parent.bottom
      height: 9
      enabled: root.expanded && root.seekable
      cursorShape: enabled ? Qt.SizeHorCursor : Qt.ArrowCursor
      onPressed: function (mouse) { root.seekTo((mouse.x - 10) / Math.max(1, track.width)) }
      onPositionChanged: function (mouse) {
        if (pressed) root.seekTo((mouse.x - 10) / Math.max(1, track.width))
      }
    }
  }

  // =====================================================================
  //  Control panel
  //
  //  Built on Omarchy's own PopupCard / PanelSlider / PanelSectionHeader /
  //  PanelSeparator / Button instead of hand-rolled chrome. That buys
  //  Color.popups.*, Style.cornerRadius, the shared 140ms fade, focus-grab
  //  dismissal, bar-position-aware anchoring and the popout coordinator for
  //  free -- and means this panel re-themes with every other Omarchy popup
  //  rather than drifting away from them.
  // =====================================================================

  PopupCard {
    id: pop
    anchorItem: root
    bar: root.bar
    owner: root
    open: root.menuOpen && root.hasMedia
    contentWidth: pop.fittedContentWidth(Style.space(330))
    contentHeight: pop.fittedContentHeight(col.implicitHeight)

    Column {
      id: col
      anchors.fill: parent
      spacing: Style.space(14)

      // ---- hero row: artwork | track metadata | uppercase status ----
      // Mirrors the battery popup's hero: icon, stacked labels, and a
      // letterspaced all-caps status line in Qt.darker(fg, 1.4).
      Item {
        width: parent.width
        implicitHeight: Math.max(artFrame.height, heroLabels.implicitHeight)

        Rectangle {
          id: artFrame
          width: Style.space(78)
          height: Style.space(78)
          radius: Style.space(8)
          anchors.left: parent.left
          anchors.verticalCenter: parent.verticalCenter
          color: Style.selectedFillFor(root.fg, Color.accent)

          Item {
            id: artSource
            anchors.fill: parent
            visible: false
            layer.enabled: true
            Image {
              anchors.fill: parent
              source: root.artUrl
              fillMode: Image.PreserveAspectCrop
              asynchronous: true
              cache: true
            }
          }

          Rectangle {
            id: artMask
            anchors.fill: parent
            radius: artFrame.radius
            visible: false
            layer.enabled: true
          }

          // Greyscale by default so the panel stays inside the rice; the cover
          // returns to full colour only while the cursor is on it.
          MultiEffect {
            anchors.fill: parent
            source: artSource
            visible: root.artUrl !== ""
            saturation: artHover.hovered ? 0.0 : -1.0
            maskEnabled: true
            maskSource: artMask
            Behavior on saturation { NumberAnimation { duration: 320; easing.type: Easing.OutCubic } }
          }

          Text {
            anchors.centerIn: parent
            visible: root.artUrl === ""
            text: "󰝚"
            color: root.fg
            opacity: 0.3
            font.family: root.mono
            font.pixelSize: Style.font.display
          }

          HoverHandler { id: artHover }
        }

        Column {
          id: heroLabels
          anchors.left: artFrame.right
          anchors.leftMargin: Style.space(12)
          anchors.right: parent.right
          anchors.verticalCenter: artFrame.verticalCenter
          spacing: Style.space(2)

          Text {
            width: parent.width
            text: root.title || "Nothing playing"
            color: root.fg
            font.family: root.mono
            font.pixelSize: Style.font.title
            font.bold: true
            elide: Text.ElideRight
            maximumLineCount: 2
            wrapMode: Text.WordWrap
          }
          Text {
            width: parent.width
            text: root.artist
            color: root.fg
            opacity: 0.6
            font.family: root.mono
            font.pixelSize: Style.font.bodySmall
            elide: Text.ElideRight
            visible: text !== ""
          }
          Text {
            width: parent.width
            text: root.album
            color: root.fg
            opacity: 0.45
            font.family: root.mono
            font.pixelSize: Style.font.caption
            elide: Text.ElideRight
            visible: text !== ""
          }
          Text {
            topPadding: Style.space(4)
            text: (root.playing ? "Playing" : "Paused").toUpperCase()
            color: Qt.darker(root.fg, 1.4)
            font.family: root.mono
            font.pixelSize: Style.font.caption
            font.bold: true
            font.letterSpacing: 1.2
          }
        }
      }

      // ---- scrub ----
      PanelSlider {
        id: scrub
        width: parent.width
        bar: root.bar
        visible: root.lenSec > 0
        enabled: root.seekable
        opacity: root.seekable ? 1.0 : 0.4
        minimum: 0
        maximum: Math.max(1, root.lenSec)
        step: 1
        value: root.posSec
        onReleased: function (v) { root.seekSeconds(v) }
      }

      Item {
        width: parent.width
        implicitHeight: elapsed.implicitHeight
        visible: root.lenSec > 0

        Text {
          id: elapsed
          anchors.left: parent.left
          // While dragging, read the handle rather than the player, so the
          // number tracks the thumb instead of lagging a second behind it.
          text: root.fmt(scrub.dragging ? scrub.liveValue : root.posSec)
          color: root.fg
          opacity: 0.6
          font.family: root.mono
          font.pixelSize: Style.font.bodySmall
        }

        Text {
          id: rightTime
          property bool showRemaining: false
          anchors.right: parent.right
          text: showRemaining
            ? "-" + root.fmt(Math.max(0, root.lenSec - root.posSec))
            : root.fmt(root.lenSec)
          color: root.fg
          opacity: rtHover.hovered ? 0.85 : 0.6
          font.family: root.mono
          font.pixelSize: Style.font.bodySmall
          Behavior on opacity { NumberAnimation { duration: 130 } }

          HoverHandler { id: rtHover }
          MouseArea {
            anchors.fill: parent
            anchors.margins: -Style.space(4)
            cursorShape: Qt.PointingHandCursor
            onClicked: rightTime.showRemaining = !rightTime.showRemaining
          }
        }
      }

      PanelSeparator { foreground: root.fg }
      PanelSectionHeader { text: "PLAYBACK"; foreground: root.fg }

      // ---- transport ----
      Row {
        anchors.horizontalCenter: parent.horizontalCenter
        spacing: Style.space(6)

        Button {
          anchors.verticalCenter: parent.verticalCenter
          iconText: "󰒝"
          foreground: root.fg
          iconSize: Style.font.icon
          bordered: true
          active: !!root.player && !!root.player.shuffle
          enabled: !!root.player && !!root.player.shuffleSupported
          opacity: enabled ? 1.0 : 0.35
          onClicked: { try { root.player.shuffle = !root.player.shuffle } catch (e) {} }
        }
        Button {
          anchors.verticalCenter: parent.verticalCenter
          iconText: "󰒮"
          foreground: root.fg
          iconSize: Style.font.icon
          enabled: !!root.player && !!root.player.canGoPrevious
          opacity: enabled ? 1.0 : 0.35
          onClicked: root.act("previous")
        }
        Button {
          anchors.verticalCenter: parent.verticalCenter
          iconText: root.playing ? "󰏤" : "󰐊"
          foreground: root.fg
          iconSize: Style.font.iconLarge
          horizontalPadding: Style.spacing.panelGap
          enabled: !!root.player && !!(root.player.canTogglePlaying || root.player.canPlay || root.player.canPause)
          opacity: enabled ? 1.0 : 0.35
          onClicked: root.act("playPause")
        }
        Button {
          anchors.verticalCenter: parent.verticalCenter
          iconText: "󰒭"
          foreground: root.fg
          iconSize: Style.font.icon
          enabled: !!root.player && !!root.player.canGoNext
          opacity: enabled ? 1.0 : 0.35
          onClicked: root.act("next")
        }
        Button {
          anchors.verticalCenter: parent.verticalCenter
          // The glyph names the state it is IN, not the one a click moves to.
          iconText: (root.player && root.player.loopState === MprisLoopState.Track) ? "󰑘" : "󰑖"
          foreground: root.fg
          iconSize: Style.font.icon
          bordered: true
          active: !!root.player && root.player.loopState !== MprisLoopState.None
          enabled: !!root.player && !!root.player.loopSupported
          opacity: enabled ? 1.0 : 0.35
          onClicked: {
            if (!root.player) return
            try {
              var s = root.player.loopState
              root.player.loopState = (s === MprisLoopState.None) ? MprisLoopState.Playlist
                : (s === MprisLoopState.Playlist) ? MprisLoopState.Track
                : MprisLoopState.None
            } catch (e) {}
          }
        }
      }

      // ---- volume ----
      Item {
        id: volBlock
        width: parent.width
        implicitHeight: volSlider.implicitHeight
        visible: !!root.player && !!root.player.volumeSupported

        readonly property real vol: (root.player && isFinite(root.player.volume))
          ? root.clamp01(root.player.volume) : 0

        Text {
          id: volIcon
          anchors.left: parent.left
          anchors.verticalCenter: parent.verticalCenter
          text: volBlock.vol <= 0.001 ? "󰝟" : volBlock.vol < 0.5 ? "󰖀" : "󰕾"
          color: root.fg
          opacity: 0.6
          font.family: root.mono
          font.pixelSize: Style.font.icon
        }

        PanelSlider {
          id: volSlider
          anchors.left: volIcon.right
          anchors.leftMargin: Style.space(10)
          anchors.right: parent.right
          anchors.verticalCenter: parent.verticalCenter
          bar: root.bar
          minimum: 0
          maximum: 1
          value: volBlock.vol
          onMoved: function (v) { try { root.player.volume = root.clamp01(v) } catch (e) {} }
        }
      }

      // ---- sources ----
      PanelSeparator { foreground: root.fg; visible: root.sources.length > 1 }
      PanelSectionHeader {
        text: "SOURCE"
        foreground: root.fg
        visible: root.sources.length > 1
      }

      Column {
        width: parent.width
        spacing: Style.space(4)
        visible: root.sources.length > 1

        Repeater {
          model: root.sources

          Button {
            id: srcBtn
            required property var modelData

            readonly property bool selected: !!root.player && !!modelData && !!root.mediaService
              && root.mediaService.playerKey(root.player) === root.mediaService.playerKey(modelData)

            width: parent.width
            leftAlign: true
            bordered: true
            active: selected
            foreground: root.fg
            fontSize: Style.font.bodySmall
            iconSize: Style.font.iconSmall
            iconText: modelData && modelData.isPlaying ? "󰏤" : "󰐊"
            text: root.sourceLabel(modelData)
            onClicked: if (root.mediaService)
              root.mediaService.selectPlayer(root.mediaService.playerKey(srcBtn.modelData))
          }
        }
      }
    }
  }
}
