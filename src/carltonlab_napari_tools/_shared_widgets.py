from pathlib import Path
from typing import TYPE_CHECKING, Literal

from qtpy.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLayout,
    QLineEdit,
    QListView,
    QMessageBox,
    QSizePolicy,
    QTreeView,
    QVBoxLayout,
    QWidget,
)

from carltonlab_napari_tools._shared_variables import (
    DEFAULT_SEPARATOR_SPACING,
    DEFAULT_SEPARATOR_THICKNESS,
)

if TYPE_CHECKING:
    from napari.components import ViewerModel


class FrameSeparator(QWidget):
    def __init__(
        self,
        spacing_width: tuple[int, int] = (
            DEFAULT_SEPARATOR_SPACING,
            DEFAULT_SEPARATOR_SPACING,
        ),
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(layout)

        layout.addSpacing(spacing_width[0])

        separator = QFrame(self)
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setFrameShadow(QFrame.Shadow.Sunken)
        separator.setStyleSheet("background-color: gray;")
        separator.setFixedHeight(DEFAULT_SEPARATOR_THICKNESS)
        layout.addWidget(separator)

        layout.addSpacing(spacing_width[1])


class KeepChannelsWidget(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self._channel_list: list[int] = []

        self._layout = QVBoxLayout()
        self._layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(self._layout)

        self._keep_channels_cb = QCheckBox("Keep channels")
        self._keep_channels_cb.toggled.connect(self._on_keep_channels_toggled)
        self._layout.addWidget(self._keep_channels_cb)

        self._keep_channels_row = QWidget()
        self._keep_channels_row_layout = QHBoxLayout()
        self._keep_channels_row_layout.setContentsMargins(0, 0, 0, 0)
        self._keep_channels_row.setLayout(self._keep_channels_row_layout)
        self._layout.addWidget(self._keep_channels_row)

        self._keep_channels_label = QLabel("Keep channels")
        self._keep_channels_label.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Preferred,
        )
        self._keep_channels_row_layout.addWidget(self._keep_channels_label)

        self._keep_channels_line_edit = QLineEdit()
        self._keep_channels_line_edit.editingFinished.connect(
            self._on_keep_channels_edited
        )
        self._keep_channels_row_layout.addWidget(self._keep_channels_line_edit)

        self._output_channel_row = QWidget()
        self._output_channel_row_layout = QHBoxLayout()
        self._output_channel_row_layout.setContentsMargins(0, 0, 0, 0)
        self._output_channel_row.setLayout(self._output_channel_row_layout)
        self._layout.addWidget(self._output_channel_row)

        self._output_channel_label = QLabel("Channel order: ")
        self._output_channel_row_layout.addWidget(self._output_channel_label)

        self._output_channel_result_label = QLabel("All channels")
        self._output_channel_row_layout.addWidget(
            self._output_channel_result_label
        )
        self._output_channel_row_layout.addStretch()

        self._on_keep_channels_toggled(False)

    @staticmethod
    def _parse_channels(channel_string: str) -> list[int]:
        if not channel_string.strip():
            return []

        channels: list[int] = []
        for part in channel_string.split(","):
            part = part.strip()
            if not part:
                return []

            if "-" in part:
                range_parts = part.split("-")
                if len(range_parts) != 2:
                    return []
                try:
                    start, end = (int(value.strip()) for value in range_parts)
                except ValueError:
                    return []
                if start > end:
                    return []
                channels.extend(range(start, end + 1))
            else:
                try:
                    channels.append(int(part))
                except ValueError:
                    return []

        return channels

    def _on_keep_channels_edited(self) -> None:
        self._channel_list = self._parse_channels(
            self._keep_channels_line_edit.text()
        )
        if not self._channel_list:
            self._keep_channels_line_edit.clear()
            self._output_channel_result_label.setText("All channels")
        else:
            self._output_channel_result_label.setText(
                ", ".join(str(channel) for channel in self._channel_list)
            )

    def _on_keep_channels_toggled(self, state: bool) -> None:
        self._keep_channels_line_edit.setEnabled(state)

    def get_channels(self) -> list[int]:
        if not self._keep_channels_cb.isChecked():
            return []
        return self._channel_list.copy()


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
) -> list[Path] | None:
    dialog = QFileDialog(parent, caption)
    dialog.setOption(QFileDialog.Option.DontUseNativeDialog, True)

    dialog.setFileMode(QFileDialog.FileMode.Directory)
    dialog.setOption(QFileDialog.Option.ShowDirsOnly, True)

    views = dialog.findChildren(QListView) + dialog.findChildren(QTreeView)
    for view in views:
        view.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection
        )

    if not dialog.exec():
        return None

    dirs = dialog.selectedFiles()
    if not dirs:
        return None
    return [Path(p) for p in dirs]


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
