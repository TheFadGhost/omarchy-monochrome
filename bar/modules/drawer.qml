import QtQuick
import Quickshell
import qs.Ui
import qs.Commons

// Icon drawer: collapses the wifi / sound / bluetooth / display bar icons
// into one chevron that fans the four icons out on hover (or on click, see
// `hoverMode`), and re-collapses when the pointer leaves.
//
// HOW IT WORKS -- this module does NOT reimplement the four panels.
// The four first-party widgets (`omarchy.network`, `omarchy.audio`,
// `omarchy.bluetooth`, `omarchy.monitor`) STAY in shell.json's bar layout:
// their plugins keep running, their panels stay summonable, and their state
// stays readable. This module finds their live instances through
// `bar.moduleSlots`, collapses their bar buttons to invisible
// 1px slivers with `Binding`s on the widget roots (implicitWidth/Height 1,
// opacity 0, enabled false -- see the Repeater below for why not
// visible:false), and draws its own animated icon cells that mirror each
// widget's real state. Clicking a
// cell calls the live widget's own `toggle()`, which opens the REAL
// first-party panel (the same KeyboardPanel the stock icon opens). If this
// module fails to load or is removed, the Bindings die with it and the stock
// icons come straight back -- graceful degradation by construction.
//
// Collapsed, anything in a non-default state stays fanned out on its own:
// muted output, disconnected network, connected bluetooth device, and any
// cell whose panel is currently open. A warning is never hidden in the drawer.
//
// Per-widget state read from the live items (all live-updating):
//   network    item.icon, item.kind ("wifi"|"ethernet"|"disconnected")
//   audio      item.outputIcon(), item.outputMuted, item.setOutputVolume()
//   bluetooth  item.icon, item.adapter, item.connectedDevices
//   monitor    static glyph, item.setBrightness()/showBrightnessOsd()
//
// Configuration -- from this entry's `settings` object in shell.json:
//   { "id": "drawer", "type": "qml",
//     "components": ["omarchy.network", ...],   // which widgets to subsume
//     "hover": true }                            // false = expand on click
// HOOK: when `ghost-settings dump --json` exists (planned settings.toml CLI),
// feed its values into `externalConfig` below; until then shell.json's
// per-entry settings are the single knob. Did not exist when this was built.
Item {
  id: root

  property var bar
  property string moduleName
  property var settings

  // External config hook (see header). Shape: { components: [...], hover: bool }
  property var externalConfig: ({})

  readonly property var componentIds: {
    var ext = externalConfig && Array.isArray(externalConfig.components)
      ? externalConfig.components : null
    if (ext && ext.length > 0) return ext
    var s = settings && Array.isArray(settings.components) ? settings.components : null
    if (s && s.length > 0) return s
    return ["omarchy.network", "omarchy.audio", "omarchy.bluetooth", "omarchy.monitor"]
  }

  readonly property bool hoverMode: {
    if (externalConfig && externalConfig.hover !== undefined) return externalConfig.hover !== false
    if (settings && settings.hover !== undefined) return settings.hover !== false
    return true
  }

  property bool hovered: false
  property bool pinnedOpen: false
  readonly property bool expanded: hoverMode ? (hovered || pinnedOpen) : pinnedOpen

  readonly property color fg: bar ? bar.barForeground : "#dfe3e6"
  readonly property string mono: bar ? bar.fontFamily : "monospace"
  function alpha(a) { return Qt.rgba(fg.r, fg.g, fg.b, a) }

  // Pill geometry fits INSIDE the island plate, not the raw bar band --
  // ghost.barisland insets the band by 7px top and bottom. Same derivation
  // as mediapill.qml; keep in sync with Island.qml's inset.
  readonly property int islandInset: Style.space(7)
  readonly property int pillH: Math.max(14, (bar ? bar.barSize : 26) - (islandInset * 2) - 4)
  readonly property int cellW: Style.space(24)

  // Bar.qml's open-panel mark defaults to 55% of the slot width; hint a dot.
  readonly property real openPanelIndicatorWidth: Style.space(18)

  // ---- live widget lookup -------------------------------------------------
  // Reading bar.moduleSlots and slot.activeItem inside the binding captures
  // them as dependencies, so this re-resolves when slots register or their
  // loaders finish. On a multi-monitor bar each widget has one slot per
  // screen; prefer the instance living in this drawer's own window so the
  // panel opens on the right screen.
  function itemFor(id) {
    var slots = (bar && bar.moduleSlots) ? bar.moduleSlots : []
    var fallback = null
    var mine = root.QsWindow ? root.QsWindow.window : null
    for (var i = 0; i < slots.length; i++) {
      var s = slots[i]
      if (!s || s.moduleName !== id) continue
      var item = s.activeItem
      if (!item) continue
      if (typeof item.open !== "function" || typeof item.close !== "function") continue
      if (!fallback) fallback = item
      if (mine && bar && typeof bar.slotWindow === "function" && bar.slotWindow(s) === mine)
        return item
    }
    return fallback
  }

  // Every live widget item this drawer manages, across all screens' slots --
  // all copies get hidden, each screen's drawer replaces its own.
  readonly property var managedItems: {
    var out = []
    var slots = (bar && bar.moduleSlots) ? bar.moduleSlots : []
    for (var i = 0; i < slots.length; i++) {
      var s = slots[i]
      if (!s || componentIds.indexOf(s.moduleName) === -1) continue
      var item = s.activeItem
      if (!item) continue
      if (typeof item.open !== "function" || typeof item.close !== "function") continue
      out.push(item)
    }
    return out
  }

  // ---- per-component presentation ----------------------------------------
  function cellGlyph(id, item) {
    if (id === "omarchy.audio")
      return item && typeof item.outputIcon === "function" ? item.outputIcon() : "󰕾"
    if (id === "omarchy.monitor")
      return Quickshell.screens.length > 1 ? "󰍺" : "󰍹"
    if (item && item.icon !== undefined && item.icon !== "") return item.icon
    if (id === "omarchy.network") return "󰤨"
    if (id === "omarchy.bluetooth") return "󰂯"
    return "󰘔"
  }

  // Non-default states that must stay visible while collapsed.
  function cellAlert(id, item) {
    if (!item) return false
    if (id === "omarchy.audio") return item.outputMuted === true
    if (id === "omarchy.network") return item.kind === "disconnected"
    if (id === "omarchy.bluetooth")
      return !!(item.connectedDevices && item.connectedDevices.length > 0)
        || !!(item.adapter && !item.adapter.enabled)
    return false
  }

  function cellLabel(id) {
    if (id === "omarchy.network") return "Network"
    if (id === "omarchy.audio") return "Volume"
    if (id === "omarchy.bluetooth") return "Bluetooth"
    if (id === "omarchy.monitor") return "Display"
    var tail = String(id).split(".").pop()
    return tail.charAt(0).toUpperCase() + tail.slice(1)
  }

  // Mirror the first-party icons' non-left-click affordances.
  function cellSecondary(id, item) {
    if (!item) return
    if (id === "omarchy.audio" && typeof item.toggleAllMuted === "function") item.toggleAllMuted()
    else if (id === "omarchy.bluetooth" && typeof item.toggleBluetooth === "function") item.toggleBluetooth()
    else item.toggle()
  }

  function cellWheel(id, item, delta) {
    if (!item) return
    if (id === "omarchy.audio" && typeof item.setOutputVolume === "function") {
      if (item.hasOutput === false) return
      var v = item.setOutputVolume(item.outputVolume + (delta > 0 ? 0.05 : -0.05))
      if (typeof item.showVolumeOsd === "function") item.showVolumeOsd(v)
    } else if (id === "omarchy.monitor" && typeof item.setBrightness === "function") {
      if (item.brightnessAvailable === false) return
      item.setBrightness(item.brightnessPercent + (delta > 0 ? 5 : -5))
      if (typeof item.showBrightnessOsd === "function") item.showBrightnessOsd(item.brightnessPercent)
    }
  }

  // ---- hide the subsumed first-party bar buttons --------------------------
  // Bar.qml: `implicitWidth: activeItem && activeItem.visible ? ... : 0`, so
  // an invisible widget root collapses its slot. RestoreBindingOrValue puts
  // the widget's own `visible` binding back if this module unloads.
  // A Repeater (not Instantiator) because Instantiator resolved every
  // delegate's context modelData to the first model entry here -- only the
  // first widget got hidden. Repeater's required-property injection is
  // per-delegate and reliable; the wrapper Items are zero-size and invisible,
  // parented to this root, and only exist to host the Bindings.
  //
  // The buttons are collapsed to a 1px transparent disabled sliver, NOT
  // visible:false. Row positioners skip zero-size items entirely, so a
  // visible:false widget's slot was left at the section origin (x=1395,
  // measured via `omarchy-shell shell debugBarGeometry`) and its panel --
  // which anchors to the bar button -- opened centered there, nowhere near
  // the drawer. At 1px the slot keeps its true layout position right beside
  // this drawer, so a summoned panel drops where the drawer sits. The
  // widget's own `visible` binding stays untouched (e.g. bluetooth hides
  // itself when there is no adapter), and the panels live in separate
  // popup surfaces, which item opacity/enabled do not propagate into.
  Repeater {
    model: root.managedItems
    delegate: Item {
      required property var modelData
      visible: false
      Binding { target: modelData; property: "implicitWidth"; value: 1; restoreMode: Binding.RestoreBindingOrValue }
      Binding { target: modelData; property: "implicitHeight"; value: 1; restoreMode: Binding.RestoreBindingOrValue }
      Binding { target: modelData; property: "opacity"; value: 0; restoreMode: Binding.RestoreBindingOrValue }
      Binding { target: modelData; property: "enabled"; value: false; restoreMode: Binding.RestoreBindingOrValue }
    }
  }

  visible: managedItems.length > 0
  implicitWidth: pill.implicitWidth
  implicitHeight: bar ? bar.barSize : 26

  // Hover layer, declared FIRST so the cell MouseAreas (later siblings) win
  // clicks while this stays the only hoverEnabled area (mediapill pattern:
  // hoverEnabled:false areas above are transparent to hover but eat clicks).
  MouseArea {
    anchors.fill: parent
    hoverEnabled: true
    acceptedButtons: Qt.NoButton
    onEntered: root.hovered = true
    onExited: root.hovered = false
  }

  Rectangle {
    id: pill
    anchors.centerIn: parent
    implicitWidth: row.implicitWidth + Style.space(8)
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
      anchors.verticalCenter: parent.verticalCenter
      anchors.left: parent.left
      anchors.leftMargin: Style.space(4)
      spacing: 0

      Repeater {
        model: root.componentIds

        // Each cell clips itself shut instead of turning invisible, so the
        // fan-out is one eased width animation and the Row never jumps.
        Item {
          id: cell
          required property string modelData

          readonly property var widgetItem: root.itemFor(modelData)
          readonly property bool alert: root.cellAlert(modelData, widgetItem)
          readonly property bool panelOpen: !!widgetItem && widgetItem.opened === true
          readonly property bool shown: !!widgetItem && widgetItem.visible === true
            && (root.expanded || alert || panelOpen)

          width: shown ? root.cellW : 0
          height: root.pillH
          clip: true
          opacity: shown ? 1 : 0
          Behavior on width { NumberAnimation { duration: 220; easing.type: Easing.OutCubic } }
          Behavior on opacity { NumberAnimation { duration: 170 } }

          Rectangle {
            anchors.horizontalCenter: parent.horizontalCenter
            anchors.verticalCenter: parent.verticalCenter
            width: root.cellW - Style.space(2)
            height: Math.min(root.pillH - 2, width)
            radius: height / 2
            color: cellHover.hovered ? root.alpha(0.14) : "transparent"
            Behavior on color { ColorAnimation { duration: 130 } }
          }

          Text {
            anchors.centerIn: parent
            text: root.cellGlyph(cell.modelData, cell.widgetItem)
            color: root.fg
            opacity: cell.panelOpen || cellHover.hovered ? 1.0 : (cell.alert && !root.expanded ? 0.9 : 0.75)
            font.family: root.mono
            font.pixelSize: Style.font.icon
            Behavior on opacity { NumberAnimation { duration: 130 } }
          }

          // Open-panel dot, mirroring Bar.qml's mark (which now has no
          // visible slot to sit on).
          Rectangle {
            visible: cell.panelOpen
            anchors.horizontalCenter: parent.horizontalCenter
            anchors.bottom: parent.bottom
            width: Style.space(10)
            height: Style.space(2)
            radius: height / 2
            color: Color.accent
            opacity: 0.9
          }

          HoverHandler {
            id: cellHover
            onHoveredChanged: {
              if (!root.bar) return
              if (hovered) root.bar.showTooltip(cell, root.cellLabel(cell.modelData))
              else root.bar.hideTooltip(cell)
            }
          }

          MouseArea {
            anchors.fill: parent
            acceptedButtons: Qt.LeftButton | Qt.RightButton | Qt.MiddleButton
            onClicked: function (mouse) {
              var item = cell.widgetItem
              if (!item) return
              if (mouse.button === Qt.RightButton) root.cellSecondary(cell.modelData, item)
              else item.toggle()
            }
            onWheel: function (wheel) {
              root.cellWheel(cell.modelData, cell.widgetItem, wheel.angleDelta.y)
            }
          }
        }
      }

      // ---- summary glyph ----
      // Chevron pointing the way the drawer fans (cells grow to its left);
      // flips while expanded. Click pins it open -- the only expand gesture
      // when `hover` is configured false.
      Item {
        id: glyphCell
        width: Style.space(16)
        height: root.pillH

        Text {
          anchors.centerIn: parent
          text: root.expanded ? "󰅂" : "󰅁"
          color: root.fg
          opacity: glyphHover.hovered || root.expanded ? 0.95 : 0.55
          font.family: root.mono
          font.pixelSize: Style.font.iconSmall
          Behavior on opacity { NumberAnimation { duration: 130 } }
        }

        HoverHandler { id: glyphHover }

        MouseArea {
          anchors.fill: parent
          onClicked: root.pinnedOpen = !root.pinnedOpen
        }
      }
    }
  }
}
