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
    QSpinBox,
    QVBoxLayout,
    QWidget,
)
from superqt import QRangeSlider

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

        self._slider_zoom_container: QWidget = QWidget()
        self._slider_zoom_layout: QHBoxLayout = QHBoxLayout()
        self._slider_zoom_layout.setContentsMargins(0, 0, 0, 0)
        self._slider_zoom_container.setLayout(self._slider_zoom_layout)
        self._layout.addWidget(self._slider_zoom_container)

        self._set_slider_min_zero_button = QPushButton("Set 0")
        self._set_slider_min_zero_button.clicked.connect(
            self._set_slider_min_zero_button_pressed
        )
        self._slider_zoom_layout.addWidget(self._set_slider_min_zero_button)

        self._set_slider_min_to_lower_button = QPushButton("Set Min")
        self._set_slider_min_to_lower_button.clicked.connect(
            self._set_slider_min_to_lower_button_pressed
        )
        self._slider_zoom_layout.addWidget(
            self._set_slider_min_to_lower_button
        )

        self._decrease_slider_min_button = QPushButton("-10")
        self._decrease_slider_min_button.clicked.connect(
            self._decrease_slider_min_button_pressed
        )
        self._slider_zoom_layout.addWidget(self._decrease_slider_min_button)

        self._reset_slider_range_button = QPushButton("Reset")
        self._reset_slider_range_button.clicked.connect(
            self._reset_slider_range_button_pressed
        )
        self._slider_zoom_layout.addWidget(self._reset_slider_range_button)

        self._set_slider_current_button = QPushButton("Set current")
        self._set_slider_current_button.clicked.connect(
            self._set_slider_current_button_pressed
        )
        self._slider_zoom_layout.addWidget(self._set_slider_current_button)

        self._increase_slider_max_button = QPushButton("+10")
        self._increase_slider_max_button.clicked.connect(
            self._increase_slider_max_button_pressed
        )
        self._slider_zoom_layout.addWidget(self._increase_slider_max_button)

        self._set_slider_max_to_upper_button = QPushButton("Set Max")
        self._set_slider_max_to_upper_button.clicked.connect(
            self._set_slider_max_to_upper_button_pressed
        )
        self._slider_zoom_layout.addWidget(
            self._set_slider_max_to_upper_button
        )

        self._set_slider_max_full_button = QPushButton("65535")
        self._set_slider_max_full_button.clicked.connect(
            self._set_slider_max_full_button_pressed
        )
        self._slider_zoom_layout.addWidget(self._set_slider_max_full_button)

        self._contrast_slider: QRangeSlider = QRangeSlider(
            Qt.Orientation.Horizontal
        )
        self._contrast_slider.setRange(0, 65535)
        self._contrast_slider.setSingleStep(1)
        self._contrast_slider.setValue((1, 65535))
        self._contrast_slider.valueChanged.connect(
            self._on_range_slider_value_changed
        )
        self._layout.addWidget(self._contrast_slider)

        self._spin_boxes_container: QWidget = QWidget()
        self._spin_boxes_container_layout: QHBoxLayout = QHBoxLayout()
        self._spin_boxes_container_layout.setContentsMargins(0, 0, 0, 0)
        self._spin_boxes_container.setLayout(self._spin_boxes_container_layout)
        self._layout.addWidget(self._spin_boxes_container)

        self._min_label: QLabel = QLabel("Min")
        self._min_label.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed
        )
        self._spin_boxes_container_layout.addWidget(self._min_label)
        self._min_spin_box: QSpinBox = QSpinBox()
        self._min_spin_box.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        self._min_spin_box.setKeyboardTracking(False)
        self._min_spin_box.setRange(0, 65535)
        self._min_spin_box.setValue(1)
        self._min_spin_box.editingFinished.connect(
            self._on_min_spinbox_editing_finished
        )
        self._spin_boxes_container_layout.addWidget(self._min_spin_box)

        self._max_label: QLabel = QLabel("Max")
        self._max_label.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed
        )
        self._spin_boxes_container_layout.addWidget(self._max_label)
        self._max_spin_box: QSpinBox = QSpinBox()
        self._max_spin_box.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        self._max_spin_box.setKeyboardTracking(False)
        self._max_spin_box.setRange(0, 65535)
        self._max_spin_box.setValue(65535)
        self._max_spin_box.editingFinished.connect(
            self._on_max_spinbox_editing_finished
        )
        self._spin_boxes_container_layout.addWidget(self._max_spin_box)

    def _set_from_current_contrast_button_pressed(self) -> None:
        image_layer: Image = self._image_layer
        image_layer_contrasts: list[float | None] = image_layer.contrast_limits
        if all(contrast is not None for contrast in image_layer_contrasts):
            min_contrast: int = int(cast(int, image_layer_contrasts[0]))
            max_contrast: int = int(cast(int, image_layer_contrasts[1]))
            slider_min = min(self._contrast_slider.minimum(), min_contrast)
            slider_max = max(self._contrast_slider.maximum(), max_contrast)
            with QSignalBlocker(self._min_spin_box):
                self._min_spin_box.setValue(min_contrast)
            with QSignalBlocker(self._max_spin_box):
                self._max_spin_box.setValue(max_contrast)
            with QSignalBlocker(self._contrast_slider):
                self._contrast_slider.setRange(slider_min, slider_max)
                self._contrast_slider.setValue((min_contrast, max_contrast))
            set_layer_contrast_limits(
                self._image_layer, min_contrast, max_contrast
            )

    def _set_slider_bounds(self, slider_min: int, slider_max: int) -> None:
        slider_min = max(0, min(slider_min, 65535))
        slider_max = max(slider_min, min(slider_max, 65535))
        lower_value, upper_value = cast(
            tuple[int, int], self._contrast_slider.value()
        )
        lower_value = min(max(lower_value, slider_min), slider_max)
        upper_value = min(max(upper_value, slider_min), slider_max)
        if lower_value > upper_value:
            lower_value = upper_value

        with QSignalBlocker(self._contrast_slider):
            self._contrast_slider.setRange(slider_min, slider_max)
            self._contrast_slider.setValue((lower_value, upper_value))
        with QSignalBlocker(self._min_spin_box):
            self._min_spin_box.setValue(lower_value)
        with QSignalBlocker(self._max_spin_box):
            self._max_spin_box.setValue(upper_value)
        set_layer_contrast_limits(self._image_layer, lower_value, upper_value)

    def _set_slider_min_zero_button_pressed(self) -> None:
        slider_max = self._contrast_slider.maximum()
        self._set_slider_bounds(0, slider_max)

    def _set_slider_min_to_lower_button_pressed(self) -> None:
        lower_value, _ = cast(tuple[int, int], self._contrast_slider.value())
        slider_max = self._contrast_slider.maximum()
        self._set_slider_bounds(lower_value, slider_max)

    def _decrease_slider_min_button_pressed(self) -> None:
        slider_min = self._contrast_slider.minimum()
        slider_max = self._contrast_slider.maximum()
        self._set_slider_bounds(max(0, slider_min - 10), slider_max)

    def _reset_slider_range_button_pressed(self) -> None:
        self._set_slider_bounds(0, 65535)

    def _set_slider_current_button_pressed(self) -> None:
        lower_value, upper_value = cast(
            tuple[int, int], self._contrast_slider.value()
        )
        self._set_slider_bounds(lower_value, upper_value)

    def _increase_slider_max_button_pressed(self) -> None:
        slider_min = self._contrast_slider.minimum()
        slider_max = self._contrast_slider.maximum()
        self._set_slider_bounds(slider_min, min(65535, slider_max + 10))

    def _set_slider_max_to_upper_button_pressed(self) -> None:
        _, upper_value = cast(tuple[int, int], self._contrast_slider.value())
        slider_min = self._contrast_slider.minimum()
        self._set_slider_bounds(slider_min, upper_value)

    def _set_slider_max_full_button_pressed(self) -> None:
        slider_min = self._contrast_slider.minimum()
        self._set_slider_bounds(slider_min, 65535)

    def _on_min_spinbox_value_changed(self, value: int) -> None:
        max_value = max(value, self._max_spin_box.value())
        with QSignalBlocker(self._min_spin_box):
            self._min_spin_box.setValue(value)
        with QSignalBlocker(self._max_spin_box):
            self._max_spin_box.setValue(max_value)
        with QSignalBlocker(self._contrast_slider):
            self._contrast_slider.setValue((value, max_value))
        set_layer_contrast_limits(
            self._image_layer,
            self._min_spin_box.value(),
            self._max_spin_box.value(),
        )

    def _on_min_spinbox_editing_finished(self) -> None:
        self._on_min_spinbox_value_changed(self._min_spin_box.value())

    def _on_max_spinbox_value_changed(self, value: int) -> None:
        min_value = min(value, self._min_spin_box.value())
        with QSignalBlocker(self._min_spin_box):
            self._min_spin_box.setValue(min_value)
        with QSignalBlocker(self._max_spin_box):
            self._max_spin_box.setValue(value)
        with QSignalBlocker(self._contrast_slider):
            self._contrast_slider.setValue((min_value, value))
        set_layer_contrast_limits(
            self._image_layer,
            self._min_spin_box.value(),
            self._max_spin_box.value(),
        )

    def _on_max_spinbox_editing_finished(self) -> None:
        self._on_max_spinbox_value_changed(self._max_spin_box.value())

    def _on_range_slider_value_changed(self, values: tuple[int, int]) -> None:
        min_value, max_value = values
        with QSignalBlocker(self._min_spin_box):
            self._min_spin_box.setValue(min_value)
        with QSignalBlocker(self._max_spin_box):
            self._max_spin_box.setValue(max_value)
        set_layer_contrast_limits(self._image_layer, min_value, max_value)

    def set_contrast_limits(self, contrast_limits: list[float | None]) -> None:
        if any(contrast_limit is None for contrast_limit in contrast_limits):
            raise ValueError(
                f"The contrast_limits cannot be None: {contrast_limits}"
            )
        int_min = cast(int, contrast_limits[0])
        int_max = cast(int, contrast_limits[1])
        with QSignalBlocker(self._contrast_slider):
            self._contrast_slider.setValue((int_min, int_max))
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

        self._image_pairs_list: list[tuple[Image, Image]] = []

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
