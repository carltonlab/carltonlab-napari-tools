import os
from pathlib import Path
from typing import TYPE_CHECKING

from napari.layers import Image, Layer, Shapes
from napari.utils.notifications import show_info
from qtpy.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from carltonlab_napari_count_tool._model import _open_image_as_layer
from carltonlab_napari_count_tool._shared_widgets import confirm_dialog

if TYPE_CHECKING:
    from napari.components import ViewerModel

DEFAULT_PROJECT_NAME = "cl_score_points_project"


class RegionWidget(QWidget):
    def __init__(self, parent_widget: QWidget, napari_viewer: "ViewerModel"):
        super().__init__(parent_widget)
        self._napari_viewer = napari_viewer
        self._parent_widget = parent_widget

        self._image_layer: Image | None = None
        self._polyline_layer: Layer | None = None

        self._image_directory: str | None = None
        self._project_data_path: str | None = None

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

        self._open_image_button: QPushButton = QPushButton("Open")
        self._open_image_button.clicked.connect(
            self._open_image_button_pressed
        )
        self._layout.addWidget(self._open_image_button)

        self._spline_layer_title: QLabel = QLabel("Spline layer")
        self._spline_layer_title.setStyleSheet("font-weight: bold")
        self._layout.addWidget(self._spline_layer_title)

        self._spline_layer_line_edit: QLineEdit = QLineEdit("")
        self._spline_layer_line_edit.setDisabled(True)
        self._layout.addWidget(self._spline_layer_line_edit)

        self._button_container_widget: QWidget = QWidget()
        self._button_container_layout: QHBoxLayout = QHBoxLayout()
        self._button_container_widget.setLayout(self._button_container_layout)
        self._layout.addWidget(self._button_container_widget)

        self._new_spline_layer_button: QPushButton = QPushButton("New")
        self._new_spline_layer_button.clicked.connect(
            self._new_spline_layer_button_pressed
        )
        self._button_container_layout.addWidget(self._new_spline_layer_button)
        self._select_spline_layer_button: QPushButton = QPushButton("Select")
        self._select_spline_layer_button.clicked.connect(
            self._select_spline_layer_button_pressed
        )
        self._button_container_layout.addWidget(
            self._select_spline_layer_button
        )

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
        self._polyline_layer = None
        self._image_directory = None

        self._selected_image_line_edit.setText("")
        self._spline_layer_line_edit.setText("")
        self._number_regions_spinner.setValue(7)

    def _open_image_button_pressed(self) -> None:
        print("")
        print(f"The image layer is: {self._image_layer}")

        if self._image_layer is not None:
            print("Confirming")
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

        file_name_path_obj: Path = Path(file_path)
        file_name_no_ext: str = file_name_path_obj.stem
        file_name_ext: str = file_name_path_obj.name
        new_project_path: str = os.path.join(
            parent_dir, file_name_no_ext + "_clscp"
        )
        os.makedirs(new_project_path)
        image_new_path = os.path.join(new_project_path, file_name_ext)
        os.rename(file_path, image_new_path)
        project_new_dir_path: str = os.path.join(
            new_project_path, DEFAULT_PROJECT_NAME
        )
        os.makedirs(project_new_dir_path)
        self._project_data_path = project_new_dir_path

        self._image_layer = _open_image_as_layer(
            self._napari_viewer, image_new_path
        )

        self._update_layers_labels()

    def _load_project(self, image_path) -> None:
        self._image_layer = _open_image_as_layer(
            self._napari_viewer, image_path
        )

        self._update_layers_labels()

    def _select_spline_layer_button_pressed(self) -> None:
        current_layer: Layer | None = (
            self._napari_viewer.layers.selection.active
        )
        if current_layer is None or not isinstance(current_layer, Shapes):
            self._polyline_layer = None
            self._spline_layer_line_edit.setText("")
            return
        layer_title: str = current_layer.name
        self._spline_layer_line_edit.setText(layer_title)
        self._polyline_layer = current_layer

    def _new_spline_layer_button_pressed(self) -> None:
        self._polyline_layer = self._napari_viewer.add_shapes(
            name="clt-spline-layer"
        )
        self._spline_layer_line_edit.setText(self._polyline_layer.name)

    def _update_layers_labels(self) -> None:
        if self._image_layer is not None:
            self._selected_image_line_edit.setText(self._image_layer.name)
        if self._polyline_layer is not None:
            self._spline_layer_line_edit.setText(self._polyline_layer.name)
