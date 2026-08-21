import configparser
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
    EXTRACTED_CHANNELS_FILE_NAME,
    STITCHED_IMAGE_DIR_NAME,
    SUPPORTED_STITCH_EXTENSIONS,
    TILES_CONFIG_FILE_NAME,
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
    parse_channel_string,
)
from carltonlab_napari_tools.channel_extraction import (
    extract_channels_to_ome_zarr,
)
from carltonlab_napari_tools.image_stitching import (
    stitch_ome_zarr_images,
)

if TYPE_CHECKING:
    from napari.viewer import ViewerModel

BUTTONS_WIDTH = 30
ICONS_DIR = Path(__file__).resolve().parent.parent / "assets" / "icons"
ADD_DIR_ICON = ICONS_DIR / "add_dir.svg"
REMOVE_ICON = ICONS_DIR / "remove.svg"


class StitchProjectStatusRow(QWidget):
    _status_button_stylesheet = (
        "QPushButton {{ border: 1px solid gray; border-radius: 4px; "
        "background-color: palette(button); font-weight: bold; "
        "color: {color}; }}"
    )

    def __init__(
        self,
        display_name: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)

        layout = QHBoxLayout()
        layout.setContentsMargins(4, 0, 4, 0)
        layout.setSpacing(4)
        self.setLayout(layout)

        name_label = QLabel(display_name)
        name_label.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Preferred,
        )
        layout.addWidget(name_label)

        self._extraction_status_button = QPushButton("Ex")
        self._stitching_status_button = QPushButton("St")

        for button in (
            self._extraction_status_button,
            self._stitching_status_button,
        ):
            button.setSizePolicy(
                QSizePolicy.Policy.Preferred,
                QSizePolicy.Policy.Preferred,
            )
            layout.addWidget(button)

    def _set_status(
        self,
        button: QPushButton,
        color: str,
        tooltip: str,
        bold: bool = False,
    ) -> None:
        button.setStyleSheet(
            self._status_button_stylesheet.format(color=color)
        )
        button.setToolTip(tooltip)

    def set_extraction_status(
        self,
        color: str,
        tooltip: str,
        bold: bool = False,
    ) -> None:
        self._set_status(
            self._extraction_status_button,
            color,
            tooltip,
            bold,
        )

    def set_stitching_status(
        self,
        color: str,
        tooltip: str,
        bold: bool = False,
        text: str = "St",
    ) -> None:
        self._stitching_status_button.setText(text)
        self._set_status(
            self._stitching_status_button,
            color,
            tooltip,
            bold,
        )


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
        self._keep_channels_widget._keep_channels_cb.toggled.connect(
            self._update_qlist
        )
        self._keep_channels_widget._keep_channels_line_edit.editingFinished.connect(
            self._update_qlist
        )
        self._main_layout.addWidget(self._keep_channels_widget)

        self._main_layout.addWidget(FrameSeparator(parent=self))

        self._registration_container = QWidget()
        self._registration_layout = QFormLayout()
        self._registration_layout.setContentsMargins(0, 0, 0, 0)
        self._registration_container.setLayout(self._registration_layout)

        self._registration_channel_spinbox = QSpinBox()
        self._registration_channel_spinbox.setMinimum(1)
        self._registration_channel_spinbox.setMaximum(9999)
        self._registration_channel_spinbox.setValue(1)

        registration_channel_widget = QWidget()
        registration_channel_layout = QHBoxLayout()
        registration_channel_layout.setContentsMargins(0, 0, 0, 0)
        registration_channel_widget.setLayout(registration_channel_layout)
        registration_channel_layout.addWidget(
            self._registration_channel_spinbox
        )

        registration_channel_help = QLabel("?")
        registration_channel_help.setToolTip("Channel number is 1-based.")
        registration_channel_layout.addWidget(registration_channel_help)

        self._registration_layout.addRow(
            "Registration channel",
            registration_channel_widget,
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

        supported_entries = [
            p
            for p in directory_path.iterdir()
            if p.name.endswith(".ome.zarr")
            or (
                p.is_file()
                and any(
                    p.name.endswith(extension)
                    for extension in SUPPORTED_STITCH_EXTENSIONS
                )
            )
        ]

        if not supported_entries:
            show_error(
                f"The directory {directory_path} does not contain any files"
            )
            return False

        unsupported_files = [
            p
            for p in directory_path.iterdir()
            if p.is_file() and p not in supported_entries
        ]
        if unsupported_files:
            show_error(
                f"The directory {directory_path} contains unsupported files:\n"
                + "\n".join(str(path.name) for path in unsupported_files)
            )
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

    def _get_extracted_tile_path(
        self,
        tile_path: Path,
        channels: list[int],
    ) -> Path:
        """Return the OME-Zarr path for a tile and channel selection."""
        if tile_path.name.endswith(".ome.zarr") and not channels:
            return tile_path

        tile_name = tile_path.name

        if tile_name.endswith(".ome.zarr"):
            base_name = tile_name.removesuffix(".ome.zarr")
        else:
            base_name = tile_name
            for extension in sorted(
                SUPPORTED_STITCH_EXTENSIONS,
                key=len,
                reverse=True,
            ):
                if base_name.endswith(extension):
                    base_name = base_name[: -len(extension)]
                    break

        if "_kept_channels_" in base_name:
            base_name = base_name.split("_kept_channels_", 1)[0]

        if channels:
            channel_string = "-".join(str(channel) for channel in channels)
            base_name += f"_kept_channels_{channel_string}"

        return tile_path.with_name(f"{base_name}.ome.zarr")

    def _get_project_path(self, starting_project: Path) -> Path:
        existing_projects = [
            path
            for path in starting_project.iterdir()
            if path.is_dir() and path.name.endswith(CLSP_PROJECT_SUFFIX)
        ]

        if existing_projects:
            return existing_projects[0]

        return starting_project / self._get_project_name(starting_project)

    def _get_stored_channels(
        self,
        project_path: Path,
    ) -> str | list[int] | None:
        config_path = (
            project_path / TILES_DIR_NAME / EXTRACTED_CHANNELS_FILE_NAME
        )

        if not config_path.exists():
            return None

        config = configparser.ConfigParser()
        try:
            config.read(config_path)
            stored_channels = config.get("channels", "kept").strip()
        except (configparser.Error, OSError, ValueError):
            return None

        if stored_channels == "all":
            return "all"

        parsed_channels = parse_channel_string(stored_channels)
        if not parsed_channels:
            return None

        return parsed_channels

    def _has_stitched_image(self, project_path: Path) -> bool:
        stitched_dir = project_path / STITCHED_IMAGE_DIR_NAME
        return stitched_dir.is_dir() and any(stitched_dir.glob("*.ome.zarr"))

    def _channels_match(
        self,
        stored_channels: str | list[int] | None,
        requested_channels: list[int],
    ) -> bool:
        if stored_channels is None:
            return False

        if not requested_channels:
            return stored_channels == "all"

        return stored_channels == requested_channels

    def _format_stored_channels(
        self,
        stored_channels: str | list[int] | None,
    ) -> str:
        if stored_channels is None:
            return "unknown"
        if isinstance(stored_channels, str):
            return stored_channels
        return ",".join(str(channel) for channel in stored_channels)

    def _set_project_row_status(
        self,
        row: StitchProjectStatusRow,
        project_path: Path,
    ) -> None:
        requested_channels = self._keep_channels_widget.get_channels()
        stored_channels = self._get_stored_channels(project_path)

        if not requested_channels:
            row.set_extraction_status(
                "gray",
                "No channel extraction required",
            )
        elif stored_channels is None:
            row.set_extraction_status(
                "red",
                "Channels haven't been created",
            )
        elif self._channels_match(stored_channels, requested_channels):
            row.set_extraction_status(
                "green",
                "Channels already extracted",
            )
        else:
            row.set_extraction_status(
                "orange",
                "Incompatible channels",
                bold=True,
            )

        if not self._has_stitched_image(project_path):
            row.set_stitching_status(
                "red",
                "Stitched image hasn't been created",
            )
        elif self._channels_match(stored_channels, requested_channels):
            row.set_stitching_status(
                "green",
                "Stitch already complete",
            )
        else:
            row.set_stitching_status(
                "orange",
                "Incompatible channels",
                bold=True,
                text=f"St - {self._format_stored_channels(stored_channels)}",
            )

    def _write_tiles_config(
        self,
        tiles_path: Path,
        tile_paths: list[Path],
    ) -> bool:
        """Write the tile filenames to the project manifest."""
        tiles_config = configparser.ConfigParser()
        tiles_config["tiles"] = {
            f"file_{index}": tile_path.name
            for index, tile_path in enumerate(tile_paths)
        }

        try:
            with (tiles_path / TILES_CONFIG_FILE_NAME).open(
                "w",
                encoding="utf-8",
            ) as config_file:
                tiles_config.write(config_file)
        except OSError as exc:
            show_error(
                f"Could not write {TILES_CONFIG_FILE_NAME} in "
                f"{tiles_path}: {exc}"
            )
            return False

        return True

    def _ensure_tiles_config(self, project_path: Path) -> bool:
        """Create a tile manifest for an existing project if needed."""
        tiles_path = project_path / TILES_DIR_NAME
        config_path = tiles_path / TILES_CONFIG_FILE_NAME

        if config_path.exists():
            return True

        tile_paths = sorted(
            path
            for path in tiles_path.iterdir()
            if path.name.endswith(".ome.zarr")
            or (
                path.is_file()
                and any(
                    path.name.endswith(extension)
                    for extension in SUPPORTED_STITCH_EXTENSIONS
                )
            )
        )
        if not tile_paths:
            show_error(f"No tiles found in {tiles_path}.")
            return False

        return self._write_tiles_config(tiles_path, tile_paths)

    def _write_extracted_channels_config(
        self,
        project_path: Path,
        channels: list[int],
    ) -> bool:
        """Write the channel selection used for project extraction."""
        config = configparser.ConfigParser()
        config["channels"] = {
            "kept": (
                "all"
                if not channels
                else ",".join(str(channel) for channel in channels)
            )
        }

        config_path = (
            project_path / TILES_DIR_NAME / EXTRACTED_CHANNELS_FILE_NAME
        )
        try:
            with config_path.open("w", encoding="utf-8") as config_file:
                config.write(config_file)
        except OSError as exc:
            show_error(
                f"Could not write {config_path.name} in "
                f"{config_path.parent}: {exc}"
            )
            return False

        return True

    def _extract_project_tiles(
        self,
        project_path: Path,
        channels: list[int],
    ) -> list[Path] | None:
        """Extract project tiles and return their OME-Zarr paths."""
        tiles_path = project_path / TILES_DIR_NAME
        config_path = tiles_path / TILES_CONFIG_FILE_NAME

        if not config_path.exists():
            show_error(f"Missing {config_path.name} in {tiles_path}.")
            return None

        config = configparser.ConfigParser()
        try:
            config.read(config_path)
            tile_names = [filename for _, filename in config.items("tiles")]
        except (configparser.Error, OSError, ValueError) as exc:
            show_error(f"Could not read {config_path.name}: {exc}")
            return None

        if not tile_names:
            show_error(f"No tiles listed in {config_path.name}.")
            return None

        tile_paths = [tiles_path / filename for filename in tile_names]
        missing_paths = [
            tile_path for tile_path in tile_paths if not tile_path.exists()
        ]
        if missing_paths:
            show_error(
                "The tile configuration contains missing files:\n"
                + "\n".join(str(path) for path in missing_paths)
            )
            return None

        extracted_paths: list[Path] = []
        for tile_number, tile_path in enumerate(tile_paths, start=1):
            output_path = self._get_extracted_tile_path(
                tile_path,
                channels,
            )

            if output_path in extracted_paths:
                continue

            if output_path.exists():
                extracted_paths.append(output_path)
                continue

            print(
                f"\nExtracting tile: {output_path.name} "
                f"({tile_number}/{len(tile_paths)})",
                flush=True,
            )
            if not extract_channels_to_ome_zarr(
                tile_path,
                output_path,
                channels,
            ):
                return None

            print("Done extracting tile\n", flush=True)
            extracted_paths.append(output_path)

        if not self._write_extracted_channels_config(
            project_path,
            channels,
        ):
            return None

        return extracted_paths

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

        return self._write_tiles_config(tiles_path, image_paths)

    def _on_stitch_button_pressed(self) -> None:
        if not self._directories_list:
            return

        project_paths: list[Path] = []

        for starting_project in self._directories_list:
            project_path = self._get_project_path(starting_project)

            if not create_project_structure(project_path, "clsp"):
                continue

            tiles_path = project_path / TILES_DIR_NAME
            if (
                tiles_path.is_dir()
                and not any(tiles_path.iterdir())
                and not self._move_tiles(starting_project, project_path)
            ):
                continue

            if not self._ensure_tiles_config(project_path):
                continue

            project_paths.append(project_path)

        requested_channels = self._keep_channels_widget.get_channels()
        requested_channels_string = (
            "all"
            if not requested_channels
            else ",".join(str(channel) for channel in requested_channels)
        )
        channel_errors: list[str] = []
        completed_projects: set[Path] = set()

        for project_path in project_paths:
            if self._has_stitched_image(project_path):
                completed_projects.add(project_path)
                print(
                    f"Project was already stitch-complete: {project_path}",
                    flush=True,
                )
                continue

            tiles_path = project_path / TILES_DIR_NAME
            config_path = tiles_path / EXTRACTED_CHANNELS_FILE_NAME
            kept_channel_files = list(
                tiles_path.glob("*_kept_channels_*.ome.zarr")
            )

            if kept_channel_files and not config_path.exists():
                channel_errors.append(
                    f"Project: {project_path}\n"
                    f"Missing {EXTRACTED_CHANNELS_FILE_NAME}"
                )
                continue

            if not config_path.exists():
                continue

            config = configparser.ConfigParser()
            try:
                config.read(config_path)
                stored_channels = config.get("channels", "kept")
            except (configparser.Error, OSError, ValueError) as exc:
                channel_errors.append(
                    f"Project: {project_path}\n"
                    f"Could not read {config_path.name}: {exc}"
                )
                continue

            if stored_channels == "all":
                stored_channels_string = "all"
            else:
                stored_channels_list = parse_channel_string(stored_channels)
                stored_channels_string = ",".join(
                    str(channel) for channel in stored_channels_list
                )

            if stored_channels_string != requested_channels_string:
                channel_errors.append(
                    f"Project: {project_path}\n"
                    f"Requested channels: {requested_channels_string}\n"
                    f"Stored channels: {stored_channels_string}"
                )

        if channel_errors:
            show_error(
                "Channel validation failed:\n\n"
                + "\n\n".join(channel_errors)
                + "\n\nNo extraction or stitching was performed."
            )
            return

        stitching_options = self.get_stitching_options()
        for project_number, project_path in enumerate(
            project_paths,
            start=1,
        ):
            if project_path in completed_projects:
                continue

            print(
                f"\nProject: {project_path.name} "
                f"({project_number}/{len(project_paths)})",
                flush=True,
            )
            extracted_paths = self._extract_project_tiles(
                project_path,
                requested_channels,
            )
            if extracted_paths is None:
                continue

            print(
                f"\nStitching: {project_path.name}",
                flush=True,
            )
            stitching_succeeded = stitch_ome_zarr_images(
                image_list=extracted_paths,
                output_dir=project_path / STITCHED_IMAGE_DIR_NAME,
                **stitching_options,
            )
            if stitching_succeeded:
                print("Done stitching...\n", flush=True)

        print("\nDone processing all projects.\n", flush=True)
        self._update_qlist()

        return

    def get_stitching_options(
        self,
    ) -> dict[str, int | bool | None]:
        registration_scale = self._registration_scale_spinbox.value()
        num_workers = self._num_workers_spinbox.value()
        n_batch = self._n_batch_spinbox.value()

        return {
            "registration_channel": (
                self._registration_channel_spinbox.value() - 1
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
            path = Path(directory_path)
            dir_name = f"{path.parent.name}/{path.name}"
            q_list_item = QListWidgetItem()
            q_list_item.setData(Qt.ItemDataRole.UserRole, directory_path)
            self._directories_q_list.addItem(q_list_item)

            row_widget = StitchProjectStatusRow(dir_name)
            project_path = self._get_project_path(path)
            self._set_project_row_status(row_widget, project_path)

            q_list_item.setSizeHint(row_widget.sizeHint())
            self._directories_q_list.setItemWidget(
                q_list_item,
                row_widget,
            )
