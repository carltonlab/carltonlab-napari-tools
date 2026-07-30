import os
from pathlib import Path
from typing import TYPE_CHECKING, cast

from qtpy.QtCore import QSize, Qt
from qtpy.QtGui import QIcon
from qtpy.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from carltonlab_napari_tools._protocols import (
    CToolButton,
    MainWidgetCallBacks,
)
from carltonlab_napari_tools._shared_widgets import get_directories
from carltonlab_napari_tools.image_stitching._image_stitching import (
    get_stitched_output_path,
    stitch_directories,
)

if TYPE_CHECKING:
    from napari.viewer import ViewerModel

BUTTONS_WIDTH = 30
ICONS_DIR = Path(__file__).resolve().parent.parent / "assets" / "icons"
ADD_DIR_ICON = ICONS_DIR / "add_dir.svg"
REMOVE_ICON = ICONS_DIR / "remove.svg"


class StitchOmeZarrWidget(QWidget):
    def __init__(
        self,
        napari_viewer: "ViewerModel",
        parent_widget: MainWidgetCallBacks,
        ct_tool_button: CToolButton,
    ):
        parent_q_widget: QWidget = cast(QWidget, parent_widget)
        super().__init__(parent_q_widget)

        self._napari_viewer = napari_viewer
        self._parent_widget: MainWidgetCallBacks = parent_widget
        self._ct_tool_button = ct_tool_button
        self._directories_list: list[str] = []

        self.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )

        self._layout = QVBoxLayout()
        self.setLayout(self._layout)
        self._layout.setContentsMargins(25, 2, 2, 25)

        self._main_scroll_area: QScrollArea = QScrollArea()
        self._main_scroll_area.setWidgetResizable(True)
        self._main_scroll_area.setViewportMargins(0, 0, 10, 0)
        self._layout.addWidget(self._main_scroll_area, 1)

        self._main_container: QWidget = QWidget()
        self._main_scroll_area.setWidget(self._main_container)
        self._main_layout: QVBoxLayout = QVBoxLayout()
        self._main_layout.setContentsMargins(0, 0, 0, 0)
        self._main_container.setLayout(self._main_layout)

        self._main_title_label = QLabel("CL Stitch OME.zarr")
        self._main_title_label.setStyleSheet(
            "font-weight: bold; font-size: 20px"
        )
        self._main_title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._main_layout.addWidget(self._main_title_label)

        self._add_remove_container: QWidget = QWidget()
        self._add_remove_container_layout: QHBoxLayout = QHBoxLayout()
        self._add_remove_container_layout.setContentsMargins(0, 0, 0, 0)
        self._add_remove_container_layout.setSpacing(6)
        self._add_remove_container.setLayout(self._add_remove_container_layout)

        self._q_list_title: QLabel = QLabel("OME.zarr directories")
        self._q_list_title.setStyleSheet("font-weight: bold")
        self._q_list_title.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        self._add_remove_container_layout.addWidget(self._q_list_title)

        self._add_directory_button: QPushButton = QPushButton("")
        self._add_directory_button.setIcon(QIcon(str(ADD_DIR_ICON)))
        self._add_directory_button.setFixedSize(BUTTONS_WIDTH, BUTTONS_WIDTH)
        self._add_directory_button.setIconSize(
            QSize(BUTTONS_WIDTH - 6, BUTTONS_WIDTH - 6)
        )
        self._add_directory_button.clicked.connect(
            self._add_directory_button_pressed
        )
        self._add_remove_container_layout.addWidget(self._add_directory_button)

        self._remove_selected_button: QPushButton = QPushButton("")
        self._remove_selected_button.setIcon(QIcon(str(REMOVE_ICON)))
        self._remove_selected_button.setFixedSize(BUTTONS_WIDTH, BUTTONS_WIDTH)
        self._remove_selected_button.setIconSize(
            QSize(BUTTONS_WIDTH - 6, BUTTONS_WIDTH - 6)
        )
        self._remove_selected_button.clicked.connect(
            self._remove_selected_button_pressed
        )
        self._add_remove_container_layout.addWidget(
            self._remove_selected_button
        )

        self._main_layout.addWidget(self._add_remove_container)

        self._directories_q_list: QListWidget = QListWidget()
        self._directories_q_list.setSelectionMode(
            QAbstractItemView.SelectionMode.MultiSelection
        )

        self._list_scroll_area: QScrollArea = QScrollArea()
        self._list_scroll_area.setWidgetResizable(True)
        self._list_scroll_area.setFixedHeight(300)

        list_container: QWidget = QWidget()
        list_container_layout = QVBoxLayout()
        list_container_layout.setContentsMargins(0, 0, 0, 0)
        list_container.setLayout(list_container_layout)
        list_container_layout.addWidget(self._directories_q_list)

        self._list_scroll_area.setWidget(list_container)
        self._main_layout.addWidget(self._list_scroll_area)
        self._main_layout.addSpacing(6)

        separator = QFrame(self._main_container)
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setFrameShadow(QFrame.Shadow.Sunken)
        separator.setStyleSheet("background-color: gray;")
        separator.setFixedHeight(2)
        self._main_layout.addWidget(separator)
        self._main_layout.addSpacing(6)

        self._stitch_button: QPushButton = QPushButton("Stitch gonads")
        self._stitch_button.clicked.connect(self._stitch_button_pressed)
        self._main_layout.addWidget(self._stitch_button)

        self._files_created_status_label: QLabel = QLabel("")
        self._main_layout.addWidget(self._files_created_status_label)
        self._set_files_created_label_state(False)

        self._main_layout.addStretch()

    def _add_directory_button_pressed(self) -> None:
        directories_path_list: list[str] | None = get_directories(
            self, caption="Select the directories"
        )
        if directories_path_list is None:
            return
        for directory_path in directories_path_list:
            if directory_path not in self._directories_list:
                self._directories_list.append(directory_path)
        self._update_qlist()

    def _remove_selected_button_pressed(self) -> None:
        selected_items = self._directories_q_list.selectedItems()
        if not selected_items:
            return
        for item in selected_items:
            item_path = item.data(Qt.ItemDataRole.UserRole)
            if item_path in self._directories_list:
                self._directories_list.remove(item_path)
        self._update_qlist()

    def _stitch_button_pressed(self) -> None:
        if not self._directories_list:
            return
        stitched_ok = stitch_directories(self._directories_list)
        expected_outputs = [
            get_stitched_output_path(directory)
            for directory in self._directories_list
        ]
        all_created = stitched_ok and all(
            os.path.exists(path) for path in expected_outputs
        )
        self._set_files_created_label_state(all_created)

    def _set_files_created_label_state(self, state: bool) -> None:
        if state:
            self._files_created_status_label.setText("Files created")
            self._files_created_status_label.setStyleSheet("color: green")
        else:
            self._files_created_status_label.setText("Files not created")
            self._files_created_status_label.setStyleSheet("color: red")

    def _update_qlist(self) -> None:
        self._directories_q_list.clear()
        for directory_path in self._directories_list:
            dir_name = Path(directory_path).name
            q_list_item: QListWidgetItem = QListWidgetItem(dir_name)
            q_list_item.setData(Qt.ItemDataRole.UserRole, directory_path)
            self._directories_q_list.addItem(q_list_item)
