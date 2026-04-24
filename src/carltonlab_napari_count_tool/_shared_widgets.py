from typing import TYPE_CHECKING, Literal

from qtpy.QtCore import QDir
from qtpy.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLayout,
    QListView,
    QMessageBox,
    QTreeView,
    QVBoxLayout,
    QWidget,
)

from carltonlab_napari_count_tool._shared_variables import (
    DEFAULT_SEPARATOR_SPACING,
    DEFAULT_SEPARATOR_THICKNESS,
)

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


def get_file(
    parent: QWidget,
    caption: str = "Select file",
) -> str | None:
    file_path, _ = QFileDialog.getOpenFileName(
        parent,
        caption,
        "",
        "TIFF images (*.tif *.tiff);;Config files (*.config)",
    )
    return file_path or None


def get_files(
    parent: QWidget | None = None,
    caption: str = "Select files",
    filters: str = "TIFF images (*.tif *.tiff);;Config files (*.config);;All files (*)",
) -> list[str] | None:
    file_paths, _ = QFileDialog.getOpenFileNames(parent, caption, "", filters)
    return file_paths or None


def get_directories(
    parent: QWidget | None = None,
    caption: str = "Select directories",
) -> list[str] | None:
    dialog = QFileDialog(parent, caption)
    dialog.setOption(QFileDialog.Option.DontUseNativeDialog, True)

    # Directory picking mode
    dialog.setFileMode(QFileDialog.FileMode.Directory)
    dialog.setOption(QFileDialog.Option.ShowDirsOnly, True)

    # Allow multi-selection in the internal views
    views = dialog.findChildren(QListView) + dialog.findChildren(QTreeView)
    for view in views:
        view.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection
        )

    # (Optional) start at home; remove if you want Qt's default
    dialog.setDirectory(QDir.homePath())

    if not dialog.exec():
        return None

    # selectedFiles() will contain directories in Directory mode
    dirs = dialog.selectedFiles()
    return dirs or None


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


def clear_layout(layout: QLayout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        if widget is not None:
            widget.deleteLater()
        else:
            child_layout = item.layout()
            if child_layout is not None:
                clear_layout(child_layout)


def add_separator_to_container(
    container: QWidget,
    orientation: Literal["vertical", "horizontal"],
    spacing_width: tuple[int, int] = (
        DEFAULT_SEPARATOR_SPACING,
        DEFAULT_SEPARATOR_SPACING,
    ),
    separator_thickness: int = DEFAULT_SEPARATOR_THICKNESS,
) -> QFrame | None:
    assert orientation in ["vertical", "horizontal"]
    layout = container.layout()
    if not isinstance(layout, QHBoxLayout) and not isinstance(
        layout, QVBoxLayout
    ):
        print(
            f"The layout must be a QHBoxLayout or QVBoxLayout, not {type(layout)}"
        )
        return
    layout.addSpacing(spacing_width[0])
    separator_orientation: QFrame.Shape = QFrame.Shape.HLine
    if orientation == "vertical":
        separator_orientation = QFrame.Shape.VLine
    if orientation == "horizontal":
        separator_orientation = QFrame.Shape.HLine
    separator = QFrame(container)
    separator.setFrameShape(separator_orientation)
    separator.setFrameShadow(QFrame.Shadow.Sunken)
    separator.setStyleSheet("background-color: gray;")
    separator.setFixedHeight(separator_thickness)
    layout.addWidget(separator)
    layout.addSpacing(spacing_width[1])
    return separator
