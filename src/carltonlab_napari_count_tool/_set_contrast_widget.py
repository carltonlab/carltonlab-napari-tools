from typing import cast

from napari.layers import Image
from napari.viewer import ViewerModel
from qtpy.QtCore import QSignalBlocker, Qt
from qtpy.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from carltonlab_napari_count_tool._model import (
    get_image_contrasts,
    verify_image_contrasts_file,
)
from carltonlab_napari_count_tool._protocols import (
    CToolButton,
    MainWidgetCallBacks,
)
from carltonlab_napari_count_tool._set_contrast_widget_model import (
    get_image_contrasts_from_file,
    save_contrasts,
    set_layer_contrast_limits,
)
from carltonlab_napari_count_tool._shared_widgets import clear_layout


class ContrastLimitWidget(QWidget):
    def __init__(
        self,
        napari_viewer: "ViewerModel",
        parent_widget: QWidget,
        image_layer: "Image",
        layer_index: int,
    ):
        super().__init__(parent_widget)
        self._napari_viewer = napari_viewer
        self._parent_widget = parent_widget
        self._image_layer = image_layer
        self._layer_index = layer_index

        self._layout = QVBoxLayout()
        self._layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(self._layout)

        self._title: QLabel = QLabel(
            f"Channel {self._layer_index + 1} --- {image_layer.name}"
        )
        self._title.setStyleSheet("font-weight: bold")
        self._layout.addWidget(self._title)

        self._set_from_current_contrast_button = QPushButton(
            "Set from viewer contrast"
        )
        self._set_from_current_contrast_button.clicked.connect(
            self._set_from_current_contrast_button_pressed
        )
        self._layout.addWidget(self._set_from_current_contrast_button)

        self._min_container: QWidget = QWidget()
        self._min_container_layout: QHBoxLayout = QHBoxLayout()
        self._min_container.setLayout(self._min_container_layout)
        self._layout.addWidget(self._min_container)

        self._min_label: QLabel = QLabel("Min")
        self._min_container_layout.addWidget(self._min_label)
        self._min_slider: QSlider = QSlider(Qt.Orientation.Horizontal)
        self._min_slider.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        self._min_slider.setRange(0, 65535)
        self._min_slider.setSingleStep(1)
        self._min_slider.setValue(1)
        self._min_slider.valueChanged.connect(
            self._on_min_spinbox_value_changed
        )
        self._min_container_layout.addWidget(self._min_slider)
        self._min_spin_box: QSpinBox = QSpinBox()
        self._min_spin_box.setRange(0, 65535)
        self._min_spin_box.setValue(1)
        self._min_spin_box.valueChanged.connect(
            self._on_min_spinbox_value_changed
        )
        self._min_container_layout.addWidget(self._min_spin_box)

        self._max_container: QWidget = QWidget()
        self._max_container_layout: QHBoxLayout = QHBoxLayout()
        self._max_container.setLayout(self._max_container_layout)
        self._layout.addWidget(self._max_container)

        self._max_label: QLabel = QLabel("Max")
        self._max_container_layout.addWidget(self._max_label)
        self._max_slider: QSlider = QSlider(Qt.Orientation.Horizontal)
        self._max_slider.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        self._max_slider.setRange(0, 65535)
        self._max_slider.setSingleStep(1)
        self._max_slider.setValue(65535)
        self._max_slider.valueChanged.connect(
            self._on_max_spinbox_value_changed
        )
        self._max_container_layout.addWidget(self._max_slider)
        self._max_spin_box: QSpinBox = QSpinBox()
        self._max_spin_box.setRange(0, 65535)
        self._max_spin_box.setValue(65535)
        self._max_spin_box.valueChanged.connect(
            self._on_max_spinbox_value_changed
        )
        self._max_container_layout.addWidget(self._max_spin_box)

    def _set_from_current_contrast_button_pressed(self) -> None:
        image_layer: Image = self._image_layer
        image_layer_contrasts: list[float | None] = image_layer.contrast_limits
        if all(contrast is not None for contrast in image_layer_contrasts):
            min_contrast: int = int(cast(int, image_layer_contrasts[0]))
            max_contrast: int = int(cast(int, image_layer_contrasts[1]))
            with QSignalBlocker(self._min_spin_box):
                self._min_spin_box.setValue(min_contrast)
            with QSignalBlocker(self._min_slider):
                self._min_slider.setValue(min_contrast)
            with QSignalBlocker(self._max_spin_box):
                self._max_spin_box.setValue(max_contrast)
            with QSignalBlocker(self._max_slider):
                self._max_slider.setValue(max_contrast)

    def _on_min_spinbox_value_changed(self, value) -> None:
        with QSignalBlocker(self._min_slider):
            self._min_slider.setValue(value)
        with QSignalBlocker(self._min_spin_box):
            self._min_spin_box.setValue(value)
        if self._max_slider.value() < value:
            with QSignalBlocker(self._max_slider):
                self._max_slider.setValue(value)
        if self._max_spin_box.value() < value:
            with QSignalBlocker(self._max_spin_box):
                self._max_spin_box.setValue(value)
        set_layer_contrast_limits(
            self._image_layer,
            self._min_spin_box.value(),
            self._max_spin_box.value(),
        )

    def _on_max_spinbox_value_changed(self, value) -> None:
        with QSignalBlocker(self._max_slider):
            self._max_spin_box.setValue(value)
        with QSignalBlocker(self._min_slider):
            self._max_slider.setValue(value)
        if self._min_spin_box.value() > self._max_spin_box.value():
            with QSignalBlocker(self._min_spin_box):
                self._min_spin_box.setValue(value)
        if self._min_slider.value() > self._max_slider.value():
            with QSignalBlocker(self._min_slider):
                self._min_slider.setValue(value)
        set_layer_contrast_limits(
            self._image_layer,
            self._min_spin_box.value(),
            self._max_spin_box.value(),
        )

    def set_contrast_limits(self, contrast_limits: list[float | None]) -> None:
        if any(contrast_limit is None for contrast_limit in contrast_limits):
            raise ValueError(
                f"The contrast_limits cannot be None: {contrast_limits}"
            )
        int_min = cast(int, contrast_limits[0])
        int_max = cast(int, contrast_limits[1])
        self._min_spin_box.setValue(int_min)
        self._max_spin_box.setValue(int_max)

    def get_contrast_limits(self) -> tuple[float, float]:
        float_min: float = float(self._min_spin_box.value())
        float_max: float = float(self._max_spin_box.value())
        return (float_min, float_max)


class SetContrastWidget(QWidget):
    def __init__(
        self,
        napari_viewer: "ViewerModel",
        parent_widget: MainWidgetCallBacks,
        image_tuple: tuple[Image, ...] | None = None,
        image_path: str | None = None,
        ctool_button: CToolButton | None = None,
    ):
        parent_q_widget: QWidget = cast(QWidget, parent_widget)
        super().__init__(parent_q_widget)

        self._napari_viewer = napari_viewer
        self._base_layer: Image
        self._scoring_layer: Image
        self._main_widget: MainWidgetCallBacks = parent_widget
        self._image_tuple: tuple[Image, ...] | None = None
        self._image_path: str | None = None
        self._ctool_button: CToolButton | None = ctool_button

        self._contrast_dict: dict[int, ContrastLimitWidget] = {}

        self._layout = QVBoxLayout()
        self.setLayout(self._layout)

        self._top_container: QWidget = QWidget()
        self._top_container_layout = QVBoxLayout()
        self._top_container.setLayout(self._top_container_layout)

        self._top_scroll_area: QScrollArea = QScrollArea()
        self._top_scroll_area.setWidgetResizable(True)
        self._top_scroll_area.setViewportMargins(0, 0, 10, 0)
        self._layout.addWidget(self._top_scroll_area, 1)
        self._top_scroll_area.setWidget(self._top_container)

        self._main_title_label = QLabel("CL Set Contrast")
        self._main_title_label.setStyleSheet(
            "font-weight: bold; font-size: 20px"
        )
        self._main_title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._top_container_layout.addWidget(self._main_title_label)

        self._no_image_open_label: QLabel = QLabel("No image open")
        self._no_image_open_label.setStyleSheet(
            "font-weight: bold; color: red;"
        )
        self._no_image_open_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._top_container_layout.addWidget(self._no_image_open_label)

        self._contrast_container: QWidget = QWidget()
        self._contrast_container_layout: QVBoxLayout = QVBoxLayout()
        self._contrast_container.setLayout(self._contrast_container_layout)
        self._top_container_layout.addWidget(self._contrast_container)

        self._save_container: QWidget = QWidget()
        self._save_container_layout: QVBoxLayout = QVBoxLayout()
        self._save_container_layout.setContentsMargins(0, 0, 0, 0)
        self._save_container.setLayout(self._save_container_layout)
        self._top_container_layout.addWidget(self._save_container)

        self._save_contrasts_button: QPushButton = QPushButton("Save")
        self._save_contrasts_button.clicked.connect(
            self._save_contrasts_button_pressed
        )
        self._save_container_layout.addWidget(self._save_contrasts_button)

        self._contrast_limit_saved_label: QLabel = QLabel("")
        self._save_container_layout.addWidget(self._contrast_limit_saved_label)

        self._set_save_image_label_state(False)

        self._top_container_layout.addStretch()

        if image_tuple is not None and image_path is not None:
            self.new_image_open(image_tuple, image_path)

    def new_image_open(
        self, image_tuple: tuple[Image, ...] | None, image_path: str | None
    ) -> None:
        self._image_tuple = image_tuple
        self._image_path = image_path
        self._create_contrast_widgets()
        self._load_contrasts()
        return

    def _create_contrast_widgets(self) -> None:
        image_tuple = self._image_tuple
        clear_layout(self._contrast_container_layout)
        if image_tuple is None:
            self._no_image_open_label.setVisible(True)
            self._save_container.setVisible(False)
            self._contrast_container.setVisible(False)
            return
        self._contrast_dict = {}
        for image_index, image in enumerate(image_tuple):
            adding_widget: ContrastLimitWidget = ContrastLimitWidget(
                self._napari_viewer, self, image, image_index
            )
            self._contrast_container_layout.addWidget(adding_widget)
            if image_index < len(image_tuple) - 1:
                self._contrast_container_layout.addSpacing(6)
                separator = QFrame(self._contrast_container)
                separator.setFrameShape(QFrame.Shape.HLine)
                separator.setFrameShadow(QFrame.Shadow.Sunken)
                separator.setStyleSheet("background-color: gray;")
                separator.setFixedHeight(2)
                self._contrast_container_layout.addWidget(separator)
                self._contrast_container_layout.addSpacing(6)
            self._contrast_dict[image_index] = adding_widget
        if len(image_tuple) > 0:
            self._contrast_container_layout.addSpacing(6)
            end_separator = QFrame(self._contrast_container)
            end_separator.setFrameShape(QFrame.Shape.HLine)
            end_separator.setFrameShadow(QFrame.Shadow.Sunken)
            end_separator.setStyleSheet("background-color: gray;")
            end_separator.setFixedHeight(2)
            self._contrast_container_layout.addWidget(end_separator)
            self._contrast_container_layout.addSpacing(6)
        self._no_image_open_label.setVisible(False)
        self._contrast_container.setVisible(True)
        self._save_container.setVisible(True)

    def _load_contrasts(self) -> None:
        image_tuple = self._image_tuple
        if image_tuple is None:
            return
        image_path = self._image_path
        if image_path is None:
            return
        for image_index, image_layer in enumerate(image_tuple):
            contrasts: list[float | None] = get_image_contrasts(image_layer)
            self._contrast_dict[image_index].set_contrast_limits(contrasts)
        validated_contrast_file: bool = verify_image_contrasts_file(image_path)
        if validated_contrast_file:
            loaded_contrasts: dict[int, tuple[float, float]] | None = (
                get_image_contrasts_from_file(image_path, image_tuple)
            )
            if loaded_contrasts is not None:
                for image_index, contrast_tuple in loaded_contrasts.items():
                    contrast_list: list[float | None] = cast(
                        list[float | None], contrast_tuple
                    )
                    self._contrast_dict[image_index].set_contrast_limits(
                        contrast_list
                    )
        self._set_save_image_label_state(validated_contrast_file)

    def _save_contrasts_button_pressed(self) -> None:
        if len(self._contrast_dict) == 0:
            print("The length of the contrast dict is 0")
            return
        if self._image_path is None:
            print(f"The image path is {self._image_path}")
            return
        saving_dict: dict[int, tuple[float, float]] = {}
        for saving_index, saving_value in self._contrast_dict.items():
            saving_dict[saving_index] = saving_value.get_contrast_limits()
        save_contrasts(self._napari_viewer, saving_dict, self._image_path)
        self._set_save_image_label_state(True)
        if self._ctool_button is not None:
            self._ctool_button.validate_property(self._image_path)

    def _set_save_image_label_state(self, state: bool) -> None:
        if state:
            self._contrast_limit_saved_label.setText("Contrasts limits saved")
            self._contrast_limit_saved_label.setStyleSheet("color: green")
        else:
            self._contrast_limit_saved_label.setText(
                "Contrasts limits not saved"
            )
            self._contrast_limit_saved_label.setStyleSheet("color: red")
