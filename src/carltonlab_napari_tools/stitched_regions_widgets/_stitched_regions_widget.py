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

from carltonlab_napari_tools._shared_widgets import FrameSeparator
from carltonlab_napari_tools.general_widgets._project_list_widget import (
    CLTProjectListWidget,
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
        self._container_layout.addWidget(self._display_spline_button)

        self._save_spline_button = QPushButton("Save spline")
        self._container_layout.addWidget(self._save_spline_button)

        self._spline_status_label = QLabel("Spline not saved")
        self._container_layout.addWidget(self._spline_status_label)

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

        self._container_layout.addStretch()

        self.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
