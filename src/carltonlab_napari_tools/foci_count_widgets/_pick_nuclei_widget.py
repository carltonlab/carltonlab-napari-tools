from napari.layers import Image, Labels, Points, Shapes
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

from carltonlab_napari_tools._shared_widgets import FrameSeparator
from carltonlab_napari_tools.general_widgets._project_list_widget import (
    CLTProjectListWidget,
)


class CLTPickNucleiWidget(QWidget):
    def __init__(
        self,
        parent: QWidget,
        project_list_widget: CLTProjectListWidget,
    ) -> None:
        super().__init__(parent)

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
