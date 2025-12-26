from typing import TYPE_CHECKING

from napari.layers import Image, Layer, Shapes
from qtpy.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

if TYPE_CHECKING:
    from napari.components import ViewerModel


class RegionWidget(QWidget):
    def __init__(self, parent_widget: QWidget, napari_viewer: "ViewerModel"):
        super().__init__(parent_widget)
        self._napari_viewer = napari_viewer
        self._parent_widget = parent_widget

        self._selected_layer: Layer | None = None
        self._polyline_layer: Layer | None = None

        self._initialize_gui()

    def _initialize_gui(self):
        self._layout: QVBoxLayout = QVBoxLayout()
        self.setLayout(self._layout)

        self._image_title_label: QLabel = QLabel("Image layer")
        self._image_title_label.setStyleSheet("font-weight: bold")
        self._layout.addWidget(self._image_title_label)

        self._selected_image_line_edit: QLineEdit = QLineEdit("")
        self._selected_image_line_edit.setDisabled(True)
        self._layout.addWidget(self._selected_image_line_edit)

        self._select_image_button: QPushButton = QPushButton("Select")
        self._select_image_button.clicked.connect(
            self._select_layer_button_pressed
        )
        self._layout.addWidget(self._select_image_button)

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
        self._selected_layer = None
        self._polyline_layer = None

        self._selected_image_line_edit.setText("")
        self._spline_layer_line_edit.setText("")
        self._number_regions_spinner.setValue(7)

    def _select_layer_button_pressed(self) -> None:
        current_layer: Layer | None = (
            self._napari_viewer.layers.selection.active
        )
        if current_layer is None or not isinstance(current_layer, Image):
            self._reset_gui()
            return
        layer_title: str = current_layer.name
        self._selected_image_line_edit.setText(layer_title)
        self._selected_layer = current_layer

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
