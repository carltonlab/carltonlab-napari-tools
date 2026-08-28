from typing import TYPE_CHECKING

from napari.layers import Image, Shapes
from qtpy.QtCore import Qt
from qtpy.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from carltonlab_napari_tools._shared_variables import (
    IMAGE_CONTRASTS_FILE_NAME,
    PROJECT_FILE_DIR_NAME,
    REGIONS_DIR_NAME,
    SPLINE_LAYER_FILE_NAME,
)
from carltonlab_napari_tools._shared_widgets import FrameSeparator
from carltonlab_napari_tools._utils import (
    get_project_stitched_image_path,
    resolve_clsp_project_path,
)
from carltonlab_napari_tools._viewer_utils import (
    apply_image_contrasts,
    open_ome_zarr_layers,
)
from carltonlab_napari_tools.general_widgets._project_list_widget import (
    CLTProjectListWidget,
)
from carltonlab_napari_tools.spline_manager._spline_manager import (
    configure_spline_layer,
    display_splines,
    load_spline_layer,
    save_spline_layer,
)

if TYPE_CHECKING:
    from napari.components import ViewerModel


class CLTStitchedRegionsWidget(QWidget):
    def __init__(
        self,
        napari_viewer: "ViewerModel",
        parent: QWidget,
        project_list_widget: CLTProjectListWidget,
    ) -> None:
        super().__init__(parent)

        self._napari_viewer = napari_viewer
        self._project_list_widget = project_list_widget
        self._project_list_widget.itemSelectionChanged.connect(
            self._on_project_selection_changed
        )

        self._image_layer: Image | None = None
        self._spline_layer: Shapes | None = None
        self._regions_layer: Shapes | None = None
        self._expanded_regions_layer: Shapes | None = None

        self._layout = QVBoxLayout()
        self._layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(self._layout)

        self._scroll_area = QScrollArea()
        self._scroll_area.setWidgetResizable(True)
        self._scroll_area.setFrameShape(QScrollArea.Shape.NoFrame)
        self._layout.addWidget(self._scroll_area)

        self._container = QWidget()
        self._container_layout = QVBoxLayout()
        self._container_layout.setContentsMargins(0, 0, 0, 0)
        self._container_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._container.setLayout(self._container_layout)
        self._scroll_area.setWidget(self._container)

        self._title_label = QLabel("CL Set Regions")
        self._title_label.setStyleSheet("font-weight: bold; font-size: 20px;")
        self._title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._container_layout.addWidget(self._title_label)

        self._container_layout.addWidget(FrameSeparator(parent=self))

        self._image_status_label = QLabel("No stitched image loaded")
        self._image_status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._image_status_label.setStyleSheet(
            "color: gray; font-style: italic;"
        )
        self._container_layout.addWidget(self._image_status_label)

        self._spline_title_label = QLabel("Spline")
        self._spline_title_label.setStyleSheet("font-weight: bold;")
        self._container_layout.addWidget(self._spline_title_label)

        self._interpolation_order_widget = QWidget()
        self._interpolation_order_layout = QHBoxLayout()
        self._interpolation_order_layout.setContentsMargins(0, 0, 0, 0)
        self._interpolation_order_widget.setLayout(
            self._interpolation_order_layout
        )

        self._interpolation_order_label = QLabel("Interpolation order")
        self._interpolation_order_layout.addWidget(
            self._interpolation_order_label
        )

        self._interpolation_order_spinbox = QSpinBox()
        self._interpolation_order_spinbox.setRange(1, 100)
        self._interpolation_order_spinbox.setValue(3)
        self._interpolation_order_spinbox.setSizePolicy(
            QSizePolicy.Policy.Maximum,
            QSizePolicy.Policy.Preferred,
        )
        self._interpolation_order_layout.addWidget(
            self._interpolation_order_spinbox
        )
        self._interpolation_order_layout.addStretch()
        self._container_layout.addWidget(self._interpolation_order_widget)

        self._display_spline_button = QPushButton("Display spline")
        self._display_spline_button.clicked.connect(
            self._display_spline_button_pressed
        )
        self._container_layout.addWidget(self._display_spline_button)

        self._save_spline_button = QPushButton("Save spline")
        self._save_spline_button.clicked.connect(
            self._save_spline_button_pressed
        )
        self._container_layout.addWidget(self._save_spline_button)

        self._spline_status_label = QLabel("Spline not saved")
        self._container_layout.addWidget(self._spline_status_label)
        self._set_spline_saved_state(False)

        self._container_layout.addWidget(FrameSeparator(parent=self))

        self._regions_title_label = QLabel("Regions")
        self._regions_title_label.setStyleSheet("font-weight: bold;")
        self._container_layout.addWidget(self._regions_title_label)

        self._number_regions_widget = QWidget()
        self._number_regions_layout = QHBoxLayout()
        self._number_regions_layout.setContentsMargins(0, 0, 0, 0)
        self._number_regions_widget.setLayout(self._number_regions_layout)

        self._number_regions_label = QLabel("Number of regions")
        self._number_regions_layout.addWidget(self._number_regions_label)

        self._number_regions_spinbox = QSpinBox()
        self._number_regions_spinbox.setRange(1, 100)
        self._number_regions_spinbox.setValue(7)
        self._number_regions_spinbox.setSizePolicy(
            QSizePolicy.Policy.Maximum,
            QSizePolicy.Policy.Preferred,
        )
        self._number_regions_layout.addWidget(self._number_regions_spinbox)
        self._number_regions_layout.addStretch()
        self._container_layout.addWidget(self._number_regions_widget)

        self._create_regions_button = QPushButton("Create regions")
        self._container_layout.addWidget(self._create_regions_button)

        self._regions_status_label = QLabel("Regions not created")
        self._container_layout.addWidget(self._regions_status_label)

        self._container_layout.addWidget(FrameSeparator(parent=self))

        self._expanded_regions_title_label = QLabel("Expand regions")
        self._expanded_regions_title_label.setStyleSheet("font-weight: bold;")
        self._container_layout.addWidget(self._expanded_regions_title_label)

        self._save_expanded_regions_button = QPushButton(
            "Save expanded regions"
        )
        self._container_layout.addWidget(self._save_expanded_regions_button)

        self._expanded_regions_status_label = QLabel(
            "Expanded regions not saved"
        )
        self._container_layout.addWidget(self._expanded_regions_status_label)

        self._display_spline_button.clicked.connect(
            self._display_spline_button_pressed
        )
        self._interpolation_order_spinbox.valueChanged.connect(
            self._display_spline_button_pressed
        )

        self._container_layout.addStretch()

        self.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )

        self._load_selected_project_image()

    def _on_project_selection_changed(self) -> None:
        self._load_selected_project_image()

    def _load_selected_project_image(self) -> None:
        self._image_layer = None
        self._spline_layer = None
        self._regions_layer = None
        self._expanded_regions_layer = None
        self._set_spline_saved_state(False)
        self._napari_viewer.layers.clear()

        gonad_path = self._project_list_widget.get_current_project_path()
        if gonad_path is None:
            self._image_status_label.setText("No project selected")
            return

        project_path = resolve_clsp_project_path(gonad_path)
        if project_path is None:
            self._image_status_label.setText("No CLSP project found")
            return

        stitched_path = get_project_stitched_image_path(project_path)
        if stitched_path is None:
            self._image_status_label.setText("No stitched image found")
            return

        opened_images = open_ome_zarr_layers(
            self._napari_viewer,
            str(stitched_path),
        )
        if not opened_images:
            self._image_status_label.setText("Could not open stitched image")
            return

        self._image_layer = opened_images[0]
        contrast_path = (
            project_path / PROJECT_FILE_DIR_NAME / IMAGE_CONTRASTS_FILE_NAME
        )
        apply_image_contrasts(opened_images, contrast_path)

        spline_path = (
            project_path
            / PROJECT_FILE_DIR_NAME
            / REGIONS_DIR_NAME
            / SPLINE_LAYER_FILE_NAME
        )
        self._spline_layer = load_spline_layer(
            self._napari_viewer,
            spline_path,
        )
        if self._spline_layer is None:
            self._spline_layer = self._napari_viewer.add_shapes(
                name="clt_spline_layer",
                ndim=2,
            )
            configure_spline_layer(self._spline_layer)
            self._napari_viewer.layers.selection.active = self._spline_layer
        else:
            self._set_spline_saved_state(True)

        self._image_status_label.setText(f"Loaded: {stitched_path.name}")

    def _display_spline_button_pressed(self) -> None:
        if self._spline_layer is None:
            return

        display_splines(
            self._spline_layer,
            self._interpolation_order_spinbox.value(),
        )

    def _save_spline_button_pressed(self) -> None:
        if self._spline_layer is None:
            self._spline_status_label.setText("No spline layer")
            return

        gonad_path = self._project_list_widget.get_current_project_path()
        project_path = (
            resolve_clsp_project_path(gonad_path)
            if gonad_path is not None
            else None
        )
        if project_path is None:
            self._spline_status_label.setText("No project selected")
            return

        spline_path = (
            project_path
            / PROJECT_FILE_DIR_NAME
            / REGIONS_DIR_NAME
            / SPLINE_LAYER_FILE_NAME
        )
        if not save_spline_layer(self._spline_layer, spline_path):
            self._spline_status_label.setText(
                "Exactly one spline must be created"
            )
            self._set_spline_saved_state(False)
            return

        self._set_spline_saved_state(True)

    def _set_spline_saved_state(self, saved: bool) -> None:
        if saved:
            self._spline_status_label.setText("Spline saved")
            self._spline_status_label.setStyleSheet(
                "color: #29BA00; font-weight: bold;"
            )
        else:
            self._spline_status_label.setText("Spline not saved")
            self._spline_status_label.setStyleSheet(
                "color: gray; font-style: italic;"
            )
