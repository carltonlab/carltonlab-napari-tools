import configparser
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from napari.utils.notifications import show_error
from qtpy.QtCore import Qt
from qtpy.QtWidgets import (
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from carltonlab_napari_tools._shared_variables import (
    CLSP_PROJECT_SUFFIX,
    EXTRACTED_CHANNELS_FILE_NAME,
    STITCHED_IMAGE_DIR_NAME,
    TILE_CONTRASTS_FILE_NAME_SUFFIX,
    TILES_CONFIG_FILE_NAME,
    TILES_DIR_NAME,
)
from carltonlab_napari_tools._shared_widgets import (
    FrameSeparator,
    KeepChannelsWidget,
)
from carltonlab_napari_tools._tile_utils import (
    ensure_tiles_config,
    get_extracted_tile_path,
    move_tiles,
)
from carltonlab_napari_tools._utils import (
    create_project_structure,
    get_clsp_project_path,
    parse_channel_string,
)
from carltonlab_napari_tools.channel_extraction import (
    extract_project_tiles,
)
from carltonlab_napari_tools.general_widgets._project_list_widget import (
    CLTProjectListWidget,
)
from carltonlab_napari_tools.image_stitching import (
    stitch_ome_zarr_images,
)
from carltonlab_napari_tools.image_stitching._stitching_options_widget import (
    CLTStitchingOptionsWidget,
)

if TYPE_CHECKING:
    from napari.viewer import ViewerModel


@dataclass(frozen=True)
class ProjectStatus:
    extraction_color: str
    extraction_tooltip: str
    contrast_color: str
    contrast_tooltip: str
    stitching_color: str
    stitching_tooltip: str
    stitching_text: str = "St"


class StitchOmeZarrWidget(QWidget):
    def __init__(
        self,
        napari_viewer: "ViewerModel",
        parent: QWidget,
        project_list_widget: CLTProjectListWidget,
        keep_channels_widget: KeepChannelsWidget,
    ) -> None:
        super().__init__(parent)

        self._napari_viewer = napari_viewer
        self._project_list_widget = project_list_widget
        self._keep_channels_widget = keep_channels_widget

        self.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )

        self._layout = QVBoxLayout()
        self.setLayout(self._layout)
        self._layout.setContentsMargins(0, 0, 0, 0)

        self._main_scroll_area: QScrollArea = QScrollArea()
        self._main_scroll_area.setWidgetResizable(True)
        self._main_scroll_area.setViewportMargins(0, 0, 0, 0)
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

        self._stitching_options_widget = CLTStitchingOptionsWidget(
            parent=self._main_container
        )
        self._main_layout.addWidget(self._stitching_options_widget)
        self._main_layout.addWidget(FrameSeparator(parent=self))

        self._stitch_button: QPushButton = QPushButton("Stitch gonads")
        self._stitch_button.clicked.connect(self._on_stitch_button_pressed)
        self._main_layout.addWidget(self._stitch_button)

        self._files_created_status_label: QLabel = QLabel("")
        self._main_layout.addWidget(self._files_created_status_label)
        self._set_files_created_label_state(False)

        self._main_layout.addStretch()

    def _has_stitched_image(self, project_path: Path) -> bool:
        stitched_dir = project_path / STITCHED_IMAGE_DIR_NAME
        return stitched_dir.is_dir() and any(stitched_dir.glob("*.ome.zarr"))

    @staticmethod
    def get_project_status(
        starting_path: str | Path,
        requested_channels: list[int],
    ) -> ProjectStatus:
        project_path = Path(starting_path)

        if not project_path.name.endswith(CLSP_PROJECT_SUFFIX):
            existing_projects = [
                path
                for path in project_path.iterdir()
                if path.is_dir() and path.name.endswith(CLSP_PROJECT_SUFFIX)
            ]
            if existing_projects:
                project_path = existing_projects[0]

        stored_channels: str | list[int] | None = None
        channels_config_path = (
            project_path / TILES_DIR_NAME / EXTRACTED_CHANNELS_FILE_NAME
        )

        if channels_config_path.exists():
            config = configparser.ConfigParser()
            try:
                config.read(channels_config_path)
                stored_value = config.get("channels", "kept").strip()
            except (configparser.Error, OSError, ValueError):
                stored_value = ""

            if stored_value == "all":
                stored_channels = "all"
            elif stored_value:
                parsed_channels = parse_channel_string(stored_value)
                if parsed_channels:
                    stored_channels = parsed_channels

        channels_match = (
            stored_channels == "all"
            if not requested_channels
            else stored_channels == requested_channels
        )

        if not requested_channels:
            extraction_color = "gray"
            extraction_tooltip = "No channel extraction required"
        elif stored_channels is None:
            extraction_color = "red"
            extraction_tooltip = "Channels haven't been created"
        elif channels_match:
            extraction_color = "green"
            extraction_tooltip = "Channels already extracted"
        else:
            extraction_color = "orange"
            extraction_tooltip = "Incompatible channels"

        contrast_tile_paths = StitchOmeZarrWidget._get_contrast_tile_paths(
            project_path
        )
        contrast_files_exist = bool(contrast_tile_paths) and all(
            tile_path.with_name(
                f"{tile_path.name.removesuffix('.ome.zarr')}"
                f"{TILE_CONTRASTS_FILE_NAME_SUFFIX}"
            ).exists()
            for tile_path in contrast_tile_paths
        )
        if contrast_files_exist:
            contrast_color = "green"
            contrast_tooltip = "Contrasts already set"
        else:
            contrast_color = "red"
            contrast_tooltip = "Contrasts haven't been set"

        stitched_image_directory = project_path / STITCHED_IMAGE_DIR_NAME
        stitched_image_exists = stitched_image_directory.is_dir() and any(
            stitched_image_directory.glob("*.ome.zarr")
        )

        if not stitched_image_exists:
            stitching_color = "red"
            stitching_tooltip = "Stitched image hasn't been created"
            stitching_text = "St"
        elif channels_match:
            stitching_color = "green"
            stitching_tooltip = "Stitch already complete"
            stitching_text = "St"
        else:
            stitching_color = "orange"
            stored_text = (
                "unknown"
                if stored_channels is None
                else (
                    stored_channels
                    if isinstance(stored_channels, str)
                    else ",".join(str(channel) for channel in stored_channels)
                )
            )
            stitching_tooltip = (
                f"Incompatible channels (stored: {stored_text})"
            )
            stitching_text = "St"

        return ProjectStatus(
            extraction_color=extraction_color,
            extraction_tooltip=extraction_tooltip,
            contrast_color=contrast_color,
            contrast_tooltip=contrast_tooltip,
            stitching_color=stitching_color,
            stitching_tooltip=stitching_tooltip,
            stitching_text=stitching_text,
        )

    @staticmethod
    def _get_contrast_tile_paths(project_path: Path) -> list[Path]:
        tiles_directory = project_path / TILES_DIR_NAME
        tiles_config_path = tiles_directory / TILES_CONFIG_FILE_NAME
        channels_config_path = tiles_directory / EXTRACTED_CHANNELS_FILE_NAME

        if not tiles_config_path.exists() or not channels_config_path.exists():
            return []

        tiles_config = configparser.ConfigParser()
        channels_config = configparser.ConfigParser()
        try:
            tiles_config.read(tiles_config_path)
            channels_config.read(channels_config_path)
            tile_names = [
                tile_name for _, tile_name in tiles_config.items("tiles")
            ]
            stored_channels = channels_config.get("channels", "kept").strip()
        except (configparser.Error, OSError):
            return []

        if stored_channels == "all":
            kept_channels: list[int] = []
        else:
            kept_channels = parse_channel_string(stored_channels)
            if not kept_channels:
                return []

        tile_paths: list[Path] = []
        for tile_name in tile_names:
            original_tile_path = tiles_directory / tile_name
            if not kept_channels:
                if not original_tile_path.name.endswith(".ome.zarr"):
                    continue
                tile_path = original_tile_path
            else:
                tile_path = get_extracted_tile_path(
                    original_tile_path,
                    kept_channels,
                )

            if tile_path.is_dir() and tile_path.name.endswith(".ome.zarr"):
                tile_paths.append(tile_path)

        return tile_paths

    def _on_stitch_button_pressed(self) -> None:
        starting_projects = self._project_list_widget.get_project_paths()
        if not starting_projects:
            return

        project_paths: list[Path] = []

        for starting_project in starting_projects:
            project_path = get_clsp_project_path(starting_project)

            if not create_project_structure(project_path, "clsp"):
                continue

            tiles_path = project_path / TILES_DIR_NAME
            if (
                tiles_path.is_dir()
                and not any(tiles_path.iterdir())
                and not move_tiles(starting_project, project_path)
            ):
                continue

            if not ensure_tiles_config(project_path):
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
            extracted_paths = extract_project_tiles(
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
        self._project_list_widget.refresh_rows()

        return

    def get_stitching_options(
        self,
    ) -> dict[str, int | bool | None]:
        return self._stitching_options_widget.get_stitching_options()

    def _set_files_created_label_state(self, state: bool) -> None:
        if state:
            self._files_created_status_label.setText("Files created")
            self._files_created_status_label.setStyleSheet("color: green")
        else:
            self._files_created_status_label.setText("Files not created")
            self._files_created_status_label.setStyleSheet("color: red")
