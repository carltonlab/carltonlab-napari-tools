import os
from pathlib import Path
from typing import TYPE_CHECKING

from napari.layers import Image, Shapes
from napari.utils.notifications import show_info
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
GOOD_LABEL_COLOR_CSS = "rgb(60,255,60)"
BAD_LABEL_COLOR_CSS = "rgb(255,60,60)"
SPLINE_SAVED_TEXT = "Spline saved"
SPLINE_NOT_SAVED_TEXT = "Spline not saved"


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

        self._display_spline_button = QPushButton("Display spline")
        self._display_spline_button.clicked.connect(self._display_spline)
        self._layout.addWidget(self._display_spline_button)

        self._save_spline_button: QPushButton = QPushButton("Save")
        self._save_spline_button.clicked.connect(
            self._save_spline_button_pressed
        )
        self._layout.addWidget(self._save_spline_button)

        self._spline_saved_label: QLabel = QLabel()
        self._layout.addWidget(self._spline_saved_label)
        self._set_spline_saved_state(False)

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
        # self._spline_layer.mouse_double_click_callbacks.append(
        #    self._on_shape_finished
        # )
        self._update_layers_labels()
        self._set_spline_saved_state(False)

    def _load_project(self, image_path) -> None:
        parent_dir = os.path.dirname(image_path)
        regions_path = os.path.join(
            parent_dir,
            DEFAULT_PROJECT_NAME,
            REGIONS_DIR_NAME,
        )
        self._regions_path = regions_path
        self._image_layer = open_image_as_layer(
            self._napari_viewer, image_path
        )
        spline_layer_path: str = os.path.join(
            parent_dir, DEFAULT_PROJECT_NAME, REGIONS_DIR_NAME, SPLINE_NAME
        )
        if not os.path.exists(spline_layer_path):
            show_info("No spline layer file found")
            self._spline_layer = self._napari_viewer.add_shapes(
                name="ctl-spline-layer"
            )
            self._set_spline_saved_state(False)
        else:
            self._spline_layer = open_csv_as_shape_layer(
                self._napari_viewer,
                os.path.join(
                    parent_dir,
                    DEFAULT_PROJECT_NAME,
                    REGIONS_DIR_NAME,
                    SPLINE_NAME,
                ),
            )
            self._display_spline()
            self._set_spline_saved_state(True)
        self._update_layers_labels()

    def _update_displayed_vertices(self, update_shape_index: int) -> None:
        if self._spline_layer is None:
            show_info("The spline layer is not set.")
            return
        spline_layer: Shapes = self._spline_layer
        shape_data = spline_layer._data_view.shapes[update_shape_index].data
        spline_layer._data_view.edit(update_shape_index, shape_data)
        spline_layer._data_view.shapes[
            update_shape_index
        ]._update_displayed_data()
        spline_layer.edge_width = 5
        spline_layer.refresh()

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
        spline_file_path = os.path.join(regions_path, SPLINE_NAME)
        if os.path.exists(spline_file_path):
            # ask to confirm_dialog
            dialog_result: bool = confirm_dialog(
                self._napari_viewer, "Spline file already exists, overwrite?"
            )
            if not dialog_result:
                return
            else:
                os.remove(spline_file_path)
        save_layer_as_csv(
            self._spline_layer, os.path.join(regions_path, SPLINE_NAME)
        )
        self._set_spline_saved_state(True)

    def _display_spline(self):
        if self._spline_layer is None:
            return
        spline_layer = self._spline_layer
        shape_obj = spline_layer._data_view.shapes[0]
        if shape_obj.interpolation_order > 1:
            return
        shape_obj.interpolation_order = 3
        shape_obj.edge_width = 5
        shape_data = shape_obj.data
        spline_layer._data_view.edit(0, shape_data)
        shape_obj._update_displayed_data()
        spline_layer.edge_width = 5
        spline_layer.refresh()

    def _on_shape_finished(self, layer, event):
        """Triggered only when the user double-clicks to finish a shape."""
        if len(layer.data) == 0:
            return
        shape_obj = layer._data_view.shapes[-1]
        if shape_obj.interpolation_order > 1:
            return
        try:
            shape_obj.interpolation_order = 3
            shape_obj.edge_width = 5
            shape_obj._update_displayed_vertices()
        except (IndexError, AttributeError, TypeError):
            pass

    def _set_spline_saved_state(self, saved_state: bool) -> None:
        if saved_state:
            self._spline_saved_label.setText(SPLINE_SAVED_TEXT)
            print(f"color: {GOOD_LABEL_COLOR_CSS}")
            self._spline_saved_label.setStyleSheet(
                f"color:{GOOD_LABEL_COLOR_CSS}"
            )
        else:
            self._spline_saved_label.setText(SPLINE_NOT_SAVED_TEXT)
            print(f"color: {BAD_LABEL_COLOR_CSS}")
            self._spline_saved_label.setStyleSheet(
                f"color:{BAD_LABEL_COLOR_CSS}"
            )
