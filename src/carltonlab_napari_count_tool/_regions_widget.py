import os
from pathlib import Path
from typing import TYPE_CHECKING

from napari.layers import Image, Layer, Shapes
from napari.utils.notifications import show_info
from qtpy.QtCore import QTimer
from qtpy.QtWidgets import (
    QFileDialog,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from carltonlab_napari_count_tool._model import (
    connect_callback_to_shape_double_click,
    open_csv_as_shape_layer,
    open_image_as_layer,
    save_layer_as_csv,
)
from carltonlab_napari_count_tool._shared_widgets import confirm_dialog

if TYPE_CHECKING:
    from napari.components import ViewerModel

DEFAULT_PROJECT_NAME = "cl_score_points_project"
SPLINE_NAME = "clt_regions_spline.csv"
REGIONS_DIR_NAME = "regions"


class RegionWidget(QWidget):
    def __init__(self, parent_widget: QWidget, napari_viewer: "ViewerModel"):
        super().__init__(parent_widget)
        self._napari_viewer = napari_viewer
        self._parent_widget = parent_widget

        self._image_layer: Image | None = None
        self._spline_layer: Shapes | None = None

        self._image_directory: str | None = None
        self._regions_path: str | None = None

        self._spline_completed_callback = self._on_shape_finished

        self._initialize_gui()

    def _initialize_gui(self):
        self._layout: QVBoxLayout = QVBoxLayout()
        self.setLayout(self._layout)

        self._image_title_label: QLabel = QLabel("Project Image")
        self._image_title_label.setStyleSheet("font-weight: bold")
        self._layout.addWidget(self._image_title_label)

        self._selected_image_line_edit: QLineEdit = QLineEdit("")
        self._selected_image_line_edit.setDisabled(True)
        self._layout.addWidget(self._selected_image_line_edit)

        self.open_image_button: QPushButton = QPushButton("Open")
        self.open_image_button.clicked.connect(self.open_image_button_pressed)
        self._layout.addWidget(self.open_image_button)

        self._spline_layer_title: QLabel = QLabel("Spline layer")
        self._spline_layer_title.setStyleSheet("font-weight: bold")
        self._layout.addWidget(self._spline_layer_title)

        self._spline_layer_line_edit: QLineEdit = QLineEdit("")
        self._spline_layer_line_edit.setDisabled(True)
        self._layout.addWidget(self._spline_layer_line_edit)

        self._save_spline_button: QPushButton = QPushButton("Save")
        self._save_spline_button.clicked.connect(
            self._save_spline_button_pressed
        )
        self._layout.addWidget(self._save_spline_button)

        self._numbers_region_label: QLabel = QLabel("Number of regions")
        self._numbers_region_label.setStyleSheet("font-weight: bold")
        self._layout.addWidget(self._numbers_region_label)

        self._number_regions_spinner: QSpinBox = QSpinBox()
        self._number_regions_spinner.setMinimum(1)
        self._number_regions_spinner.setMaximum(100)
        self._number_regions_spinner.setValue(7)
        self._number_regions_spinner.setSingleStep(1)
        self._layout.addWidget(self._number_regions_spinner)

        self._confirm_button: QPushButton = QPushButton("Confirm")
        self._layout.addWidget(self._confirm_button)

    def _reset_gui(self) -> None:
        self._image_layer = None
        self._spline_layer = None
        self._image_directory = None

        self._selected_image_line_edit.setText("")
        self._spline_layer_line_edit.setText("")
        self._number_regions_spinner.setValue(7)

    def open_image_button_pressed(self) -> None:
        if self._image_layer is not None:
            confirmed_result: bool = confirm_dialog(
                self._napari_viewer, "Image already open, open new project?"
            )
            if not confirmed_result:
                return

        self._reset_gui()
        file_dialog: QFileDialog = QFileDialog(
            self, caption="Select the project image"
        )
        file_path: str = file_dialog.getOpenFileName(
            filter="Image files (*.jpg *.jpeg *.png *.tif)"
        )[0]
        if file_path == "":
            return
        parent_dir: str = os.path.dirname(file_path)
        searching_project_path: str = os.path.join(
            parent_dir, DEFAULT_PROJECT_NAME
        )
        if os.path.exists(searching_project_path):
            show_info(
                f"The image is part of a project with path {searching_project_path} already exists. Loading project"
            )
            self._load_project(file_path)
            return
        self._create_new_project(file_path)
        self._update_layers_labels()

    def _create_new_project(self, file_path) -> None:
        parent_dir: str = os.path.dirname(file_path)
        file_name_path_obj: Path = Path(file_path)
        file_name_no_ext: str = file_name_path_obj.stem
        file_name_ext: str = file_name_path_obj.name
        new_project_path: str = os.path.join(
            parent_dir, file_name_no_ext + "_clscp"
        )
        if not os.path.exists(new_project_path):
            os.makedirs(new_project_path)
        image_new_path = os.path.join(new_project_path, file_name_ext)
        if not os.path.exists(image_new_path):
            os.rename(file_path, image_new_path)
        project_new_dir_path: str = os.path.join(
            new_project_path, DEFAULT_PROJECT_NAME
        )
        if not os.path.exists(project_new_dir_path):
            os.makedirs(project_new_dir_path)
        regions_path: str = os.path.join(
            project_new_dir_path, REGIONS_DIR_NAME
        )
        if not os.path.exists(regions_path):
            os.makedirs(regions_path)
        self._regions_path = regions_path

        self._image_layer = open_image_as_layer(
            self._napari_viewer, image_new_path
        )
        self._spline_layer = self._napari_viewer.add_shapes(
            name="clt-spline-layer"
        )
        # connect_callback_to_layer_data_event(
        #    self._spline_layer, self._spline_layer_changed_callback
        # )
        self._spline_layer.mouse_double_click_callbacks.append(
            self._on_shape_finished
        )
        self._update_layers_labels()

    def _load_project(self, image_path) -> None:
        parent_dir = os.path.dirname(image_path)
        self._image_layer = open_image_as_layer(
            self._napari_viewer, image_path
        )
        self._spline_layer = open_csv_as_shape_layer(
            self._napari_viewer,
            os.path.join(
                parent_dir, DEFAULT_PROJECT_NAME, REGIONS_DIR_NAME, SPLINE_NAME
            ),
        )
        if self._spline_layer is None:
            show_info("No spline layer found")
            return
        spline_layer: Layer = self._spline_layer
        connect_callback_to_shape_double_click(
            spline_layer, self._spline_completed_callback
        )
        QTimer.singleShot(0, self._interpolate_loaded_spline)
        self._update_layers_labels()

    def _interpolate_loaded_spline(self, tries_left: int = 10) -> None:
        layer = self._spline_layer
        if layer is None:
            return

        data_view = getattr(layer, "_data_view", None)
        if data_view is None:
            if tries_left > 0:
                QTimer.singleShot(
                    30, lambda: self._interpolate_loaded_spline(tries_left - 1)
                )
            return

        shapes = getattr(data_view, "shapes", None)
        if not shapes:  # still empty/not ready
            if tries_left > 0:
                QTimer.singleShot(
                    30, lambda: self._interpolate_loaded_spline(tries_left - 1)
                )
            return

        try:
            # IMPORTANT: ShapeList requires _update_displayed() to be called
            # from within batched_updates(), otherwise it raises AssertionError.
            with data_view.batched_updates():
                for shape_obj in shapes:
                    # Path/polyline interpolation lives on the shape object
                    shape_obj.interpolation_order = 3

                    # Path has this (ShapeList does NOT)
                    if hasattr(shape_obj, "_update_displayed_data"):
                        shape_obj._update_displayed_data()  # noqa: SLF001

                # Rebuild ShapeList caches used by the main (non-selected) visual
                data_view._update_displayed()  # noqa: SLF001

            layer.events.data()
            if hasattr(layer, "_update_thumbnail"):
                layer._update_thumbnail()
            layer.refresh()

        except (ValueError, RuntimeError) as e:
            print(f"[interp] failed: {e!r}, tries_left={tries_left}")
            if tries_left > 0:
                QTimer.singleShot(
                    30, lambda: self._interpolate_loaded_spline(tries_left - 1)
                )

    # def _interpolate_loaded_spline(self, tries_left: int = 10) -> None:
    #    layer = self._spline_layer
    #    if layer is None:
    #        return

    #    data_view = getattr(layer, "_data_view", None)
    #    if data_view is None:
    #        if tries_left > 0:
    #            QTimer.singleShot(
    #                30, lambda: self._interpolate_loaded_spline(tries_left - 1)
    #            )
    #        return

    #    shapes = getattr(data_view, "shapes", None)
    #    if not shapes:  # None or empty list => not ready yet
    #        if tries_left > 0:
    #            QTimer.singleShot(
    #                30, lambda: self._interpolate_loaded_spline(tries_left - 1)
    #            )
    #        return

    #    try:
    #        # 1) Set interpolation order on all shape objects
    #        for shape_object in shapes:
    #            shape_object.interpolation_order = 3

    #        # 2) Recompute displayed data (private)
    #        if hasattr(data_view, "_update_displayed_data"):
    #            data_view._update_displayed_data()  # noqa: SLF001

    #        # 3) Trigger the same event pathway as an edit:
    #        # re-assigning layer.data forces napari to rebuild display caches.
    #        layer.data = list(layer.data)

    #        layer.refresh()
    #    except Exception:
    #        if tries_left > 0:
    #            QTimer.singleShot(
    #                30, lambda: self._interpolate_loaded_spline(tries_left - 1)
    #            )

    # def _interpolate_loaded_spline(self, tries_left: int = 10) -> None:
    #    layer = self._spline_layer
    #    if layer is None:
    #        return

    #    data_view = getattr(layer, "_data_view", None)
    #    if data_view is None or not getattr(data_view, "shapes", None):
    #        # shapes not ready yet -> try again shortly
    #        if tries_left > 0:
    #            QTimer.singleShot(
    #                30, lambda: self._interpolate_loaded_spline(tries_left - 1)
    #            )
    #        return

    #    try:
    #        for shape_object in data_view.shapes:
    #            shape_object.interpolation_order = 3

    #        # Force the *whole* ShapeList to recompute displayed data (this is what edits trigger)
    #        data_view._update_displayed_data()  # noqa: SLF001

    #        layer.refresh()
    #    except Exception:
    #        # if anything goes wrong, retry a few times
    #        if tries_left > 0:
    #            QTimer.singleShot(
    #                30, lambda: self._interpolate_loaded_spline(tries_left - 1)
    #            )

    # def _interpolate_loaded_spline(self) -> None:
    #    if self._spline_layer is None:
    #        show_info("No spline layer to interpolate")
    #        return
    #    if self._spline_layer._data_view is None:
    #        show_info("No shapes list in the spline layer")
    #        return
    #    if not self._spline_layer._data_view.shapes:
    #        show_info("No spline created in the spline layer")
    #        return
    #    try:
    #        for shape_object in self._spline_layer._data_view.shapes:
    #            shape_object.interpolation_order = 3
    #            shape_object._update_displayed_vertices()
    #        self._spline_layer.refresh()
    #    except (IndexError, AttributeError, TypeError):
    #        pass

    def _update_layers_labels(self) -> None:
        if self._image_layer is not None:
            self._selected_image_line_edit.setText(self._image_layer.name)
        if self._spline_layer is not None:
            self._spline_layer_line_edit.setText(self._spline_layer.name)

    def _save_spline_button_pressed(self) -> None:
        if self._spline_layer is None:
            show_info("No spline layer to save")
            return
        shapes_list = self._spline_layer._data_view
        if not shapes_list:
            show_info("No shapes list in the spline layer")
            return
        if not len(shapes_list.shapes):
            show_info("No spline created in the spline layer")
            return
        if len(shapes_list.shapes) > 1:
            show_info(
                "Only one spline(shape) should be saved in the spline layer"
            )
            return
        if self._regions_path is None:
            show_info("No regions path set")
            return
        regions_path: str = self._regions_path
        save_layer_as_csv(
            self._spline_layer, os.path.join(regions_path, SPLINE_NAME)
        )

    def _on_shape_finished(self, layer, event):
        """Triggered only when the user double-clicks to finish a shape."""
        if len(layer.data) == 0:
            return
        try:
            shape_obj = layer._data_view.shapes[-1]
            shape_obj.interpolation_order = 3
            shape_obj._update_displayed_vertices()
            layer.refresh()
            print(f"Shape {len(layer.data)} completed and interpolated.")
        except (IndexError, AttributeError, TypeError):
            pass
