import configparser
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd
from napari.layers import Image, Labels, Points, Shapes
from napari.layers.base import ActionType
from napari.utils.notifications import show_error
from qtpy.QtCore import QSignalBlocker, Qt
from qtpy.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from carltonlab_napari_tools._shared_variables import (
    CLSP_PROJECT_SUFFIX,
    IMAGE_CONTRASTS_FILE_NAME,
    NUCLEI_POINTS_FEATURES_TABLE_FILE_NAME,
    NUCLEI_POINTS_LAYER_FILE_NAME,
    PICK_NUCLEI_DIR_NAME,
    PROJECT_FILE_DIR_NAME,
    STITCHED_IMAGE_DIR_NAME,
)
from carltonlab_napari_tools._shared_widgets import FrameSeparator
from carltonlab_napari_tools._viewer_utils import open_ome_zarr_layers
from carltonlab_napari_tools.general_widgets._project_list_widget import (
    CLTProjectListWidget,
)

if TYPE_CHECKING:
    from napari.components import ViewerModel


class CLTSBSPointWidget(QWidget):
    def __init__(
        self,
        point_name: str,
        region_name: str | None,
        square_width: int,
        square_height: int,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)

        layout = QHBoxLayout()
        layout.setContentsMargins(4, 2, 4, 2)
        self.setLayout(layout)

        self._point_name_label = QLabel(point_name)
        self._region_name_label = QLabel(
            region_name if region_name is not None else "Region: Not assigned"
        )
        self._square_width_label = QLabel(f"W: {square_width}")
        self._square_height_label = QLabel(f"H: {square_height}")

        layout.addWidget(self._point_name_label)
        layout.addWidget(self._region_name_label)
        layout.addStretch()
        layout.addWidget(self._square_width_label)
        layout.addWidget(self._square_height_label)

    def set_square_dimensions(
        self,
        square_width: int,
        square_height: int,
    ) -> None:
        self._square_width_label.setText(f"W: {square_width}")
        self._square_height_label.setText(f"H: {square_height}")


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
        self._nuclei_points_path: Path | None = None
        self._nuclei_features_path: Path | None = None
        self._nuclei_features_headers: dict[str, str] = {
            "x_coord": "x_coord",
            "y_coord": "y_coord",
            "z_coord": "z_coord",
            "sbs_number": "sbs_number",
            "square_width": "square_width",
            "square_height": "square_height",
            "square_z_sections": "square_z_sections",
        }
        self._current_nuclei_features: dict[str, np.ndarray] = {
            self._nuclei_features_headers["x_coord"]: np.array([0.0]),
            self._nuclei_features_headers["y_coord"]: np.array([0.0]),
            self._nuclei_features_headers["z_coord"]: np.array([0.0]),
            self._nuclei_features_headers["sbs_number"]: np.array([1]),
            self._nuclei_features_headers["square_width"]: np.array([100]),
            self._nuclei_features_headers["square_height"]: np.array([100]),
            self._nuclei_features_headers["square_z_sections"]: np.array([27]),
        }

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
        self._square_size_spinbox.setRange(1, 1_000_000)
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
        self._show_squares_checkbox.toggled.connect(
            self._on_show_squares_checkbox_toggled
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
        self._z_sections_spinbox.setRange(1, 1_000_000)
        self._z_sections_spinbox.setValue(27)
        self._z_sections_spinbox.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Preferred,
        )
        self._z_sections_layout.addWidget(self._z_sections_spinbox)
        self._layout.addWidget(self._z_sections_widget)

        self._layout.addSpacing(6)

        self._sbs_list_header_widget = QWidget()
        self._sbs_list_header_layout = QHBoxLayout()
        self._sbs_list_header_layout.setContentsMargins(0, 0, 0, 0)
        self._sbs_list_header_widget.setLayout(self._sbs_list_header_layout)

        self._sbs_list_title_label = QLabel("SBS list")
        self._sbs_list_title_label.setStyleSheet("font-weight: bold")
        self._sbs_list_title_label.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Preferred,
        )
        self._sbs_list_header_layout.addWidget(self._sbs_list_title_label)

        self._apply_to_all_button = QPushButton("Apply to all")
        self._apply_to_all_button.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Preferred,
        )
        self._apply_to_all_button.setVisible(False)
        self._apply_to_all_button.clicked.connect(
            self._apply_dimensions_to_selected
        )
        self._sbs_list_header_layout.addWidget(self._apply_to_all_button)

        self._width_label = QLabel("W:")
        self._width_spinbox = QSpinBox()
        self._width_spinbox.setRange(1, 1_000_000)
        self._width_spinbox.setValue(100)
        self._height_label = QLabel("H:")
        self._height_spinbox = QSpinBox()
        self._height_spinbox.setRange(1, 1_000_000)
        self._height_spinbox.setValue(100)

        self._sbs_list_header_layout.addWidget(self._width_label)
        self._sbs_list_header_layout.addWidget(self._width_spinbox)
        self._sbs_list_header_layout.addWidget(self._height_label)
        self._sbs_list_header_layout.addWidget(self._height_spinbox)
        self._layout.addWidget(self._sbs_list_header_widget)

        self._sbs_list_widget = QListWidget()
        self._sbs_list_widget.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection
        )
        self._sbs_list_widget.setUniformItemSizes(True)
        self._sbs_list_widget.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Preferred,
        )
        self._sbs_list_widget.setMaximumHeight(5 * 24 + 2)
        self._layout.addWidget(self._sbs_list_widget)
        self._sbs_list_widget.itemSelectionChanged.connect(
            self._on_sbs_selection_changed
        )
        self._width_spinbox.valueChanged.connect(
            self._on_square_dimensions_changed
        )
        self._height_spinbox.valueChanged.connect(
            self._on_square_dimensions_changed
        )

        self._layout.addWidget(FrameSeparator(parent=self))

        self._save_nuclei_features_button = QPushButton("Save nuclei features")
        self._layout.addWidget(self._save_nuclei_features_button)

        self._save_status_label = QLabel("Not saved yet")
        self._save_status_label.setStyleSheet(
            "color: gray; font-style: italic;"
        )
        self._layout.addWidget(self._save_status_label)

        self._save_nuclei_features_button.clicked.connect(
            self._on_save_nuclei_features_button_pressed
        )

        self._project_list_widget.currentItemChanged.connect(
            self._project_selection_changed
        )
        self._load_current_stitched_image()

    def _add_sbs_list_entry(
        self,
        point_name: str,
        region_name: str | None,
        square_width: int,
        square_height: int,
    ) -> None:
        item = QListWidgetItem()
        point_widget = CLTSBSPointWidget(
            point_name,
            region_name,
            square_width,
            square_height,
            parent=self._sbs_list_widget,
        )
        item.setSizeHint(point_widget.sizeHint())
        self._sbs_list_widget.addItem(item)
        self._sbs_list_widget.setItemWidget(item, point_widget)

    def _update_sbs_list(self) -> None:
        self._sbs_list_widget.clear()

        if self._nuclei_centers_layer is None:
            return

        features = self._nuclei_centers_layer.features
        if len(features) != len(self._nuclei_centers_layer.data):
            return

        sbs_header = self._nuclei_features_headers["sbs_number"]
        width_header = self._nuclei_features_headers["square_width"]
        height_header = self._nuclei_features_headers["square_height"]

        for feature in features.to_dict(orient="records"):
            self._add_sbs_list_entry(
                point_name=f"SBS {int(feature[sbs_header])}",
                region_name=None,
                square_width=int(feature[width_header]),
                square_height=int(feature[height_header]),
            )

    def _on_sbs_selection_changed(self) -> None:
        selected_rows = [
            self._sbs_list_widget.row(item)
            for item in self._sbs_list_widget.selectedItems()
        ]
        self._apply_to_all_button.setVisible(len(selected_rows) > 1)

        if self._nuclei_centers_layer is None or not selected_rows:
            return

        features = self._nuclei_centers_layer.features
        if any(row >= len(features) for row in selected_rows):
            return

        selected_features = features.iloc[selected_rows]
        width_header = self._nuclei_features_headers["square_width"]
        height_header = self._nuclei_features_headers["square_height"]
        with (
            QSignalBlocker(self._width_spinbox),
            QSignalBlocker(self._height_spinbox),
        ):
            self._width_spinbox.setValue(
                int(selected_features[width_header].max())
            )
            self._height_spinbox.setValue(
                int(selected_features[height_header].max())
            )

    def _on_square_dimensions_changed(self, _value: int) -> None:
        if self._nuclei_centers_layer is None:
            return

        if len(self._sbs_list_widget.selectedItems()) > 1:
            return

        row = self._sbs_list_widget.currentRow()
        features = self._nuclei_centers_layer.features.copy()
        if row < 0 or row >= len(features):
            return

        feature_index = features.index[row]
        features.loc[
            feature_index,
            self._nuclei_features_headers["square_width"],
        ] = self._width_spinbox.value()
        features.loc[
            feature_index,
            self._nuclei_features_headers["square_height"],
        ] = self._height_spinbox.value()
        self._nuclei_centers_layer.features = features
        self._rebuild_nuclei_squares()

        item = self._sbs_list_widget.item(row)
        item_widget = self._sbs_list_widget.itemWidget(item)
        if isinstance(item_widget, CLTSBSPointWidget):
            item_widget.set_square_dimensions(
                self._width_spinbox.value(),
                self._height_spinbox.value(),
            )

    def _apply_dimensions_to_selected(self) -> None:
        if self._nuclei_centers_layer is None:
            return

        selected_rows = [
            self._sbs_list_widget.row(item)
            for item in self._sbs_list_widget.selectedItems()
        ]
        if len(selected_rows) < 2:
            return

        features = self._nuclei_centers_layer.features.copy()
        feature_indices = features.index[selected_rows]
        features.loc[
            feature_indices,
            self._nuclei_features_headers["square_width"],
        ] = self._width_spinbox.value()
        features.loc[
            feature_indices,
            self._nuclei_features_headers["square_height"],
        ] = self._height_spinbox.value()
        self._nuclei_centers_layer.features = features
        self._rebuild_nuclei_squares()

        for row in selected_rows:
            item = self._sbs_list_widget.item(row)
            item_widget = self._sbs_list_widget.itemWidget(item)
            if isinstance(item_widget, CLTSBSPointWidget):
                item_widget.set_square_dimensions(
                    self._width_spinbox.value(),
                    self._height_spinbox.value(),
                )

    def _project_selection_changed(self, *_args: object) -> None:
        self._load_current_stitched_image()

    def _on_show_squares_checkbox_toggled(self, checked: bool) -> None:
        if self._nuclei_squares_layer is not None:
            self._nuclei_squares_layer.visible = checked

    def _on_save_nuclei_features_button_pressed(self) -> None:
        if self._nuclei_centers_layer is None:
            self._save_status_label.setText("Couldn't save nuclei features")
            self._save_status_label.setStyleSheet(
                "color: #A80000; font-weight: bold; font-style: normal;"
            )
            show_error("No nuclei points layer is available to save.")
            return

        if self._nuclei_points_path is None:
            self._save_status_label.setText("Couldn't save nuclei features")
            self._save_status_label.setStyleSheet(
                "color: #A80000; font-weight: bold; font-style: normal;"
            )
            show_error("No project is selected for saving nuclei points.")
            return

        try:
            self._save_nuclei_points_layer()
            self._save_nuclei_features_table()
            saved_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self._save_status_label.setText(f"Last saved on: {saved_at}")
            self._save_status_label.setStyleSheet(
                "color: #29BA00; font-style: normal;"
            )
        except (OSError, ValueError) as exc:
            self._save_status_label.setText("Couldn't save nuclei features")
            self._save_status_label.setStyleSheet(
                "color: #A80000; font-weight: bold; font-style: normal;"
            )
            show_error(f"Could not save nuclei points: {exc}")

    def _save_nuclei_points_layer(self) -> None:
        if (
            self._nuclei_centers_layer is None
            or self._nuclei_points_path is None
        ):
            return

        self._nuclei_points_path.parent.mkdir(parents=True, exist_ok=True)
        self._nuclei_centers_layer.save(str(self._nuclei_points_path))

    def _save_nuclei_features_table(self) -> None:
        if (
            self._nuclei_centers_layer is None
            or self._nuclei_features_path is None
        ):
            return

        self._nuclei_features_path.parent.mkdir(parents=True, exist_ok=True)
        self._nuclei_centers_layer.features.to_csv(
            self._nuclei_features_path,
            index=False,
        )

    def _load_current_stitched_image(self) -> None:
        self._image_layer = None
        self._nuclei_centers_layer = None
        self._nuclei_squares_layer = None
        self._nuclei_segmentation_layer = None
        self._nuclei_points_path = None
        self._nuclei_features_path = None

        self._napari_viewer.layers.clear()

        project_path = self._project_list_widget.get_current_project_path()
        if project_path is None:
            return

        project_path = self._resolve_project_path(project_path)
        if project_path is None:
            return

        self._load_nuclei_file_paths(project_path)

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
        self._load_nuclei_layers()
        self._load_nuclei_features()
        self._update_sbs_list()

    def _load_nuclei_layers(self) -> None:
        if self._image_layer is None:
            return

        image_ndim = self._image_layer.ndim

        self._nuclei_squares_layer = self._napari_viewer.add_shapes(
            name="nuclei_squares",
            ndim=2,
        )
        self._on_show_squares_checkbox_toggled(
            self._show_squares_checkbox.isChecked()
        )

        if (
            self._nuclei_points_path is not None
            and self._nuclei_points_path.is_file()
        ):
            opened_points = self._napari_viewer.open(
                str(self._nuclei_points_path)
            )
            point_layers = (
                opened_points
                if isinstance(opened_points, list)
                else [opened_points]
            )
            self._nuclei_centers_layer = next(
                (layer for layer in point_layers if isinstance(layer, Points)),
                None,
            )
        else:
            self._nuclei_centers_layer = self._napari_viewer.add_points(
                name="nuclei_centers",
                ndim=image_ndim,
            )
            self._nuclei_centers_layer.current_properties = (
                self._current_nuclei_features
            )
            self._nuclei_centers_layer.face_color = "#999999"
            self._nuclei_centers_layer.current_face_color = "#999999"
            self._nuclei_centers_layer.size = 40
            self._nuclei_centers_layer.current_size = 40
            self._nuclei_centers_layer.border_color = "black"
            self._nuclei_centers_layer.current_border_color = "black"
            self._nuclei_centers_layer.text = "sbs_number"
            self._nuclei_centers_layer.text.color = "cyan"

        if self._nuclei_centers_layer is not None:
            self._nuclei_centers_layer.events.data.connect(
                self._on_nuclei_points_added
            )
            self._napari_viewer.layers.selection.active = (
                self._nuclei_centers_layer
            )

    def _on_nuclei_points_added(self, event: object) -> None:
        if getattr(event, "action", None) != ActionType.ADDED:
            return

        if self._nuclei_centers_layer is None:
            return

        features = self._nuclei_centers_layer.features.copy()
        if not self._validate_nuclei_features(features):
            return

        if len(features) != len(self._nuclei_centers_layer.data):
            return

        feature_index = features.index[-1]
        point = np.asarray(self._nuclei_centers_layer.data[-1], dtype=float)

        x_coord = float(point[-1])
        y_coord = float(point[-2]) if len(point) >= 2 else 0.0
        z_coord = float(point[-3]) if len(point) >= 3 else 0.0

        sbs_header = self._nuclei_features_headers["sbs_number"]
        existing_sbs_values = pd.to_numeric(
            features[sbs_header].iloc[:-1],
            errors="coerce",
        ).dropna()
        sbs_number = (
            int(existing_sbs_values.max()) + 1
            if not existing_sbs_values.empty
            else 1
        )

        features.loc[
            feature_index,
            self._nuclei_features_headers["x_coord"],
        ] = x_coord
        features.loc[
            feature_index,
            self._nuclei_features_headers["y_coord"],
        ] = y_coord
        features.loc[
            feature_index,
            self._nuclei_features_headers["z_coord"],
        ] = z_coord
        features.loc[feature_index, sbs_header] = sbs_number
        features.loc[
            feature_index,
            self._nuclei_features_headers["square_width"],
        ] = self._square_size_spinbox.value()
        features.loc[
            feature_index,
            self._nuclei_features_headers["square_height"],
        ] = self._square_size_spinbox.value()
        features.loc[
            feature_index,
            self._nuclei_features_headers["square_z_sections"],
        ] = self._z_sections_spinbox.value()
        self._nuclei_centers_layer.features = features
        self._rebuild_nuclei_squares()
        self._update_sbs_list()

    def _load_nuclei_features(self) -> None:
        if (
            self._nuclei_features_path is None
            or not self._nuclei_features_path.is_file()
            or self._nuclei_centers_layer is None
        ):
            return

        try:
            features = pd.read_csv(self._nuclei_features_path)
        except (
            OSError,
            UnicodeError,
            pd.errors.ParserError,
        ) as exc:
            show_error(f"Could not load nuclei features: {exc}")
            return

        number_of_points = len(self._nuclei_centers_layer.data)
        if len(features) != number_of_points:
            show_error(
                "The nuclei features table does not contain one row "
                f"per point. Points: {number_of_points}; "
                f"features: {len(features)}."
            )
            return

        if not self._validate_nuclei_features(features):
            return

        self._nuclei_centers_layer.features = features
        self._rebuild_nuclei_squares()

        maximum_sbs_number = (
            int(features["sbs_number"].max()) if not features.empty else 1
        )
        self._current_nuclei_features[
            self._nuclei_features_headers["sbs_number"]
        ] = np.array([maximum_sbs_number])
        self._nuclei_centers_layer.current_properties = (
            self._current_nuclei_features
        )
        self._nuclei_centers_layer.face_color = "#999999"
        self._nuclei_centers_layer.current_face_color = "#999999"
        self._nuclei_centers_layer.size = 40
        self._nuclei_centers_layer.current_size = 40
        self._nuclei_centers_layer.border_color = "black"
        self._nuclei_centers_layer.current_border_color = "black"
        self._nuclei_centers_layer.text = "sbs_number"
        self._nuclei_centers_layer.text.color = "cyan"

    def _validate_nuclei_features(self, features: pd.DataFrame) -> bool:
        required_headers = set(self._nuclei_features_headers.values())
        missing_headers = required_headers.difference(features.columns)

        if missing_headers:
            show_error(
                "The nuclei features table is missing required headers: "
                + ", ".join(sorted(missing_headers))
            )
            return False

        return True

    def _rebuild_nuclei_squares(self) -> None:
        if (
            self._nuclei_centers_layer is None
            or self._nuclei_squares_layer is None
        ):
            return

        points = np.asarray(self._nuclei_centers_layer.data, dtype=float)
        features = self._nuclei_centers_layer.features
        width_header = self._nuclei_features_headers["square_width"]
        height_header = self._nuclei_features_headers["square_height"]

        if len(points) != len(features):
            return

        squares = []
        for point, feature in zip(
            points,
            features.itertuples(index=False),
            strict=True,
        ):
            feature_values = feature._asdict()
            half_width = float(feature_values[width_header]) / 2
            half_height = float(feature_values[height_header]) / 2
            center = point[-2:]
            offsets = np.array(
                [
                    [-half_height, -half_width],
                    [half_height, -half_width],
                    [half_height, half_width],
                    [-half_height, half_width],
                ]
            )
            xy_vertices = center + offsets
            squares.append(xy_vertices)

        self._nuclei_squares_layer.data = squares
        self._nuclei_squares_layer.edge_color = "yellow"
        self._nuclei_squares_layer.face_color = "yellow"
        self._nuclei_squares_layer.opacity = 0.6
        self._nuclei_squares_layer.refresh()

    def _load_nuclei_file_paths(self, project_path: Path) -> None:
        pick_nuclei_directory = (
            project_path / PROJECT_FILE_DIR_NAME / PICK_NUCLEI_DIR_NAME
        )

        nuclei_paths = (
            pick_nuclei_directory / NUCLEI_POINTS_LAYER_FILE_NAME,
            pick_nuclei_directory / NUCLEI_POINTS_FEATURES_TABLE_FILE_NAME,
        )

        (
            self._nuclei_points_path,
            self._nuclei_features_path,
        ) = nuclei_paths

    @staticmethod
    def _resolve_project_path(starting_path: Path) -> Path | None:
        if starting_path.name.endswith(CLSP_PROJECT_SUFFIX):
            return starting_path

        project_paths = [
            path
            for path in starting_path.iterdir()
            if path.is_dir() and path.name.endswith(CLSP_PROJECT_SUFFIX)
        ]
        return project_paths[0] if project_paths else None

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
