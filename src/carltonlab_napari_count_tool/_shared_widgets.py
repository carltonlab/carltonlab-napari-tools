from typing import TYPE_CHECKING, Literal

from qtpy.QtWidgets import QAbstractItemView, QFileDialog, QMessageBox, QWidget

if TYPE_CHECKING:
    from napari.components import ViewerModel


def confirm_dialog(
    napari_viewer: "ViewerModel", message: str, no_mode: bool = False
) -> bool:
    parent = getattr(
        getattr(napari_viewer, "window", None), "_qt_window", None
    )

    message_box = QMessageBox(parent=parent)
    message_box.setText(message)
    if not no_mode:
        message_box.setStandardButtons(QMessageBox.Ok | QMessageBox.Cancel)
    if no_mode:
        message_box.setStandardButtons(QMessageBox.No | QMessageBox.Ok)
    message_box.setDefaultButton(QMessageBox.Ok)
    message_box.exec_()

    return (
        message_box.standardButton(message_box.clickedButton())
        == QMessageBox.Ok
    )


def get_directory(
    parent: QWidget | None = None, caption: str = "Select directory"
) -> str | None:
    directory = QFileDialog.getExistingDirectory(
        parent, caption, "", QFileDialog.Option.ShowDirsOnly
    )
    return directory or None


ClspPickResult = list[str] | None | Literal["non-clsp"]


def get_clsp_directories(
    parent: QWidget | None = None,
    caption: str = "Select one or more *_clsp directories",
    start_dir: str | None = None,
) -> ClspPickResult:
    dialog = QFileDialog(parent, caption)
    dialog.setFileMode(QFileDialog.FileMode.Directory)
    dialog.setOption(QFileDialog.Option.DontUseNativeDialog, True)
    dialog.setOption(QFileDialog.Option.ShowDirsOnly, True)

    if start_dir:
        dialog.setDirectory(start_dir)

    # Enable multi-selection
    list_view = dialog.findChild(QAbstractItemView, "listView")
    if list_view is not None:
        list_view.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection
        )

    tree_view = dialog.findChild(QAbstractItemView, "treeView")
    if tree_view is not None:
        tree_view.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection
        )

    if not dialog.exec():
        return None  # user cancelled

    selected = dialog.selectedFiles()

    # Hard validation: ALL must end with `_clsp`
    if not selected or any(
        not d.rstrip("/").endswith("_clsp") for d in selected
    ):
        return "non-clsp"

    return selected
