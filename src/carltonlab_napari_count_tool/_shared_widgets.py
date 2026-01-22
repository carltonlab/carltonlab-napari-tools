from typing import TYPE_CHECKING

from qtpy.QtWidgets import QMessageBox

if TYPE_CHECKING:
    from napari.components import ViewerModel


def confirm_dialog(napari_viewer: "ViewerModel", message: str) -> bool:
    parent = getattr(
        getattr(napari_viewer, "window", None), "_qt_window", None
    )

    message_box = QMessageBox(parent=parent)
    message_box.setText(message)
    message_box.setStandardButtons(QMessageBox.Ok | QMessageBox.Cancel)
    message_box.setDefaultButton(QMessageBox.Ok)
    message_box.exec_()

    return (
        message_box.standardButton(message_box.clickedButton())
        == QMessageBox.Ok
    )
