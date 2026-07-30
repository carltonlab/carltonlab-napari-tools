import os
from pathlib import Path
from typing import TYPE_CHECKING, Literal, cast

from qtpy.QtCore import QSize, Qt
from qtpy.QtGui import QColor, QIcon
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

from carltonlab_napari_tools._extract_channel_widget_model import (
    extract_channels,
    get_file_type,
    parse_string_for_channels,
)
from carltonlab_napari_tools._protocols import (
    CToolButton,
    MainWidgetCallBacks,
)
from carltonlab_napari_tools._shared_widgets import (
    add_separator_to_container,
    get_directories,
    get_directory,
    get_files,
)

if TYPE_CHECKING:
    from napari.viewer import ViewerModel

BUTTONS_WIDTH = 30
ICONS_DIR = Path(__file__).resolve().parent / "assets" / "icons"
ADD_DIR_ICON = ICONS_DIR / "add_dir.svg"
ADD_FILE_ICON = ICONS_DIR / "add_file.svg"
REMOVE_ICON = ICONS_DIR / "remove.svg"


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
        self._add_remove_container_layout.setSpacing(6)
        self._add_remove_container_layout.setContentsMargins(0, 0, 0, 0)
        self._add_remove_container.setLayout(self._add_remove_container_layout)

        self._q_list_title: QLabel = QLabel("Image directories or files")
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

        self._add_file_button: QPushButton = QPushButton("")
        self._add_file_button.setIcon(QIcon(str(ADD_FILE_ICON)))
        self._add_file_button.setFixedSize(BUTTONS_WIDTH, BUTTONS_WIDTH)
        self._add_file_button.setIconSize(
            QSize(BUTTONS_WIDTH - 6, BUTTONS_WIDTH - 6)
        )
        self._add_file_button.clicked.connect(self._add_file_button_pressed)
        self._add_remove_container_layout.addWidget(self._add_file_button)

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

        self._file_directory_q_list: QListWidget = QListWidget()
        self._file_directory_q_list.setSelectionMode(
            QAbstractItemView.SelectionMode.MultiSelection
        )
        self._file_directory_q_list.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        self._main_layout.addWidget(self._file_directory_q_list)

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

        self._example_label: QLabel = QLabel("(e.g. 1-2,4)")
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
        self._set_files_created_label_state(False)
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

    def _remove_selected_button_pressed(self) -> None:
        selected_items = self._file_directory_q_list.selectedItems()
        if not selected_items:
            return
        for item in selected_items:
            item_text = item.text()
            item_path = item.data(Qt.ItemDataRole.UserRole)
            if (
                item_text.endswith(" --- dir")
                and item_path in self._image_directories_list
            ):
                self._image_directories_list.remove(item_path)
            elif (
                item_text.endswith(" --- file")
                and item_path in self._image_files_list
            ):
                self._image_files_list.remove(item_path)
        self._update_qlist()

    def _save_all_to_directory_checkbox_state_changed(self) -> None:
        if self._save_all_to_directory_checkbox.isChecked():
            self._saving_directory_container.setDisabled(False)
        else:
            self._saving_directory_container.setDisabled(True)

    def _select_saving_directory_button_pressed(self) -> None:
        directory_path: str | None = get_directory(
            self, caption="Select saving directory"
        )
        if directory_path is None:
            self._save_all_directory = None
            self._saving_line_edit.setText("")
            return
        self._save_all_directory = directory_path
        self._saving_line_edit.setText(directory_path)

    def _keeping_channels_line_edited(self) -> None:
        user_text = self._keeping_channels_line_edit.text()
        if user_text == "":
            return
        if not all(character in "0123456789-," for character in user_text):
            self._keeping_channels_line_edit.setText("")
            return

    def _extract_channels_button_pressed(self) -> None:
        channels_text = self._keeping_channels_line_edit.text().strip()
        if channels_text == "":
            return
        if (
            self._save_all_to_directory_checkbox.isChecked()
            and self._saving_line_edit.text().strip() == ""
        ):
            return
        save_directory: str | None = None
        if self._save_all_to_directory_checkbox.isChecked():
            if self._save_all_directory is None or not os.path.isdir(
                self._save_all_directory
            ):
                return
            save_directory = self._save_all_directory
        extract_channels(
            self._image_files_list,
            self._image_directories_list,
            channels_text,
            save_directory=save_directory,
        )
        expected_paths = self._get_expected_output_paths(
            channels_text, save_directory
        )
        print(f"expected output count: {len(expected_paths)}")
        for path in expected_paths:
            print(f"expected output: {path} exists={os.path.exists(path)}")
        all_created = len(expected_paths) > 0 and all(
            os.path.exists(path) for path in expected_paths
        )
        self._set_files_created_label_state(all_created)
        return

    def _get_expected_output_paths(
        self, channels_text: str, save_directory: str | None
    ) -> list[str]:
        channels_raw = parse_string_for_channels(channels_text)
        if len(channels_raw) == 0:
            return []
        input_paths: list[str] = []
        input_paths.extend(self._image_files_list)
        patterns = [
            "*.dv",
            "*.DV",
            "*.dv_add_decon",
            "*.zs",
            "*.deconzs",
            "*.tif",
            "*.tiff",
            "*.zarr",
        ]
        for directory in self._image_directories_list:
            path = Path(directory)
            if not path.is_dir():
                continue
            for pattern in patterns:
                for found_path in path.rglob(pattern):
                    if (
                        found_path.suffix == ".zarr"
                        and not found_path.is_dir()
                    ):
                        continue
                    input_paths.append(str(found_path))
        expected_paths: list[str] = []
        for file_path in input_paths:
            file_type = get_file_type(file_path)
            if file_type == "dir" or file_type == "fail":
                continue
            if "_extracted_channels" in Path(file_path).name:
                continue
            path_obj = Path(file_path)
            if path_obj.suffix == ".zarr" and path_obj.name.endswith(
                ".ome.zarr"
            ):
                file_name_no_ext = path_obj.name[: -len(".ome.zarr")]
            else:
                file_name_no_ext = path_obj.stem
            channels_string = "_extracted_channels"
            for channel in channels_raw:
                channels_string += f"_{channel}"
            saving_file_name = f"{file_name_no_ext}{channels_string}.ome.zarr"
            saving_dir = save_directory or os.path.dirname(file_path)
            expected_paths.append(os.path.join(saving_dir, saving_file_name))
        return expected_paths

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
        path_object: Path = Path(path)
        file_name: str = path_object.name
        q_list_item: QListWidgetItem = QListWidgetItem(
            f"{file_name} --- {file_type}"
        )
        if file_type == "dir":
            q_list_item.setForeground(QColor("#27ADF5"))
        if file_type == "file":
            q_list_item.setForeground(QColor("#F7A02F"))
        q_list_item.setData(Qt.ItemDataRole.UserRole, path)
        self._file_directory_q_list.addItem(q_list_item)

    def _update_qlist(self) -> None:
        self._file_directory_q_list.clear()
        for directory_path in self._image_directories_list:
            self._add_q_list_item(directory_path, "dir")
        for file_path in self._image_files_list:
            self._add_q_list_item(file_path, "file")
        return
