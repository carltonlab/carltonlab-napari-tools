from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd
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
    NUCLEI_POINTS_FEATURES_TABLE_FILE_NAME,
    PICK_NUCLEI_DIR_NAME,
    PROJECT_FILE_DIR_NAME,
    REGIONS_CONFIGURATION_FILE_NAME,
    REGIONS_DIR_NAME,
    SPLINE_LAYER_FILE_NAME,
)
from carltonlab_napari_tools._shared_widgets import (
    FrameSeparator,
    confirm_dialog,
)
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
    SPLINE_DEFAULT_EDGE_WIDTH,
    assign_points_to_spline_regions,
    configure_spline_layer,
    create_expanded_regions_layer,
    display_splines,
    expand_shape,
    get_spline_equal_segments,
    load_regions_configuration,
    load_spline_layer,
    reset_regions_configuration,
    save_regions_configuration,
    save_spline_layer,
    verify_spline_interpolation,
)

if TYPE_CHECKING:
    from napari.components import ViewerModel


REGION_COLOR_PALETTE = (
    "#ff0000",
    "#00ffff",
    "#ffff00",
)


class CLTStitchedRegionsWidget(QWidget):
    @staticmethod
    def is_project_regions_complete(project_path: Path) -> bool:
        resolved_project_path = resolve_clsp_project_path(project_path)
        if resolved_project_path is None:
            return False

        regions_directory = (
            resolved_project_path / PROJECT_FILE_DIR_NAME / REGIONS_DIR_NAME
        )
        configuration = load_regions_configuration(
            regions_directory / REGIONS_CONFIGURATION_FILE_NAME
        )
        if configuration is None or configuration[1] is None:
            return False

        features_path = (
            resolved_project_path
            / PROJECT_FILE_DIR_NAME
            / PICK_NUCLEI_DIR_NAME
            / NUCLEI_POINTS_FEATURES_TABLE_FILE_NAME
        )
        try:
            features = pd.read_csv(features_path)
        except (
            OSError,
            pd.errors.EmptyDataError,
            pd.errors.ParserError,
        ):
            return False

        return (
            not features.empty
            and "region" in features
            and bool(features["region"].notna().all())
        )

    def __init__(
        self,
        napari_viewer: "ViewerModel",
        parent: QWidget,
        project_list_widget: CLTProjectListWidget,
        status_update_callback: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(parent)

        self._napari_viewer = napari_viewer
        self._project_list_widget = project_list_widget
        self._status_update_callback = status_update_callback
        self._project_list_widget.itemSelectionChanged.connect(
            self._on_project_selection_changed
        )

        self._image_layer: Image | None = None
        self._spline_layer: Shapes | None = None
        self._regions_layer: Shapes | None = None
        self._expanded_regions_layer: Shapes | None = None
        self._nuclei_connections_layer: Shapes | None = None
        self._nuclei_features: pd.DataFrame | None = None
        self._expanded_regions_spinboxes: list[QSpinBox] = []
        self._current_project_path: Path | None = None
        self._saved_spline_signature: tuple[tuple[int, ...], bytes] | None = (
            None
        )
        self._saved_interpolation_order: int | None = None
        self._saved_number_of_regions: int | None = None

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

        self._number_regions_widget = QWidget()
        self._number_regions_layout = QHBoxLayout()
        self._number_regions_layout.setContentsMargins(0, 0, 0, 0)
        self._number_regions_widget.setLayout(self._number_regions_layout)

        self._number_regions_label = QLabel("Set number of regions")
        self._number_regions_layout.addWidget(self._number_regions_label)

        self._number_regions_spinbox = QSpinBox()
        self._number_regions_spinbox.setRange(1, 100)
        self._number_regions_spinbox.setValue(7)
        self._number_regions_spinbox.setSizePolicy(
            QSizePolicy.Policy.Maximum,
            QSizePolicy.Policy.Preferred,
        )
        self._number_regions_layout.addWidget(self._number_regions_spinbox)

        self._current_regions_label = QLabel("Current regions: None")
        self._number_regions_layout.addWidget(self._current_regions_label)

        self._apply_regions_button = QPushButton("Apply")
        self._apply_regions_button.clicked.connect(
            self._apply_regions_button_pressed
        )
        self._number_regions_layout.addWidget(self._apply_regions_button)
        self._container_layout.addWidget(self._number_regions_widget)

        self._regions_status_label = QLabel("Regions not created")
        self._container_layout.addWidget(self._regions_status_label)
        self._set_regions_saved_state(False)

        self._expanded_regions_title_label = QLabel("Expand regions")
        self._expanded_regions_title_label.setStyleSheet("font-weight: bold;")
        self._container_layout.addWidget(self._expanded_regions_title_label)

        self._set_all_expanded_widget = QWidget()
        self._set_all_expanded_layout = QHBoxLayout()
        self._set_all_expanded_layout.setContentsMargins(0, 0, 0, 0)
        self._set_all_expanded_widget.setLayout(self._set_all_expanded_layout)
        self._set_all_expanded_layout.addWidget(QLabel("Set all to:"))

        self._set_all_expanded_spinbox = QSpinBox()
        self._set_all_expanded_spinbox.setRange(0, 1_000_000)
        self._set_all_expanded_spinbox.setValue(500)
        self._set_all_expanded_layout.addWidget(self._set_all_expanded_spinbox)

        self._apply_all_expanded_button = QPushButton("Apply")
        self._apply_all_expanded_button.clicked.connect(
            self._apply_all_expanded_button_pressed
        )
        self._set_all_expanded_layout.addWidget(
            self._apply_all_expanded_button
        )
        self._set_all_expanded_layout.addStretch()
        self._container_layout.addWidget(self._set_all_expanded_widget)

        self._expanded_regions_container = QWidget()
        self._expanded_regions_layout = QVBoxLayout()
        self._expanded_regions_layout.setContentsMargins(0, 0, 0, 0)
        self._expanded_regions_container.setLayout(
            self._expanded_regions_layout
        )
        self._container_layout.addWidget(self._expanded_regions_container)

        self._save_expanded_regions_button = QPushButton(
            "Save expanded regions"
        )
        self._save_expanded_regions_button.clicked.connect(
            self._save_expanded_regions_button_pressed
        )
        self._container_layout.addWidget(self._save_expanded_regions_button)

        self._expanded_regions_status_label = QLabel(
            "Expanded regions not saved"
        )
        self._container_layout.addWidget(self._expanded_regions_status_label)
        self._set_expanded_regions_saved_state(False)

        self._display_spline_button.clicked.connect(
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
        self._current_project_path = None
        self._clear_expanded_regions_controls()
        self._set_spline_saved_state(False)
        self._set_regions_saved_state(False)
        self._set_expanded_regions_saved_state(False)
        self._napari_viewer.layers.clear()

        gonad_path = self._project_list_widget.get_current_project_path()
        if gonad_path is None:
            self._image_status_label.setText("No project selected")
            return

        project_path = resolve_clsp_project_path(gonad_path)
        if project_path is None:
            self._image_status_label.setText("No CLSP project found")
            return
        self._current_project_path = project_path

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

        regions_configuration_path = (
            project_path
            / PROJECT_FILE_DIR_NAME
            / REGIONS_DIR_NAME
            / REGIONS_CONFIGURATION_FILE_NAME
        )
        regions_configuration = load_regions_configuration(
            regions_configuration_path
        )
        if regions_configuration is not None:
            interpolation_order, number_of_regions, _ = regions_configuration
            if interpolation_order is not None:
                self._interpolation_order_spinbox.setValue(interpolation_order)
            if number_of_regions is not None:
                self._number_regions_spinbox.setValue(number_of_regions)

        self._display_spline_button_pressed()
        self._create_regions_button_pressed()
        self._evaluate_nuclei_regions()
        if regions_configuration is not None:
            _, saved_number_of_regions, _ = regions_configuration
            if saved_number_of_regions is not None:
                self._current_regions_label.setText(
                    f"Current regions: {saved_number_of_regions}"
                )
                self._set_regions_saved_state(True)

        self._saved_spline_signature = self._get_spline_signature()
        self._saved_interpolation_order = (
            self._interpolation_order_spinbox.value()
        )
        self._saved_number_of_regions = (
            saved_number_of_regions
            if regions_configuration is not None
            and saved_number_of_regions is not None
            else (
                len(self._regions_layer._data_view.shapes)
                if self._regions_layer is not None
                else None
            )
        )

        self._image_status_label.setText(f"Loaded: {stitched_path.name}")

    def _load_nuclei_features(self, project_path: Path) -> None:
        features_path = (
            project_path
            / PROJECT_FILE_DIR_NAME
            / PICK_NUCLEI_DIR_NAME
            / NUCLEI_POINTS_FEATURES_TABLE_FILE_NAME
        )
        if not features_path.is_file():
            self._nuclei_features = None
            return
        self._nuclei_features = pd.read_csv(features_path)

    def _evaluate_nuclei_regions(self) -> None:
        if self._spline_layer is None or self._regions_layer is None:
            return
        if self._current_project_path is None:
            return

        self._load_nuclei_features(self._current_project_path)
        if self._nuclei_features is None:
            return

        required_columns = {
            "stitched_x_coord",
            "stitched_y_coord",
            "region",
        }
        if not required_columns.issubset(self._nuclei_features.columns):
            return

        points_yx = self._nuclei_features[
            ["stitched_y_coord", "stitched_x_coord"]
        ].to_numpy(dtype=np.float32)
        if len(points_yx) == 0:
            return

        spline_shape = self._spline_layer._data_view.shapes[0]
        projected_points, region_numbers = assign_points_to_spline_regions(
            points_yx,
            spline_shape,
            len(self._regions_layer._data_view.shapes),
        )

        self._nuclei_features["region"] = region_numbers
        features_path = (
            self._current_project_path
            / PROJECT_FILE_DIR_NAME
            / PICK_NUCLEI_DIR_NAME
            / NUCLEI_POINTS_FEATURES_TABLE_FILE_NAME
        )
        self._nuclei_features.to_csv(features_path, index=False)
        if self._status_update_callback is not None:
            self._status_update_callback()

        line_data = np.stack(
            [points_yx, projected_points],
            axis=1,
        )

        line_colors = [
            REGION_COLOR_PALETTE[(region - 1) % len(REGION_COLOR_PALETTE)]
            for region in region_numbers
        ]
        if (
            self._nuclei_connections_layer is not None
            and self._nuclei_connections_layer in self._napari_viewer.layers
        ):
            self._napari_viewer.layers.remove(self._nuclei_connections_layer)

        self._nuclei_connections_layer = self._napari_viewer.add_shapes(
            name="clt_nuclei_spline_connections",
            ndim=2,
            edge_width=4,
        )
        self._nuclei_connections_layer.add_lines(line_data)
        self._nuclei_connections_layer.edge_color = line_colors
        self._nuclei_connections_layer.refresh()

    def _get_spline_signature(
        self,
    ) -> tuple[tuple[int, ...], bytes] | None:
        if self._spline_layer is None:
            return None
        shapes = self._spline_layer._data_view.shapes
        if len(shapes) != 1:
            return None
        data = np.asarray(shapes[0].data)
        return data.shape, data.tobytes()

    def _reset_nuclei_regions(self) -> None:
        if self._current_project_path is None:
            return

        self._load_nuclei_features(self._current_project_path)
        if self._nuclei_features is None:
            return
        if "region" not in self._nuclei_features.columns:
            return

        self._nuclei_features["region"] = None
        features_path = (
            self._current_project_path
            / PROJECT_FILE_DIR_NAME
            / PICK_NUCLEI_DIR_NAME
            / NUCLEI_POINTS_FEATURES_TABLE_FILE_NAME
        )
        self._nuclei_features.to_csv(features_path, index=False)

    def _confirm_region_recalculation(self) -> bool:
        current_spline_signature = self._get_spline_signature()
        spline_changed = (
            current_spline_signature != self._saved_spline_signature
        )
        interpolation_changed = (
            self._saved_interpolation_order is not None
            and self._interpolation_order_spinbox.value()
            != self._saved_interpolation_order
        )
        number_changed = (
            self._saved_number_of_regions is not None
            and self._number_regions_spinbox.value()
            != self._saved_number_of_regions
        )

        if not (spline_changed or interpolation_changed or number_changed):
            return True

        if spline_changed or interpolation_changed:
            changes = (
                "the region geometry",
                "the expanded region settings",
                "all nuclei region assignments",
            )
        else:
            changes = (
                "the expanded region settings",
                "all nuclei region assignments",
            )

        message = (
            "This change may alter the SBS region assignments.\n\n"
            "The following will be reset:\n- "
            + "\n- ".join(changes)
            + "\n\nDo you want to continue?"
        )
        if not confirm_dialog(self._napari_viewer, message):
            return False

        if self._current_project_path is not None:
            configuration_path = (
                self._current_project_path
                / PROJECT_FILE_DIR_NAME
                / REGIONS_DIR_NAME
                / REGIONS_CONFIGURATION_FILE_NAME
            )
            reset_regions_configuration(
                configuration_path,
                reset_number_of_regions=spline_changed
                or interpolation_changed,
                reset_expansion_values=True,
            )

        self._reset_nuclei_regions()
        self._remove_region_layers()
        self._display_spline_button_pressed()
        self._create_regions_button_pressed()
        self._evaluate_nuclei_regions()
        self._set_regions_saved_state(False)
        self._set_expanded_regions_saved_state(False)

        self._saved_spline_signature = self._get_spline_signature()
        self._saved_interpolation_order = (
            self._interpolation_order_spinbox.value()
        )
        self._saved_number_of_regions = self._number_regions_spinbox.value()
        if self._current_project_path is not None:
            save_regions_configuration(
                configuration_path,
                number_of_regions=self._number_regions_spinbox.value(),
            )
        return True

    def _display_spline_button_pressed(self) -> None:
        if self._spline_layer is None:
            return

        display_splines(
            self._spline_layer,
            self._interpolation_order_spinbox.value(),
        )

    def _apply_regions_button_pressed(self) -> None:
        if not self._confirm_region_recalculation():
            return
        if self._regions_layer is None:
            return

        if self._current_project_path is None:
            return

        configuration_path = (
            self._current_project_path
            / PROJECT_FILE_DIR_NAME
            / REGIONS_DIR_NAME
            / REGIONS_CONFIGURATION_FILE_NAME
        )
        save_regions_configuration(
            configuration_path,
            number_of_regions=self._number_regions_spinbox.value(),
        )
        self._current_regions_label.setText(
            f"Current regions: {len(self._regions_layer._data_view.shapes)}"
        )
        self._set_regions_saved_state(True)
        self._evaluate_nuclei_regions()
        if self._status_update_callback is not None:
            self._status_update_callback()

    def _remove_region_layers(self) -> None:
        for layer in (
            self._nuclei_connections_layer,
            self._expanded_regions_layer,
            self._regions_layer,
        ):
            if layer is not None and layer in self._napari_viewer.layers:
                self._napari_viewer.layers.remove(layer)

        self._nuclei_connections_layer = None
        self._expanded_regions_layer = None
        self._regions_layer = None
        self._clear_expanded_regions_controls()
        if self._spline_layer is not None:
            self._spline_layer.visible = True

    def _create_regions_button_pressed(self) -> None:

        if self._spline_layer is None:
            self._regions_status_label.setText("No spline layer")
            return

        if len(self._spline_layer._data_view.shapes) != 1:
            self._regions_status_label.setText(
                "Create exactly one spline first"
            )
            return

        interpolation_order = self._interpolation_order_spinbox.value()
        if not verify_spline_interpolation(
            self._spline_layer,
            interpolation_order,
        ):
            return

        shape_object = self._spline_layer._data_view.shapes[0]
        if shape_object.interpolation_order < 2:
            self._regions_status_label.setText(
                "Display the spline before creating regions"
            )
            return

        region_paths = get_spline_equal_segments(
            shape_object,
            number_of_segments=self._number_regions_spinbox.value(),
            points_per_segment=10,
        )
        self._regions_layer = self._napari_viewer.add_shapes(
            name="clt_regions_layer",
            ndim=2,
            edge_width=SPLINE_DEFAULT_EDGE_WIDTH,
        )
        self._regions_layer.add_paths(region_paths)
        self._apply_region_colors(self._regions_layer)
        self._spline_layer.visible = False
        self._napari_viewer.layers.selection.active = self._regions_layer
        self._set_regions_saved_state(False)
        if self._current_project_path is not None:
            self._initialize_expanded_regions(self._current_project_path)

    def _apply_all_expanded_button_pressed(self) -> None:
        value = self._set_all_expanded_spinbox.value()
        for spinbox in self._expanded_regions_spinboxes:
            spinbox.setValue(value)

    @staticmethod
    def _apply_region_colors(regions_layer: Shapes) -> None:
        number_of_regions = len(regions_layer._data_view.shapes)
        colors = [
            REGION_COLOR_PALETTE[index % len(REGION_COLOR_PALETTE)]
            for index in range(number_of_regions)
        ]
        regions_layer.edge_width = SPLINE_DEFAULT_EDGE_WIDTH
        regions_layer.current_edge_width = SPLINE_DEFAULT_EDGE_WIDTH
        regions_layer.edge_color = colors
        regions_layer.refresh()

    def _load_regions_layer(self, regions_path):
        if not regions_path.is_file():
            return None

        opened_layers = self._napari_viewer.open(str(regions_path))
        if not isinstance(opened_layers, list):
            opened_layers = [opened_layers]

        for layer in opened_layers:
            if isinstance(layer, Shapes):
                return layer

        return None

    def _clear_expanded_regions_controls(self) -> None:
        self._expanded_regions_spinboxes = []
        while self._expanded_regions_layout.count():
            item = self._expanded_regions_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _initialize_expanded_regions(self, project_path: Path) -> None:
        if self._regions_layer is None:
            self._expanded_regions_layer = None
            self._clear_expanded_regions_controls()
            self._set_expanded_regions_saved_state(False)
            return

        regions_directory = (
            project_path / PROJECT_FILE_DIR_NAME / REGIONS_DIR_NAME
        )
        configuration_path = (
            regions_directory / REGIONS_CONFIGURATION_FILE_NAME
        )

        if self._expanded_regions_layer is not None:
            self._napari_viewer.layers.remove(self._expanded_regions_layer)

        self._expanded_regions_layer = create_expanded_regions_layer(
            self._napari_viewer,
            self._regions_layer,
        )
        self._expanded_regions_layer.opacity = 0.1
        expanded_colors = [
            REGION_COLOR_PALETTE[index % len(REGION_COLOR_PALETTE)]
            for index in range(len(self._regions_layer._data_view.shapes))
        ]
        self._expanded_regions_layer.face_color = expanded_colors
        self._expanded_regions_layer.edge_color = expanded_colors
        self._expanded_regions_layer.refresh()

        expanded_index = self._napari_viewer.layers.index(
            self._expanded_regions_layer
        )
        regions_index = self._napari_viewer.layers.index(self._regions_layer)
        self._napari_viewer.layers.move(expanded_index, regions_index)

        number_of_regions = len(self._regions_layer._data_view.shapes)
        configuration = load_regions_configuration(configuration_path)
        saved_values = configuration[2] if configuration is not None else None
        has_saved_values = (
            saved_values is not None
            and len(saved_values) == number_of_regions
            and all(value is not None for value in saved_values)
        )
        values = (
            tuple(value for value in saved_values if value is not None)
            if has_saved_values and saved_values is not None
            else (500,) * number_of_regions
        )

        self._clear_expanded_regions_controls()
        for region_index, expansion_value in enumerate(values):
            row = QWidget()
            row_layout = QHBoxLayout()
            row_layout.setContentsMargins(0, 0, 0, 0)
            row.setLayout(row_layout)

            row_layout.addWidget(QLabel(f"Region {region_index + 1}"))
            spinbox = QSpinBox()
            spinbox.setRange(0, 1_000_000)
            spinbox.setValue(expansion_value)
            spinbox.valueChanged.connect(
                lambda value, index=region_index: (
                    self._expanded_region_value_changed(index, value)
                )
            )
            row_layout.addWidget(spinbox)
            row_layout.addStretch()
            self._expanded_regions_layout.addWidget(row)
            self._expanded_regions_spinboxes.append(spinbox)

            expand_shape(
                self._regions_layer,
                self._expanded_regions_layer,
                region_index,
                expansion_value,
            )

        self._regions_layer.visible = True
        self._expanded_regions_layer.visible = True
        self._napari_viewer.layers.selection.active = (
            self._expanded_regions_layer
        )
        self._set_expanded_regions_saved_state(
            has_saved_values and configuration_path.is_file()
        )

    def _expanded_region_value_changed(
        self,
        region_index: int,
        expanding_factor: int,
    ) -> None:
        if self._regions_layer is None or self._expanded_regions_layer is None:
            return

        expand_shape(
            self._regions_layer,
            self._expanded_regions_layer,
            region_index,
            expanding_factor,
        )
        self._set_expanded_regions_saved_state(False)

    def _save_expanded_regions_button_pressed(self) -> None:
        if self._expanded_regions_layer is None:
            self._set_expanded_regions_saved_state(False)
            return

        if self._current_project_path is None:
            self._set_expanded_regions_saved_state(False)
            return

        configuration_path = (
            self._current_project_path
            / PROJECT_FILE_DIR_NAME
            / REGIONS_DIR_NAME
            / REGIONS_CONFIGURATION_FILE_NAME
        )
        save_regions_configuration(
            configuration_path,
            expansion_values=[
                spinbox.value() for spinbox in self._expanded_regions_spinboxes
            ],
        )
        self._set_expanded_regions_saved_state(True)

    def _set_regions_saved_state(self, saved: bool) -> None:
        if saved:
            self._regions_status_label.setText("Regions saved")
            self._regions_status_label.setStyleSheet(
                "color: #29BA00; font-weight: bold;"
            )
        else:
            self._regions_status_label.setText("Regions not saved")
            self._regions_status_label.setStyleSheet(
                "color: gray; font-style: italic;"
            )

    def _set_expanded_regions_saved_state(self, saved: bool) -> None:
        if saved:
            self._expanded_regions_status_label.setText(
                "Expanded regions saved"
            )
            self._expanded_regions_status_label.setStyleSheet(
                "color: #29BA00; font-weight: bold;"
            )
        else:
            self._expanded_regions_status_label.setText(
                "Expanded regions not saved"
            )
            self._expanded_regions_status_label.setStyleSheet(
                "color: gray; font-style: italic;"
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

        if not self._confirm_region_recalculation():
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
