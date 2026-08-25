import configparser
from pathlib import Path
from typing import TYPE_CHECKING

from napari.layers import Image
from qtpy.QtCore import Qt
from qtpy.QtWidgets import (
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
from superqt import QRangeSlider

from carltonlab_napari_tools._shared_variables import (
    CLSP_PROJECT_SUFFIX,
    EXTRACTED_CHANNELS_FILE_NAME,
    STITCHED_IMAGE_DIR_NAME,
    SUPPORTED_STITCH_EXTENSIONS,
    TILES_CONFIG_FILE_NAME,
    TILES_DIR_NAME,
)
from carltonlab_napari_tools._shared_widgets import FrameSeparator
from carltonlab_napari_tools._utils import parse_channel_string
from carltonlab_napari_tools._viewer_utils import (
    close_image_layers,
    open_ome_zarr_layers,
)
from carltonlab_napari_tools.general_widgets._project_list_widget import (
    CLTProjectListWidget,
)

if TYPE_CHECKING:
    from napari.viewer import ViewerModel


class CLTContrastLimitWidget(QWidget):
    def __init__(
        self,
        channel_index: int,
        display_name: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)

        self._channel_index = channel_index

        self._layout = QVBoxLayout()
        self._layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(self._layout)

        self._title_label = QLabel(
            f"Channel {channel_index + 1} --- {display_name}"
        )
        self._title_label.setStyleSheet("font-weight: bold")
        self._layout.addWidget(self._title_label)

        self._set_from_viewer_button = QPushButton("Set from viewer contrast")
        self._layout.addWidget(self._set_from_viewer_button)

        self._slider_controls_container = QWidget()
        self._slider_controls_layout = QHBoxLayout()
        self._slider_controls_layout.setContentsMargins(0, 0, 0, 0)
        self._slider_controls_container.setLayout(self._slider_controls_layout)
        self._layout.addWidget(self._slider_controls_container)

        self._set_min_zero_button = QPushButton("Set 0")
        self._set_min_button = QPushButton("Set Min")
        self._decrease_min_button = QPushButton("-10")
        self._reset_range_button = QPushButton("Reset")
        self._set_current_button = QPushButton("Set current")
        self._increase_max_button = QPushButton("+10")
        self._set_max_button = QPushButton("Set Max")
        self._set_max_full_button = QPushButton("65535")

        for button in (
            self._set_min_zero_button,
            self._set_min_button,
            self._decrease_min_button,
            self._reset_range_button,
            self._set_current_button,
            self._increase_max_button,
            self._set_max_button,
            self._set_max_full_button,
        ):
            self._slider_controls_layout.addWidget(button)

        self._contrast_slider = QRangeSlider(Qt.Orientation.Horizontal)
        self._contrast_slider.setRange(0, 65535)
        self._contrast_slider.setSingleStep(1)
        self._contrast_slider.setValue((1, 65535))
        self._layout.addWidget(self._contrast_slider)

        self._spin_boxes_container = QWidget()
        self._spin_boxes_layout = QHBoxLayout()
        self._spin_boxes_layout.setContentsMargins(0, 0, 0, 0)
        self._spin_boxes_container.setLayout(self._spin_boxes_layout)
        self._layout.addWidget(self._spin_boxes_container)

        self._min_label = QLabel("Min")
        self._spin_boxes_layout.addWidget(self._min_label)

        self._min_spin_box = QSpinBox()
        self._min_spin_box.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        self._min_spin_box.setKeyboardTracking(False)
        self._min_spin_box.setRange(0, 65535)
        self._min_spin_box.setValue(1)
        self._spin_boxes_layout.addWidget(self._min_spin_box)

        self._max_label = QLabel("Max")
        self._spin_boxes_layout.addWidget(self._max_label)

        self._max_spin_box = QSpinBox()
        self._max_spin_box.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        self._max_spin_box.setKeyboardTracking(False)
        self._max_spin_box.setRange(0, 65535)
        self._max_spin_box.setValue(65535)
        self._spin_boxes_layout.addWidget(self._max_spin_box)


class CLTContrastImageRow(QWidget):
    def __init__(
        self,
        display_name: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)

        self._layout = QHBoxLayout()
        self._layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(self._layout)

        self._name_label = QLabel(display_name)
        self._name_label.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Preferred,
        )
        self._layout.addWidget(self._name_label)


class CLTSetContrastWidget(QWidget):
    def __init__(
        self,
        napari_viewer: "ViewerModel",
        parent: QWidget,
        project_list_widget: CLTProjectListWidget,
    ) -> None:
        super().__init__(parent)

        self._napari_viewer = napari_viewer
        self._project_list_widget = project_list_widget
        self._image_layers: list[Image] = []
        self._project_list_widget.itemSelectionChanged.connect(
            self._on_project_selection_changed
        )

        self._layout = QVBoxLayout()
        self._layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(self._layout)

        self._scroll_area = QScrollArea()
        self._scroll_area.setWidgetResizable(True)
        self._scroll_area.setViewportMargins(0, 0, 0, 0)
        self._layout.addWidget(self._scroll_area)

        self._container = QWidget()
        self._container_layout = QVBoxLayout()
        self._container_layout.setContentsMargins(0, 0, 0, 0)
        self._container.setLayout(self._container_layout)
        self._scroll_area.setWidget(self._container)

        self._title_label = QLabel("CL Set Contrast")
        self._title_label.setStyleSheet("font-weight: bold; font-size: 20px")
        self._title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._container_layout.addWidget(self._title_label)

        self._container_layout.addWidget(
            FrameSeparator(parent=self._container)
        )

        self._project_label = QLabel("Current project")
        self._project_label.setStyleSheet("font-weight: bold")
        self._container_layout.addWidget(self._project_label)

        self._image_list_container = QWidget()
        self._image_list_layout = QVBoxLayout()
        self._image_list_layout.setContentsMargins(0, 0, 0, 0)
        self._image_list_container.setLayout(self._image_list_layout)
        self._container_layout.addWidget(self._image_list_container)

        self._images_list_widget = QListWidget()
        self._images_list_widget.setSpacing(6)
        self._images_list_widget.itemSelectionChanged.connect(
            self._on_image_selection_changed
        )
        self._image_list_layout.addWidget(self._images_list_widget)

        self._contrast_container = QWidget()
        self._contrast_layout = QVBoxLayout()
        self._contrast_layout.setContentsMargins(0, 0, 0, 0)
        self._contrast_container.setLayout(self._contrast_layout)
        self._container_layout.addWidget(self._contrast_container)

        self._container_layout.addStretch()

        self._on_project_selection_changed()

    def _resolve_project_path(
        self,
        starting_path: Path,
    ) -> Path | None:
        if starting_path.name.endswith(CLSP_PROJECT_SUFFIX):
            return starting_path

        project_paths = [
            path
            for path in starting_path.iterdir()
            if path.is_dir() and path.name.endswith(CLSP_PROJECT_SUFFIX)
        ]
        return project_paths[0] if project_paths else None

    def _on_project_selection_changed(self) -> None:
        self._clear_open_image()
        self._clear_contrast_widgets()
        self._images_list_widget.clear()

        starting_path = self._project_list_widget.get_current_project_path()
        if starting_path is None:
            self._project_label.setText("Current project")
            return

        project_path = self._resolve_project_path(starting_path)
        if project_path is None:
            self._project_label.setText("Current project")
            return

        self._project_label.setText(
            f"Current project: {project_path.parent.name}/{project_path.name}"
        )

        for tile_path in self._get_contrast_tile_paths(project_path):
            self._add_image_entry(tile_path.name, tile_path)

        stitched_directory = project_path / STITCHED_IMAGE_DIR_NAME
        for stitched_path in sorted(stitched_directory.glob("*.ome.zarr")):
            self._add_image_entry("Stitched image", stitched_path)

    def _add_image_entry(
        self,
        display_name: str,
        image_path: Path,
    ) -> None:
        list_item = QListWidgetItem()
        list_item.setData(Qt.ItemDataRole.UserRole, image_path)
        self._images_list_widget.addItem(list_item)

        row_widget = CLTContrastImageRow(display_name)
        list_item.setSizeHint(row_widget.sizeHint())
        self._images_list_widget.setItemWidget(list_item, row_widget)

    def _on_image_selection_changed(self) -> None:
        selected_item = self._images_list_widget.currentItem()
        if selected_item is None:
            return

        image_path = selected_item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(image_path, Path):
            return

        self._clear_open_image()

        opened_layers = open_ome_zarr_layers(
            self._napari_viewer,
            str(image_path),
        )
        if opened_layers is None:
            return

        self._image_layers = opened_layers
        self._create_contrast_widgets(opened_layers)

    def _create_contrast_widgets(
        self,
        image_layers: list[Image],
    ) -> None:
        self._clear_contrast_widgets()

        for channel_index, image_layer in enumerate(image_layers):
            contrast_widget = CLTContrastLimitWidget(
                channel_index=channel_index,
                display_name=image_layer.name,
                parent=self._contrast_container,
            )
            self._contrast_layout.addWidget(contrast_widget)

    def _clear_open_image(self) -> None:
        if not self._image_layers:
            return

        close_image_layers(
            self._napari_viewer,
            self._image_layers,
        )
        self._image_layers = []

    def _clear_contrast_widgets(self) -> None:
        while self._contrast_layout.count():
            item = self._contrast_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _get_contrast_tile_paths(
        self,
        project_path: Path,
    ) -> list[Path]:
        tiles_directory = project_path / TILES_DIR_NAME
        tiles_config_path = tiles_directory / TILES_CONFIG_FILE_NAME
        channels_config_path = tiles_directory / EXTRACTED_CHANNELS_FILE_NAME

        if not tiles_config_path.exists():
            return []
        if not channels_config_path.exists():
            return []

        tiles_config = configparser.ConfigParser()
        channels_config = configparser.ConfigParser()

        try:
            tiles_config.read(tiles_config_path)
            channels_config.read(channels_config_path)
            tile_names = [
                tile_name for _, tile_name in tiles_config.items("tiles")
            ]
            stored_channels = channels_config.get(
                "channels",
                "kept",
            ).strip()
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
                if original_tile_path.name.endswith(".ome.zarr"):
                    tile_path = original_tile_path
                else:
                    continue
            else:
                tile_path = self._get_extracted_tile_path(
                    original_tile_path,
                    kept_channels,
                )

            if tile_path.is_dir() and tile_path.name.endswith(".ome.zarr"):
                tile_paths.append(tile_path)

        return tile_paths

    def _get_extracted_tile_path(
        self,
        tile_path: Path,
        channels: list[int],
    ) -> Path:
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

        channel_string = "-".join(str(channel) for channel in channels)
        output_name = f"{base_name}_kept_channels_{channel_string}.ome.zarr"
        return tile_path.with_name(output_name)
