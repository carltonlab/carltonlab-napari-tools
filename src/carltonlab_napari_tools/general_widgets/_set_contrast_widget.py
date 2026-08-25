from typing import TYPE_CHECKING

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
from superqt import QRangeSlider

from carltonlab_napari_tools._shared_widgets import FrameSeparator
from carltonlab_napari_tools.general_widgets._project_list_widget import (
    CLTProjectListWidget,
)

if TYPE_CHECKING:
    from napari.viewer import ViewerModel


class CLTContrastLimitWidget(QWidget):
    def __init__(
        self,
        channel_index: int,
        display_name: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)

        self._channel_index = channel_index

        self._layout = QVBoxLayout()
        self._layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(self._layout)

        self._title_label = QLabel(
            f"Channel {channel_index + 1} --- {display_name}"
        )
        self._title_label.setStyleSheet("font-weight: bold")
        self._layout.addWidget(self._title_label)

        self._set_from_viewer_button = QPushButton("Set from viewer contrast")
        self._layout.addWidget(self._set_from_viewer_button)

        self._slider_controls_container = QWidget()
        self._slider_controls_layout = QHBoxLayout()
        self._slider_controls_layout.setContentsMargins(0, 0, 0, 0)
        self._slider_controls_container.setLayout(self._slider_controls_layout)
        self._layout.addWidget(self._slider_controls_container)

        self._set_min_zero_button = QPushButton("Set 0")
        self._set_min_button = QPushButton("Set Min")
        self._decrease_min_button = QPushButton("-10")
        self._reset_range_button = QPushButton("Reset")
        self._set_current_button = QPushButton("Set current")
        self._increase_max_button = QPushButton("+10")
        self._set_max_button = QPushButton("Set Max")
        self._set_max_full_button = QPushButton("65535")

        for button in (
            self._set_min_zero_button,
            self._set_min_button,
            self._decrease_min_button,
            self._reset_range_button,
            self._set_current_button,
            self._increase_max_button,
            self._set_max_button,
            self._set_max_full_button,
        ):
            self._slider_controls_layout.addWidget(button)

        self._contrast_slider = QRangeSlider(Qt.Orientation.Horizontal)
        self._contrast_slider.setRange(0, 65535)
        self._contrast_slider.setSingleStep(1)
        self._contrast_slider.setValue((1, 65535))
        self._layout.addWidget(self._contrast_slider)

        self._spin_boxes_container = QWidget()
        self._spin_boxes_layout = QHBoxLayout()
        self._spin_boxes_layout.setContentsMargins(0, 0, 0, 0)
        self._spin_boxes_container.setLayout(self._spin_boxes_layout)
        self._layout.addWidget(self._spin_boxes_container)

        self._min_label = QLabel("Min")
        self._spin_boxes_layout.addWidget(self._min_label)

        self._min_spin_box = QSpinBox()
        self._min_spin_box.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        self._min_spin_box.setKeyboardTracking(False)
        self._min_spin_box.setRange(0, 65535)
        self._min_spin_box.setValue(1)
        self._spin_boxes_layout.addWidget(self._min_spin_box)

        self._max_label = QLabel("Max")
        self._spin_boxes_layout.addWidget(self._max_label)

        self._max_spin_box = QSpinBox()
        self._max_spin_box.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        self._max_spin_box.setKeyboardTracking(False)
        self._max_spin_box.setRange(0, 65535)
        self._max_spin_box.setValue(65535)
        self._spin_boxes_layout.addWidget(self._max_spin_box)


class CLTContrastImageRow(QWidget):
    def __init__(
        self,
        display_name: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)

        self._layout = QHBoxLayout()
        self._layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(self._layout)

        self._name_label = QLabel(display_name)
        self._name_label.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Preferred,
        )
        self._layout.addWidget(self._name_label)


class CLTSetContrastWidget(QWidget):
    def __init__(
        self,
        napari_viewer: "ViewerModel",
        parent: QWidget,
        project_list_widget: CLTProjectListWidget,
    ) -> None:
        super().__init__(parent)

        self._napari_viewer = napari_viewer
        self._project_list_widget = project_list_widget

        self._layout = QVBoxLayout()
        self._layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(self._layout)

        self._scroll_area = QScrollArea()
        self._scroll_area.setWidgetResizable(True)
        self._scroll_area.setViewportMargins(0, 0, 0, 0)
        self._layout.addWidget(self._scroll_area)

        self._container = QWidget()
        self._container_layout = QVBoxLayout()
        self._container_layout.setContentsMargins(0, 0, 0, 0)
        self._container.setLayout(self._container_layout)
        self._scroll_area.setWidget(self._container)

        self._title_label = QLabel("CL Set Contrast")
        self._title_label.setStyleSheet("font-weight: bold; font-size: 20px")
        self._title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._container_layout.addWidget(self._title_label)

        self._container_layout.addWidget(
            FrameSeparator(parent=self._container)
        )

        self._project_label = QLabel("Current project")
        self._project_label.setStyleSheet("font-weight: bold")
        self._container_layout.addWidget(self._project_label)

        self._image_list_container = QWidget()
        self._image_list_layout = QVBoxLayout()
        self._image_list_layout.setContentsMargins(0, 0, 0, 0)
        self._image_list_container.setLayout(self._image_list_layout)
        self._container_layout.addWidget(self._image_list_container)

        self._contrast_container = QWidget()
        self._contrast_layout = QVBoxLayout()
        self._contrast_layout.setContentsMargins(0, 0, 0, 0)
        self._contrast_container.setLayout(self._contrast_layout)
        self._container_layout.addWidget(self._contrast_container)

        test_contrast_widget = CLTContrastLimitWidget(
            channel_index=0,
            display_name="Test channel",
            parent=self._contrast_container,
        )
        self._contrast_layout.addWidget(test_contrast_widget)

        self._container_layout.addStretch()
