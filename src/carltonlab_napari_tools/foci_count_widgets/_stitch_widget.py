import shutil
from pathlib import Path
from typing import TYPE_CHECKING, cast

from napari.utils.notifications import show_error
from qtpy.QtCore import QSize, Qt
from qtpy.QtGui import QIcon
from qtpy.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from carltonlab_napari_tools._protocols import (
    CToolButton,
    MainWidgetCallBacks,
)
from carltonlab_napari_tools._shared_variables import (
    CLSP_PROJECT_SUFFIX,
    SUPPORTED_STITCH_EXTENSIONS,
    TILES_DIR_NAME,
)
from carltonlab_napari_tools._shared_widgets import (
    FrameSeparator,
    KeepChannelsWidget,
    get_directories,
)
from carltonlab_napari_tools._utils import (
    create_project_structure,
    get_common_prefix,
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
        self._directories_list: list[Path] = []

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

        self._main_title_label = QLabel("CLT Stitch images")
        self._main_title_label.setStyleSheet(
            "font-weight: bold; font-size: 20px"
        )
        self._main_title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._main_layout.addWidget(self._main_title_label)

        self._main_layout.addWidget(FrameSeparator(parent=self))

        self._keep_channels_widget = KeepChannelsWidget(parent=self)
        self._main_layout.addWidget(self._keep_channels_widget)

        self._main_layout.addWidget(FrameSeparator(parent=self))

        self._registration_container = QWidget()
        self._registration_layout = QFormLayout()
        self._registration_layout.setContentsMargins(0, 0, 0, 0)
        self._registration_container.setLayout(self._registration_layout)

        self._registration_channel_spinbox = QSpinBox()
        self._registration_channel_spinbox.setMinimum(0)
        self._registration_channel_spinbox.setMaximum(9999)
        self._registration_channel_spinbox.setValue(0)
        self._registration_layout.addRow(
            "Registration channel",
            self._registration_channel_spinbox,
        )

        self._registration_scale_spinbox = QSpinBox()
        self._registration_scale_spinbox.setMinimum(-1)
        self._registration_scale_spinbox.setMaximum(9999)
        self._registration_scale_spinbox.setValue(-1)
        self._registration_scale_spinbox.setSpecialValueText("Automatic")
        self._registration_layout.addRow(
            "Registration scale",
            self._registration_scale_spinbox,
        )

        self._main_layout.addWidget(self._registration_container)
        self._main_layout.addWidget(FrameSeparator(parent=self))

        self._fusion_container = QWidget()
        self._fusion_layout = QFormLayout()
        self._fusion_layout.setContentsMargins(0, 0, 0, 0)
        self._fusion_container.setLayout(self._fusion_layout)

        self._use_gpu_checkbox = QCheckBox("Use GPU")
        self._fusion_layout.addRow(self._use_gpu_checkbox)

        self._num_workers_spinbox = QSpinBox()
        self._num_workers_spinbox.setMinimum(0)
        self._num_workers_spinbox.setMaximum(9999)
        self._num_workers_spinbox.setValue(0)
        self._num_workers_spinbox.setSpecialValueText("Automatic")
        self._fusion_layout.addRow(
            "Number of workers",
            self._num_workers_spinbox,
        )

        self._n_batch_spinbox = QSpinBox()
        self._n_batch_spinbox.setMinimum(0)
        self._n_batch_spinbox.setMaximum(9999)
        self._n_batch_spinbox.setValue(0)
        self._n_batch_spinbox.setSpecialValueText("Automatic")
        self._fusion_layout.addRow(
            "Batch count",
            self._n_batch_spinbox,
        )

        self._main_layout.addWidget(self._fusion_container)
        self._main_layout.addWidget(FrameSeparator(parent=self))

        self._add_remove_container: QWidget = QWidget()
        self._add_remove_container_layout: QHBoxLayout = QHBoxLayout()
        self._add_remove_container_layout.setContentsMargins(0, 0, 0, 0)
        self._add_remove_container_layout.setSpacing(6)
        self._add_remove_container.setLayout(self._add_remove_container_layout)

        self._q_list_title: QLabel = QLabel("Image directories")
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

        self._main_layout.addWidget(FrameSeparator(parent=self))

        self._stitch_button: QPushButton = QPushButton("Stitch gonads")
        self._stitch_button.clicked.connect(self._on_stitch_button_pressed)
        self._main_layout.addWidget(self._stitch_button)

        self._files_created_status_label: QLabel = QLabel("")
        self._main_layout.addWidget(self._files_created_status_label)
        self._set_files_created_label_state(False)

        self._main_layout.addStretch()

    def _verify_directory(self, directory_path: Path) -> bool:
        has_existing_project = any(
            path.is_dir() and path.name.endswith(CLSP_PROJECT_SUFFIX)
            for path in directory_path.iterdir()
        )
        if has_existing_project:
            return True

        files_only = [
            p
            for p in directory_path.iterdir()
            if p.is_file() or p.name.endswith(".ome.zarr")
        ]
        if not files_only:
            show_error(
                f"The directory {directory_path} does not contain any files"
            )
            return False
        suffix_set = {
            ".ome.zarr" if p.name.endswith(".ome.zarr") else p.suffix
            for p in files_only
        }
        if len(suffix_set) != 1:
            show_error(
                f"The directory {directory_path}\nhas multiple suffixes"
            )
            return False
        suffix = list(suffix_set)[0]
        if suffix not in SUPPORTED_STITCH_EXTENSIONS:
            show_error(f"The suffix {suffix} is not supported")
            return False
        return True

    def _add_directory_button_pressed(self) -> None:
        directories_path_list: list[Path] | None = get_directories(
            self, caption="Select the directories"
        )
        if directories_path_list is None:
            return
        for directory_path in directories_path_list:
            if (
                directory_path not in self._directories_list
                and self._verify_directory(directory_path)
            ):
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

    def _get_project_name(self, directory_path: Path) -> str:
        image_names: list[str] = []

        for image_path in directory_path.iterdir():
            if not (
                image_path.is_file() or image_path.name.endswith(".ome.zarr")
            ):
                continue

            image_name = image_path.name
            for extension in SUPPORTED_STITCH_EXTENSIONS:
                if image_name.endswith(extension):
                    image_name = image_name[: -len(extension)]
                    break

            image_names.append(image_name)

        project_base_name = get_common_prefix(image_names)
        if not project_base_name:
            project_base_name = directory_path.name

        return f"{project_base_name}{CLSP_PROJECT_SUFFIX}"

    def _move_tiles(
        self,
        project_base_dir: Path,
        project_path: Path,
    ) -> bool:
        tiles_path = project_path / TILES_DIR_NAME

        image_paths = [
            image_path
            for image_path in project_base_dir.iterdir()
            if (
                image_path.name.endswith(".ome.zarr")
                or (
                    image_path.is_file()
                    and any(
                        image_path.name.endswith(extension)
                        for extension in SUPPORTED_STITCH_EXTENSIONS
                    )
                )
            )
        ]

        if not image_paths:
            show_error(f"No image tiles found in {project_base_dir}")
            return False

        destination_paths = [
            tiles_path / image_path.name for image_path in image_paths
        ]
        if any(destination.exists() for destination in destination_paths):
            show_error(
                f"One or more tile destinations already exist in {tiles_path}"
            )
            return False

        try:
            for image_path in image_paths:
                shutil.move(str(image_path), str(tiles_path / image_path.name))
        except OSError as exc:
            show_error(f"Could not move tiles from {project_base_dir}: {exc}")
            return False

        return True

    def _on_stitch_button_pressed(self) -> None:
        if not self._directories_list:
            return

        for starting_project in self._directories_list:
            existing_projects = [
                path
                for path in starting_project.iterdir()
                if path.is_dir() and path.name.endswith(CLSP_PROJECT_SUFFIX)
            ]

            if existing_projects:
                project_path = existing_projects[0]
            else:
                project_name = self._get_project_name(starting_project)
                project_path = starting_project / project_name
                if not create_project_structure(project_path, "clsp"):
                    continue

            tiles_path = project_path / TILES_DIR_NAME
            if tiles_path.is_dir() and not any(tiles_path.iterdir()):
                self._move_tiles(starting_project, project_path)

        return

    def get_stitching_options(
        self,
    ) -> dict[str, int | bool | None]:
        registration_scale = self._registration_scale_spinbox.value()
        num_workers = self._num_workers_spinbox.value()
        n_batch = self._n_batch_spinbox.value()

        return {
            "registration_channel": (
                self._registration_channel_spinbox.value()
            ),
            "registration_scale": (
                None if registration_scale < 0 else registration_scale
            ),
            "num_workers": None if num_workers == 0 else num_workers,
            "n_batch": None if n_batch == 0 else n_batch,
            "use_gpu": self._use_gpu_checkbox.isChecked(),
        }

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
