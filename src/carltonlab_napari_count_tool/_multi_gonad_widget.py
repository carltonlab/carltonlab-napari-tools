import os
from typing import TYPE_CHECKING, cast

from napari.utils.notifications import show_info
from qtpy.QtCore import Qt
from qtpy.QtWidgets import (
    QAbstractItemView,
    QFrame,
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

from carltonlab_napari_count_tool._multi_gonad_widget_model import (
    create_project_file,
    file_available,
    make_directories_dict,
)
from carltonlab_napari_count_tool._protocols import MainWidgetCallBacks
from carltonlab_napari_count_tool._shared_variables import (
    MULTI_GONAD_FILE_EXTENSION,
    MULTI_GONAD_FILE_SUFFIX,
)
from carltonlab_napari_count_tool._shared_widgets import (
    get_clsp_directories,
    get_directory,
)

if TYPE_CHECKING:
    from napari.viewer import ViewerModel

BUTTONS_WIDTH = 30


class MakeMultiGonadWidget(QWidget):
    def __init__(
        self,
        napari_viewer: "ViewerModel",
        parent_widget: MainWidgetCallBacks,
    ):
        parent_q_widget: QWidget = cast(QWidget, parent_widget)
        super().__init__(parent_q_widget)

        self._napari_viewer = napari_viewer
        self._parent_widget: MainWidgetCallBacks = parent_widget
        self._gonads_directories_dict: dict[str, str] = {}
        self._project_file_created: bool = False
        self._project_file_directory: str = ""
        self._project_file_name: str = ""

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

        self._main_title_label = QLabel("CL Create Multi Gonad Project")
        self._main_title_label.setStyleSheet(
            "font-weight: bold; font-size: 20px"
        )
        self._main_title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._main_layout.addWidget(self._main_title_label)

        self._add_remove_container: QWidget = QWidget()
        self._add_remove_container_layout: QHBoxLayout = QHBoxLayout()
        self._add_remove_container_layout.setContentsMargins(0, 0, 0, 0)
        self._add_remove_container.setLayout(self._add_remove_container_layout)

        self._q_list_title: QLabel = QLabel("Gonad files")
        self._q_list_title.setStyleSheet("font-weight: bold")
        self._q_list_title.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        self._add_remove_container_layout.addWidget(self._q_list_title)

        self._add_gonads_button: QPushButton = QPushButton("+")
        self._add_gonads_button.setFixedWidth(BUTTONS_WIDTH)
        self._add_gonads_button.clicked.connect(
            self._add_gonads_button_pressed
        )
        self._add_remove_container_layout.addWidget(self._add_gonads_button)

        self._remove_gonads_button: QPushButton = QPushButton("-")
        self._remove_gonads_button.setFixedWidth(BUTTONS_WIDTH)
        self._remove_gonads_button.clicked.connect(
            self._remove_gonads_button_pressed
        )
        self._add_remove_container_layout.addWidget(self._remove_gonads_button)

        self._main_layout.addWidget(self._add_remove_container)

        self._gonad_directories_q_list: QListWidget = QListWidget()
        self._gonad_directories_q_list.setSelectionMode(
            QAbstractItemView.SelectionMode.MultiSelection
        )

        self._list_scroll_area: QScrollArea = QScrollArea()
        self._list_scroll_area.setWidgetResizable(True)
        self._list_scroll_area.setFixedHeight(300)

        list_container: QWidget = QWidget()
        list_container_layout = QVBoxLayout()
        list_container_layout.setContentsMargins(0, 0, 0, 0)
        list_container.setLayout(list_container_layout)
        list_container_layout.addWidget(self._gonad_directories_q_list)

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

        self._project_directory_container: QWidget = QWidget()
        self._project_directory_container_layout = QVBoxLayout()
        self._project_directory_container_layout.setContentsMargins(
            12, 0, 12, 0
        )
        self._project_directory_container.setLayout(
            self._project_directory_container_layout
        )
        self._main_layout.addWidget(self._project_directory_container)

        self._project_file_directory_title: QLabel = QLabel(
            "Project file directory"
        )
        self._project_file_directory_title.setStyleSheet("font-weight: bold")
        self._project_directory_container_layout.addWidget(
            self._project_file_directory_title
        )

        self._project_file_line_edit: QLineEdit = QLineEdit("")
        self._project_file_line_edit.setDisabled(True)
        self._project_directory_container_layout.addWidget(
            self._project_file_line_edit
        )

        self._select_project_directory_button: QPushButton = QPushButton(
            "Select saving directory"
        )
        self._select_project_directory_button.clicked.connect(
            self._select_project_directory_button_pressed
        )
        self._project_directory_container_layout.addWidget(
            self._select_project_directory_button
        )
        self._main_layout.addSpacing(6)
        separator = QFrame(self._main_container)
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setFrameShadow(QFrame.Shadow.Sunken)
        separator.setStyleSheet("background-color: gray;")
        separator.setFixedHeight(2)
        self._main_layout.addWidget(separator)
        self._main_layout.addSpacing(6)

        self._project_root_container: QWidget = QWidget()
        self._project_root_container_layout = QVBoxLayout()
        self._project_root_container_layout.setContentsMargins(12, 0, 12, 0)
        self._project_root_container.setLayout(
            self._project_root_container_layout
        )
        self._main_layout.addWidget(self._project_root_container)

        self._project_file_root_title: QLabel = QLabel("Project root name")
        self._project_file_root_title.setStyleSheet("font-weight: bold")
        self._project_root_container_layout.addWidget(
            self._project_file_root_title
        )

        self._project_root_name_line_edit: QLineEdit = QLineEdit("")
        self._project_root_name_line_edit.editingFinished.connect(
            self._validate_root_name_directory
        )
        self._project_root_container_layout.addWidget(
            self._project_root_name_line_edit
        )
        self._main_layout.addSpacing(6)
        separator = QFrame(self._main_container)
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setFrameShadow(QFrame.Shadow.Sunken)
        separator.setStyleSheet("background-color: gray;")
        separator.setFixedHeight(2)
        self._main_layout.addWidget(separator)
        self._main_layout.addSpacing(6)

        self._project_name_container: QWidget = QWidget()
        self._project_name_container_layout = QVBoxLayout()
        self._project_name_container_layout.setContentsMargins(12, 0, 12, 0)
        self._project_name_container.setLayout(
            self._project_name_container_layout
        )
        self._main_layout.addWidget(self._project_name_container)

        self._project_file_name_title: QLabel = QLabel("Project file name")
        self._project_file_name_title.setStyleSheet("font-weight: bold")
        self._project_name_container_layout.addWidget(
            self._project_file_name_title
        )

        self._project_file_name_line_edit: QLineEdit = QLineEdit("")
        self._project_file_name_line_edit.setDisabled(True)
        self._project_name_container_layout.addWidget(
            self._project_file_name_line_edit
        )

        self._project_file_valid_status_label: QLabel = QLabel("")
        self._project_name_container_layout.addWidget(
            self._project_file_valid_status_label
        )
        self._main_layout.addSpacing(6)
        separator = QFrame(self._main_container)
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setFrameShadow(QFrame.Shadow.Sunken)
        separator.setStyleSheet("background-color: gray;")
        separator.setFixedHeight(2)
        self._main_layout.addWidget(separator)
        self._main_layout.addSpacing(6)

        self._create_project_container: QWidget = QWidget()
        self._create_project_container_layout = QVBoxLayout()
        self._create_project_container_layout.setContentsMargins(12, 0, 12, 0)
        self._create_project_container.setLayout(
            self._create_project_container_layout
        )
        self._main_layout.addWidget(self._create_project_container)

        self._create_project_button: QPushButton = QPushButton(
            "Create project"
        )
        self._create_project_button.clicked.connect(
            self._create_project_button_pressed
        )
        self._create_project_container_layout.addWidget(
            self._create_project_button
        )

        self._project_file_created_label: QLabel = QLabel("")
        self._create_project_container_layout.addWidget(
            self._project_file_created_label
        )

        self._main_layout.addSpacing(6)
        separator = QFrame(self._main_container)
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setFrameShadow(QFrame.Shadow.Sunken)
        separator.setStyleSheet("background-color: gray;")
        separator.setFixedHeight(2)
        self._main_layout.addWidget(separator)
        self._main_layout.addSpacing(6)

        self._new_project_container: QWidget = QWidget()
        self._new_project_container_layout = QVBoxLayout()
        self._new_project_container_layout.setContentsMargins(12, 0, 12, 0)
        self._new_project_container.setLayout(
            self._new_project_container_layout
        )
        self._main_layout.addWidget(self._new_project_container)

        self._create_new_project_button: QPushButton = QPushButton(
            "Create new project"
        )
        self._create_new_project_button.clicked.connect(
            self._create_new_project_button_pressed
        )
        self._new_project_container_layout.addWidget(
            self._create_new_project_button
        )

        self._main_layout.addStretch(1)

        self._update_project_file_created_state()
        self._validate_root_name_directory()
        self._update_qlist()

    def _reset_gui(self) -> None:
        self._gonads_directories_dict = {}
        self._project_file_created = False
        self._project_file_directory = ""
        self._project_file_name = ""
        self._gonad_directories_q_list.clear()
        self._project_file_line_edit.setText("")
        self._project_root_name_line_edit.setText("")
        self._project_file_name_line_edit.setText("")
        self._project_file_valid_status_label.setText("")
        self._create_project_button.setEnabled(True)
        self._update_project_file_created_state()
        self._validate_root_name_directory()

    def _create_new_project_button_pressed(self) -> None:
        self._reset_gui()

    def _update_project_file_created_state(self) -> None:
        if self._project_file_created:
            self._project_file_created_label.setText("Project file created")
            self._project_file_created_label.setStyleSheet("color: green")
        else:
            self._project_file_created_label.setText(
                "Project file not created"
            )
            self._project_file_created_label.setStyleSheet("color: red")
        return

    def _validate_root_name_directory(self) -> None:
        if self._project_root_name_line_edit.text() == "":
            self._project_file_valid_status_label.setText(
                "Type a file root name"
            )
            self._project_file_valid_status_label.setStyleSheet("color: red")
            self._project_file_name = ""
            return
        if self._project_file_line_edit.text() == "":
            self._project_file_valid_status_label.setText(
                "Select a saving directory"
            )
            self._project_file_valid_status_label.setStyleSheet("color: red")
            self._project_file_name = ""
            return
        complete_file_name: str = (
            MULTI_GONAD_FILE_SUFFIX
            + self._project_root_name_line_edit.text()
            + MULTI_GONAD_FILE_EXTENSION
        )
        project_file_path: str = os.path.join(
            self._project_file_line_edit.text(), complete_file_name
        )
        if file_available(project_file_path):
            self._project_file_valid_status_label.setText("Valid file name")
            self._project_file_valid_status_label.setStyleSheet("color: green")
            self._project_file_name_line_edit.setText(complete_file_name)
            self._project_file_name = complete_file_name
        else:
            self._project_file_valid_status_label.setText("Invalid file name")
            self._project_file_valid_status_label.setStyleSheet("color: red")
            self._project_file_name_line_edit.setText("")
            self._project_file_name = ""
        return

    def _update_qlist(self) -> None:
        q_list = self._gonad_directories_q_list
        q_list.clear()
        for dir_name, dir_path in self._gonads_directories_dict.items():
            q_list_item: QListWidgetItem = QListWidgetItem(dir_name)
            q_list_item.setData(Qt.ItemDataRole.UserRole, dir_path)
            q_list.addItem(q_list_item)
        return

    def _add_gonads_button_pressed(self) -> None:
        directories = get_clsp_directories(self, "Select *_clsp directories")
        if directories is None:
            return
        if directories == "non-clsp":
            show_info("Directories with no projects were selected. ERROR")
            return
        new_dictionary: dict[str, str] = make_directories_dict(
            self._gonads_directories_dict.copy(), directories
        )
        self._gonads_directories_dict = new_dictionary
        self._update_qlist()

    def _remove_gonads_button_pressed(self) -> None:
        removing_keys = [
            item.text()
            for item in self._gonad_directories_q_list.selectedItems()
        ]
        for removing_key in removing_keys:
            self._gonads_directories_dict.pop(removing_key)
        self._update_qlist()
        return

    def _select_project_directory_button_pressed(self) -> None:
        selected_dir = get_directory(self, "Select saving directory")
        if selected_dir is not None:
            self._project_file_line_edit.setText(selected_dir)
            self._project_file_directory = selected_dir
        else:
            self._project_file_line_edit.setText("")
            self._project_file_directory = ""
        return

    def _create_project_button_pressed(self) -> None:
        if self._project_file_name == "":
            show_info("No file name is set. ERROR")
            return
        if self._project_file_directory == "":
            show_info("No saving directory set. ERROR")
        project_path: str = os.path.join(
            self._project_file_directory, self._project_file_name
        )
        if create_project_file(self._gonads_directories_dict, project_path):
            show_info("Project file created")
            self._project_file_created = True
            self._update_project_file_created_state()
            self._create_project_button.setEnabled(False)
        else:
            show_info("Project file not created.ERROR")
        return
