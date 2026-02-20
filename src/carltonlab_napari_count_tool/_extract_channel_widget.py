from pathlib import Path
from typing import TYPE_CHECKING, Literal, cast

from qtpy.QtCore import Qt
from qtpy.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from carltonlab_napari_count_tool._protocols import (
    CToolButton,
    MainWidgetCallBacks,
)
from carltonlab_napari_count_tool._shared_widgets import (
    add_separator_to_container,
    get_directories,
    get_files,
)

if TYPE_CHECKING:
    from napari.viewer import ViewerModel

BUTTONS_WIDTH = 30


class ExctractChannelsWidget(QWidget):
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
        self._image_directories_list: list[str] = []
        self._image_files_list: list[str] = []
        self._save_all_directory: str | None = None

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

        self._main_title_label = QLabel("CL Extract Channels")
        self._main_title_label.setStyleSheet(
            "font-weight: bold; font-size: 20px"
        )
        self._main_title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._main_layout.addWidget(self._main_title_label)

        self._add_remove_container: QWidget = QWidget()
        self._add_remove_container_layout: QHBoxLayout = QHBoxLayout()
        self._add_remove_container_layout.setContentsMargins(0, 0, 0, 0)
        self._add_remove_container.setLayout(self._add_remove_container_layout)

        self._q_list_title: QLabel = QLabel("Image directories or files")
        self._q_list_title.setStyleSheet("font-weight: bold")
        self._q_list_title.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        self._add_remove_container_layout.addWidget(self._q_list_title)

        self._add_remove_container_dir_label: QLabel = QLabel("Dirs")
        self._add_remove_container_layout.addWidget(
            self._add_remove_container_dir_label
        )

        self._add_directory_button: QPushButton = QPushButton("+")
        self._add_directory_button.setFixedWidth(BUTTONS_WIDTH)
        self._add_directory_button.clicked.connect(
            self._add_directory_button_pressed
        )
        self._add_remove_container_layout.addWidget(self._add_directory_button)

        self._remove_directory_button: QPushButton = QPushButton("-")
        self._remove_directory_button.setFixedWidth(BUTTONS_WIDTH)
        self._remove_directory_button.clicked.connect(
            self._remove_directory_button_pressed
        )
        self._add_remove_container_layout.addWidget(
            self._remove_directory_button
        )

        self._add_remove_container_file_label: QLabel = QLabel("Files")
        self._add_remove_container_layout.addWidget(
            self._add_remove_container_file_label
        )

        self._add_file_button: QPushButton = QPushButton("+")
        self._add_file_button.setFixedWidth(BUTTONS_WIDTH)
        self._add_file_button.clicked.connect(self._add_file_button_pressed)
        self._add_remove_container_layout.addWidget(self._add_file_button)

        self._remove_file_button: QPushButton = QPushButton("-")
        self._remove_file_button.setFixedWidth(BUTTONS_WIDTH)
        self._remove_file_button.clicked.connect(
            self._remove_file_button_pressed
        )
        self._add_remove_container_layout.addWidget(self._remove_file_button)

        self._main_layout.addWidget(self._add_remove_container)

        self._file_directory_q_list: QListWidget = QListWidget()
        self._file_directory_q_list.setSelectionMode(
            QAbstractItemView.SelectionMode.MultiSelection
        )

        self._list_scroll_area: QScrollArea = QScrollArea()
        self._list_scroll_area.setWidgetResizable(True)
        self._list_scroll_area.setFixedHeight(300)

        list_container: QWidget = QWidget()
        list_container_layout = QVBoxLayout()
        list_container_layout.setContentsMargins(0, 0, 0, 0)
        list_container.setLayout(list_container_layout)
        list_container_layout.addWidget(self._file_directory_q_list)

        self._list_scroll_area.setWidget(list_container)
        self._main_layout.addWidget(self._list_scroll_area)

        add_separator_to_container(self._main_container, "horizontal")

        self._save_all_to_directory_checkbox: QCheckBox = QCheckBox(
            "Save to specified directory"
        )
        self._save_all_to_directory_checkbox.setChecked(True)
        self._save_all_to_directory_checkbox.stateChanged.connect(
            self._save_all_to_directory_checkbox_state_changed
        )
        self._main_layout.addWidget(self._save_all_to_directory_checkbox)

        self._saving_directory_container: QWidget = QWidget()
        self._saving_directory_container_layout = QVBoxLayout()
        self._saving_directory_container_layout.setContentsMargins(
            12, 0, 12, 0
        )
        self._saving_directory_container.setLayout(
            self._saving_directory_container_layout
        )
        self._main_layout.addWidget(self._saving_directory_container)

        self._saving_directory_title: QLabel = QLabel("Save at directory")
        self._saving_directory_title.setStyleSheet("font-weight: bold")
        self._saving_directory_container_layout.addWidget(
            self._saving_directory_title
        )

        self._saving_line_edit: QLineEdit = QLineEdit("")
        self._saving_line_edit.setDisabled(True)
        self._saving_directory_container_layout.addWidget(
            self._saving_line_edit
        )

        self._select_saving_directory_button: QPushButton = QPushButton(
            "Select saving directory"
        )
        self._select_saving_directory_button.clicked.connect(
            self._select_saving_directory_button_pressed
        )
        self._saving_directory_container_layout.addWidget(
            self._select_saving_directory_button
        )

        add_separator_to_container(self._main_container, "horizontal")

        self._keeping_channels_container: QWidget = QWidget()
        self._keeping_channels_container_layout = QVBoxLayout()
        self._keeping_channels_container_layout.setContentsMargins(
            12, 0, 12, 0
        )
        self._keeping_channels_container.setLayout(
            self._keeping_channels_container_layout
        )
        self._main_layout.addWidget(self._keeping_channels_container)

        self._keeping_channels_title: QLabel = QLabel("Keeping channels")
        self._keeping_channels_title.setStyleSheet("font-weight: bold")
        self._keeping_channels_container_layout.addWidget(
            self._keeping_channels_title
        )

        self._keeping_channels_line_edit_horizontal_container = QWidget()
        self._keeping_channels_line_edit_horizontal_container_layout = (
            QHBoxLayout()
        )
        self._keeping_channels_line_edit_horizontal_container_layout.setContentsMargins(
            0, 0, 0, 0
        )
        self._keeping_channels_line_edit_horizontal_container.setLayout(
            self._keeping_channels_line_edit_horizontal_container_layout
        )
        self._keeping_channels_container_layout.addWidget(
            self._keeping_channels_line_edit_horizontal_container
        )

        self._keeping_channels_line_edit: QLineEdit = QLineEdit("")
        self._keeping_channels_line_edit.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        self._keeping_channels_line_edit_horizontal_container_layout.addWidget(
            self._keeping_channels_line_edit
        )
        self._keeping_channels_line_edit.editingFinished.connect(
            self._keeping_channels_line_edited
        )

        self._example_label: QLabel = QLabel("(e.g. 1-2,4")
        self._keeping_channels_line_edit_horizontal_container_layout.addWidget(
            self._example_label
        )
        self._keeping_channels_line_edit_horizontal_container_layout.addWidget(
            self._example_label
        )

        self._extract_channels_button: QPushButton = QPushButton(
            "Extract channels"
        )
        self._extract_channels_button.clicked.connect(
            self._extract_channels_button_pressed
        )
        self._keeping_channels_container_layout.addWidget(
            self._extract_channels_button
        )

        self._files_created_status_label: QLabel = QLabel("")
        self._main_layout.addWidget(self._files_created_status_label)

        add_separator_to_container(self._main_container, "horizontal")

        self._reset_gui_button: QPushButton = QPushButton("Extract new set")
        self._reset_gui_button.clicked.connect(self._reset_gui)
        self._main_layout.addWidget(self._reset_gui_button)

        self._main_layout.addStretch()

        self._save_all_to_directory_checkbox_state_changed()
        self._set_files_created_label_state(False)
        self._update_qlist()

    def _reset_gui(self) -> None:
        self._save_all_directory = None
        self._image_directories_list = []
        self._file_directory_q_list.clear()
        self._keeping_channels_line_edit.setText("")
        self._saving_line_edit.setText("")
        return

    def _add_directory_button_pressed(self) -> None:
        directories_path_list: list[str] | None = get_directories(
            self, caption="Select the directories"
        )
        if directories_path_list is None:
            return
        for directory_path in directories_path_list:
            if directory_path not in self._image_directories_list:
                self._image_directories_list.append(directory_path)
        self._update_qlist()

    def _add_file_button_pressed(self) -> None:
        files_paths_list: list[str] | None = get_files(
            self, caption="Select the files", filters=""
        )
        if files_paths_list is None:
            return
        for file_path in files_paths_list:
            if file_path not in self._image_files_list:
                self._image_files_list.append(file_path)
        self._update_qlist()

    def _remove_file_button_pressed(self) -> None:
        return

    def _remove_directory_button_pressed(self) -> None:
        return

    def _save_all_to_directory_checkbox_state_changed(self) -> None:
        if self._save_all_to_directory_checkbox.isChecked():
            self._saving_directory_container.setDisabled(True)
        else:
            self._saving_directory_container.setDisabled(False)

    def _select_saving_directory_button_pressed(self) -> None:
        return

    def _keeping_channels_line_edited(self) -> None:
        return

    def _extract_channels_button_pressed(self) -> None:
        return

    def _set_files_created_label_state(self, state: bool) -> None:
        if state:
            self._files_created_status_label.setText("Files created")
            self._files_created_status_label.setStyleSheet("color: green")
        else:
            self._files_created_status_label.setText("Files not created")
            self._files_created_status_label.setStyleSheet("color: red")

    def _add_q_list_item(
        self, path: str, file_type: Literal["dir", "file"]
    ) -> None:
        adding_widget = QWidget()
        adding_widget_layout = QHBoxLayout()
        adding_widget_layout.setContentsMargins(3, 4, 3, 4)
        adding_widget.setLayout(adding_widget_layout)
        path_object: Path = Path(path)
        file_name: str = path_object.name
        adding_q_label: QLabel = QLabel(file_name)
        adding_q_label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        adding_widget_layout.addWidget(adding_q_label)
        adding_type_label: QLabel = QLabel(file_type)
        if file_type == "dir":
            adding_type_label.setStyleSheet(
                "font-weight: italic; color: #27ADF5"
            )
        if file_type == "file":
            adding_type_label.setStyleSheet("font-weight: italic; color: red")
        adding_widget_layout.addWidget(adding_type_label)
        q_list_item: QListWidgetItem = QListWidgetItem()
        q_list_item.setData(Qt.ItemDataRole.UserRole, path)
        q_list_item.setSizeHint(adding_widget.sizeHint())
        self._file_directory_q_list.addItem(q_list_item)
        self._file_directory_q_list.setItemWidget(q_list_item, adding_widget)

    def _update_qlist(self) -> None:
        self._file_directory_q_list.clear()
        for directory_path in self._image_directories_list:
            self._add_q_list_item(directory_path, "dir")
        for file_path in self._image_files_list:
            self._add_q_list_item(file_path, "file")
        return
