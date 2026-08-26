import configparser
from pathlib import Path
from typing import TYPE_CHECKING

from napari.layers import Image, Labels, Points, Shapes
from napari.utils.notifications import show_error
from qtpy.QtCore import Qt
from qtpy.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from carltonlab_napari_tools._shared_variables import (
    IMAGE_CONTRASTS_FILE_NAME,
    PROJECT_FILE_DIR_NAME,
    STITCHED_IMAGE_DIR_NAME,
)
from carltonlab_napari_tools._shared_widgets import FrameSeparator
from carltonlab_napari_tools._viewer_utils import (
    close_image_layers,
    open_ome_zarr_layers,
)
from carltonlab_napari_tools.general_widgets._project_list_widget import (
    CLTProjectListWidget,
)

if TYPE_CHECKING:
    from napari.components import ViewerModel


class CLTPickNucleiWidget(QWidget):
    def __init__(
        self,
        napari_viewer: "ViewerModel",
        parent: QWidget,
        project_list_widget: CLTProjectListWidget,
    ) -> None:
        super().__init__(parent)

        self._napari_viewer = napari_viewer
        self._parent_widget = parent
        self._project_list_widget = project_list_widget

        self._image_layer: Image | None = None
        self._nuclei_centers_layer: Points | None = None
        self._nuclei_squares_layer: Shapes | None = None
        self._nuclei_segmentation_layer: Labels | None = None

        self._layout = QVBoxLayout()
        self._layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(self._layout)

        self._title_label = QLabel("CLT Pick Points")
        self._title_label.setStyleSheet("font-weight: bold; font-size: 20px")
        self._title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._layout.addWidget(self._title_label)

        self._layout.addWidget(FrameSeparator(parent=self))

        self._regions_title_label = QLabel("Regions")
        self._regions_title_label.setStyleSheet("font-weight: bold")
        self._layout.addWidget(self._regions_title_label)

        self._regions_list_widget = QListWidget()
        self._regions_list_widget.setUniformItemSizes(True)
        self._regions_list_widget.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Preferred,
        )
        self._regions_list_widget.setMaximumHeight(7 * 24 + 2)
        self._layout.addWidget(self._regions_list_widget)

        self._square_controls_widget = QWidget()
        self._square_controls_layout = QHBoxLayout()
        self._square_controls_layout.setContentsMargins(0, 0, 0, 0)
        self._square_controls_widget.setLayout(self._square_controls_layout)

        self._square_size_label = QLabel("Default square size")
        self._square_size_label.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Preferred,
        )
        self._square_controls_layout.addWidget(self._square_size_label)

        self._square_size_spinbox = QSpinBox()
        self._square_size_spinbox.setMinimum(1)
        self._square_size_spinbox.setValue(100)
        self._square_size_spinbox.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Preferred,
        )
        self._square_controls_layout.addWidget(self._square_size_spinbox)

        self._show_squares_checkbox = QCheckBox("Show squares")
        self._show_squares_checkbox.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Preferred,
        )
        self._square_controls_layout.addWidget(self._show_squares_checkbox)
        self._layout.addWidget(self._square_controls_widget)

        self._z_sections_widget = QWidget()
        self._z_sections_layout = QHBoxLayout()
        self._z_sections_layout.setContentsMargins(0, 0, 0, 0)
        self._z_sections_widget.setLayout(self._z_sections_layout)

        self._z_sections_label = QLabel("Z-sections")
        self._z_sections_label.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Preferred,
        )
        self._z_sections_layout.addWidget(self._z_sections_label)

        self._z_sections_spinbox = QSpinBox()
        self._z_sections_spinbox.setMinimum(1)
        self._z_sections_spinbox.setValue(27)
        self._z_sections_spinbox.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Preferred,
        )
        self._z_sections_layout.addWidget(self._z_sections_spinbox)
        self._layout.addWidget(self._z_sections_widget)

        self._layout.addSpacing(6)

        self._sbs_list_title_label = QLabel("SBS list")
        self._sbs_list_title_label.setStyleSheet("font-weight: bold")
        self._layout.addWidget(self._sbs_list_title_label)

        self._sbs_list_widget = QListWidget()
        self._sbs_list_widget.setUniformItemSizes(True)
        self._sbs_list_widget.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Preferred,
        )
        self._sbs_list_widget.setMaximumHeight(5 * 24 + 2)
        self._layout.addWidget(self._sbs_list_widget)

        self._layout.addWidget(FrameSeparator(parent=self))

        self._save_nuclei_features_button = QPushButton("Save nuclei features")
        self._layout.addWidget(self._save_nuclei_features_button)

        self._project_list_widget.currentItemChanged.connect(
            self._project_selection_changed
        )
        self._load_current_stitched_image()

    def _project_selection_changed(self, *_args: object) -> None:
        self._load_current_stitched_image()

    def _load_current_stitched_image(self) -> None:
        self._image_layer = None

        image_layers = [
            layer
            for layer in self._napari_viewer.layers
            if isinstance(layer, Image)
        ]
        close_image_layers(self._napari_viewer, image_layers)

        project_path = self._project_list_widget.get_current_project_path()
        if project_path is None:
            return

        stitched_directory = project_path / STITCHED_IMAGE_DIR_NAME
        stitched_paths = sorted(stitched_directory.glob("*.ome.zarr"))
        if not stitched_paths:
            return

        opened_images = open_ome_zarr_layers(
            self._napari_viewer,
            str(stitched_paths[0]),
        )
        if not opened_images:
            return

        self._load_stitched_contrasts(project_path, opened_images)
        self._image_layer = opened_images[0]

    def _load_stitched_contrasts(
        self,
        project_path: Path,
        image_layers: list[Image],
    ) -> None:
        contrast_path = (
            project_path / PROJECT_FILE_DIR_NAME / IMAGE_CONTRASTS_FILE_NAME
        )
        if not contrast_path.exists():
            return

        config = configparser.ConfigParser()

        try:
            config.read(contrast_path)
            number_of_channels = config.getint(
                "ImageContrasts",
                "NumberOfChannels",
            )

            for channel_index in range(
                min(number_of_channels, len(image_layers))
            ):
                values = config.get(
                    "ImageContrasts",
                    f"channel-{channel_index + 1}",
                )
                minimum, maximum = (
                    float(value.strip())
                    for value in values.split(",", maxsplit=1)
                )
                image_layers[channel_index].contrast_limits = (
                    minimum,
                    maximum,
                )
        except (configparser.Error, OSError, ValueError) as exc:
            show_error(f"Could not load stitched image contrasts: {exc}")
