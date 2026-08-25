import QtQuick
import Quickshell
import Quickshell.Wayland
import qs.Commons

// Floating-bar backing plate.
//
// Omarchy's bar cannot be detached from the screen edge -- its margins exist
// only for hide-parking, and a PanelWindow's own colour cannot be rounded.
// Cloning the bar to patch that is not viable either: cloned bar-kind plugins
// never receive their required properties from the shell host in 4.0.0.
//
// So instead: the bar is made taller and transparent via shell.toml, and this
// service paints a rounded island inside that taller band, on the layer just
// below it. The bar's widgets are vertically centred in the band, so they land
// on the plate and the whole thing reads as one floating bar.
Item {
  id: root

  readonly property int inset: 7          // vertical gap, band edge -> plate
  readonly property int sideInset: 10     // horizontal gap, screen edge -> plate
  readonly property int band: Style.bar.sizeHorizontal

  Variants {
    model: Quickshell.screens

    PanelWindow {
      id: win
      required property var modelData
      screen: modelData

      color: "transparent"
      exclusionMode: ExclusionMode.Ignore
      WlrLayershell.namespace: "ghost-bar-island"
      WlrLayershell.layer: WlrLayer.Bottom
      WlrLayershell.keyboardFocus: WlrKeyboardFocus.None

      anchors { top: true; left: true; right: true }
      implicitHeight: root.band

      Rectangle {
        anchors.fill: parent
        anchors.topMargin: root.inset
        anchors.bottomMargin: root.inset
        anchors.leftMargin: root.sideInset
        anchors.rightMargin: root.sideInset

        radius: height / 2
        antialiasing: true
        // The theme background is #0a0a0b, identical to the darker parts of the
        // wallpaper -- a plate painted in it is invisible. Tint it toward the
        // foreground so the island reads as a raised surface.
        color: Qt.tint(Color.bar.background,
                       Qt.rgba(Color.bar.text.r, Color.bar.text.g, Color.bar.text.b, 0.05))
        border.width: 1
        border.color: Qt.rgba(Color.bar.text.r, Color.bar.text.g, Color.bar.text.b, 0.22)

        Behavior on color { ColorAnimation { duration: 420; easing.type: Easing.InOutCubic } }
      }
    }
  }
}
