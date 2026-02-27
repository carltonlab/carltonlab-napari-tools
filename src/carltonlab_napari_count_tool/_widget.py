from typing import TYPE_CHECKING, cast

from napari.layers import Image
from napari.utils.notifications import show_info
from qtpy.QtCore import Qt, QTimer
from qtpy.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from carltonlab_napari_count_tool._model import (
    open_project_image,
    validate_closed_layers,
)
from carltonlab_napari_count_tool._shared_widgets import (
    get_directory,
    get_file,
)

if TYPE_CHECKING:
    import napari
    from napari.components import ViewerModel

from carltonlab_napari_count_tool._main_widget_buttons import (
    BUTTONS_LIST,
    PREPARE_BUTTONS_LIST,
    RESULTS_BUTTONS_LIST,
    SCORE_BUTTONS_LIST,
)
from carltonlab_napari_count_tool._protocols import (
    CToolButton,
    MainWidgetCallBacks,
    PrepareWidgetAPI,
    ProcessWidgetAPI,
    ScoreWidgetAPI,
    SummaryWidgetAPI,
)


class GonadControlWidget(QWidget):
    def __init__(
        self, napari_viewer: "ViewerModel", main_widget: QWidget
    ) -> None:
        super().__init__(main_widget)

        self._napari_viewer = napari_viewer
        self._main_widget = main_widget

        self._image_path: str | None = None
        self._image_layers: list[Image] | None = None
        self._project_files_dir: str | None = None

        self._layout = QVBoxLayout()
        self.setLayout(self._layout)
        self._layout.setContentsMargins(0, 0, 0, 5)

        self._image_container: QWidget = QWidget()
        self._image_container_layout: QHBoxLayout = QHBoxLayout()
        self._image_container.setLayout(self._image_container_layout)
        self._layout.addWidget(self._image_container)

        self._open_image_title: QLabel = QLabel("Image")
        self._open_image_title.setStyleSheet("font-weight: bold")
        self._image_container_layout.addWidget(self._open_image_title)

        self._open_image_line_edit: QLineEdit = QLineEdit("")
        self._image_container_layout.addWidget(self._open_image_line_edit)

        self._open_image_button: QPushButton = QPushButton("Open image")
        self._open_image_button.clicked.connect(
            self._open_image_button_pressed
        )
        self._layout.addWidget(self._open_image_button)

        self._open_zarr_button: QPushButton = QPushButton(
            "Open OME.zarr image"
        )
        self._open_zarr_button.clicked.connect(self._open_zarr_button_pressed)
        self._layout.addWidget(self._open_zarr_button)

        self._open_image_status_label: QLabel = QLabel("")
        self._layout.addWidget(self._open_image_status_label)
        self._set_open_image_status(False)

    def _open_image_button_pressed(self) -> None:
        validated_closed_layers: bool = validate_closed_layers(
            self._napari_viewer
        )
        if not validated_closed_layers:
            return
        image_path: str | None = get_file(
            self, "Select the project image file"
        )
        self._open_image_from_path(
            image_path, validated_closed_layers=validated_closed_layers
        )

    def _open_zarr_button_pressed(self) -> None:
        validated_closed_layers: bool = validate_closed_layers(
            self._napari_viewer
        )
        if not validated_closed_layers:
            return
        image_path: str | None = get_directory(
            self, "Select the OME.zarr directory"
        )
        if image_path is not None and not image_path.endswith(".zarr"):
            show_info("Please select a directory ending in .zarr")
            return
        self._open_image_from_path(
            image_path, validated_closed_layers=validated_closed_layers
        )

    def _open_image_from_path(
        self, image_path: str | None, validated_closed_layers: bool = False
    ) -> None:
        if not validated_closed_layers:
            validated_closed_layers = validate_closed_layers(
                self._napari_viewer
            )
        if not validated_closed_layers:
            return
        self._image_path = None
        self._image_layers = None
        self._project_files_dir = None
        main_widget_callbacks: MainWidgetCallBacks = cast(
            MainWidgetCallBacks, self._main_widget
        )
        if image_path is None:
            self.open_new_image_process_widget(
                main_widget_callbacks, self._image_layers, self._image_path
            )
            self.validate_process_results_widgets(
                main_widget_callbacks, self._image_path
            )
            self._open_image_line_edit.setText("")
            self._set_open_image_status(False)
            return
        open_answer: tuple[str, list[Image], str] | None = open_project_image(
            self._napari_viewer, image_path
        )
        if open_answer is None:
            self.open_new_image_process_widget(
                main_widget_callbacks, None, None
            )
            self.validate_process_results_widgets(
                main_widget_callbacks, self._image_path
            )
            self._open_image_line_edit.setText("")
            self._set_open_image_status(False)
            return
        self._image_path = open_answer[0]
        self._image_layers = open_answer[1]
        self._project_files_dir = open_answer[2]
        self.update_line_edit()
        self.open_new_image_process_widget(
            main_widget_callbacks, tuple(self._image_layers), self._image_path
        )
        self.validate_process_results_widgets(
            main_widget_callbacks, self._image_path
        )
        return

    def open_new_image_process_widget(
        self,
        main_widget_callbacks: MainWidgetCallBacks,
        images: tuple[Image, ...] | None,
        image_path: str | None,
    ) -> None:
        process_widget: ProcessWidgetAPI | None = (
            main_widget_callbacks.get_process_widget()
        )
        if process_widget is None:
            return
        process_widget.new_image_open(images, image_path)

    def get_images_and_paths(self) -> tuple[str, str, list[Image]] | None:
        if (
            self._image_path is None
            or self._image_layers is None
            or self._project_files_dir is None
        ):
            return None
        return (self._image_path, self._project_files_dir, self._image_layers)

    def _set_open_image_status(self, status: bool) -> None:
        if status:
            self._open_image_status_label.setText("Image opened")
            self._open_image_status_label.setStyleSheet("color: green")
        else:
            self._open_image_status_label.setText("Image not opened")
            self._open_image_status_label.setStyleSheet("color: red")

    def _close_current_counting_widget(self) -> None:
        self._main_widget.close_current_widget()  # type: ignore

    def update_line_edit(self) -> None:
        if self._image_path is None:
            self._open_image_line_edit.setText("")
            self._set_open_image_status(False)
            return
        self._open_image_line_edit.setText(self._image_path)
        self._set_open_image_status(True)

    def set_image_closed(self) -> None:
        self._image_path = None
        self._image_layers = None
        self._project_files_dir = None
        self._open_image_line_edit.setText("")
        self._set_open_image_status(False)

    def validate_process_results_widgets(
        self,
        main_widget_callbacks: MainWidgetCallBacks,
        image_path: str | None,
    ):
        if image_path is None:
            return
        main_widget_callbacks.validate_process_results(image_path)


class CarltonLabCountTool(QWidget):
    # your QWidget.__init__ can optionally request the napari viewer instance
    # use a type annotation of 'napari.viewer.Viewer' for any parameter
    def __init__(self, viewer: "napari.viewer.Viewer"):  # type: ignore
        super().__init__()
        self._napari_viewer = viewer
        self._already_shown = False
        self._parent_widget = None

        self._prepare_widget: PrepareWidgetAPI | None = None
        self._process_widget: ProcessWidgetAPI | None = None
        self._score_widget: ScoreWidgetAPI | None = None
        self._summary_widget: SummaryWidgetAPI | None = None
        self._score_nuclei_widget: QWidget | None = None
        self._scroll_timer: QTimer | None = None
        self._scroll_direction: int = 0
        self._scroll_interval_ms = 80
        self._scroll_interval_min_ms = 5
        self._scroll_interval_max_ms = 200

        self._initialize_gui()
        self._install_keybindings()

    def _initialize_gui(self) -> None:
        self._main_layout = QVBoxLayout()
        self.setLayout(self._main_layout)
        self._main_layout.setContentsMargins(25, 2, 2, 25)

        self._top_container: QWidget = QWidget()
        self._top_container_layout: QVBoxLayout = QVBoxLayout()
        self._top_container.setLayout(self._top_container_layout)

        self._top_scroll_area: QScrollArea = QScrollArea()
        self._top_scroll_area.setWidgetResizable(True)
        self._main_layout.addWidget(self._top_scroll_area)
        self._top_scroll_area.setWidget(self._top_container)

        self._main_title_label = QLabel("CL Count Tool")
        self._main_title_label.setStyleSheet(
            "font-weight: bold; font-size: 20px"
        )
        self._main_title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._top_container_layout.addWidget(self._main_title_label)

        self._prepare_container: QWidget = QWidget()
        self._prepare_container_layout: QVBoxLayout = QVBoxLayout()
        self._prepare_container.setLayout(self._prepare_container_layout)

        self._prepare_container_title: QLabel = QLabel("Prepare images")
        self._prepare_container_title.setStyleSheet("font-weight: bold")
        self._prepare_container_layout.addWidget(self._prepare_container_title)

        self._top_container_layout.addWidget(self._prepare_container)

        main_widget_casted: MainWidgetCallBacks = cast(
            MainWidgetCallBacks, self
        )

        self._prepare_buttons_instances_dict: dict[str, CToolButton] = {}
        for class_name, class_ref in PREPARE_BUTTONS_LIST.items():
            self._prepare_buttons_instances_dict[class_name] = class_ref(
                self._napari_viewer, main_widget_casted
            )

        for class_instance in self._prepare_buttons_instances_dict.values():
            self._prepare_container_layout.addWidget(
                class_instance.get_button()
            )

        first_section_separator: QFrame = QFrame(self)
        first_section_separator.setFrameShape(QFrame.Shape.HLine)
        first_section_separator.setFrameShadow(QFrame.Shadow.Sunken)
        first_section_separator.setStyleSheet("background-color: gray;")
        first_section_separator.setFixedHeight(2)
        self._top_container_layout.addWidget(first_section_separator)

        self._process_container: QWidget = QWidget()
        self._process_container_layout: QVBoxLayout = QVBoxLayout()
        self._process_container.setLayout(self._process_container_layout)

        self._process_container_title: QLabel = QLabel("Process gonads")
        self._process_container_title.setStyleSheet("font-weight: bold")
        self._process_container_layout.addWidget(self._process_container_title)

        self._process_gonads_control_widget: GonadControlWidget = (
            GonadControlWidget(self._napari_viewer, self)
        )

        self._process_container_layout.addWidget(
            self._process_gonads_control_widget
        )

        self._top_container_layout.addWidget(self._process_container)

        self._buttons_instances_dict: dict[str, CToolButton] = {}
        for class_name, class_ref in BUTTONS_LIST.items():
            self._buttons_instances_dict[class_name] = class_ref(
                self._napari_viewer, main_widget_casted
            )

        for class_instance in self._buttons_instances_dict.values():
            button_vbox_container: QWidget = QWidget()
            button_vbox_container_layout = QVBoxLayout()
            button_vbox_container_layout.setContentsMargins(0, 0, 0, 5)
            button_vbox_container.setLayout(button_vbox_container_layout)
            self._process_container_layout.addWidget(button_vbox_container)
            button_vbox_container_layout.addWidget(class_instance.get_button())
            status_label: QLabel | None = class_instance.get_status_label()
            if status_label is not None:
                button_vbox_container_layout.addWidget(status_label)
                class_instance.set_status_label_state(False)

        second_section_separator: QFrame = QFrame(self)
        second_section_separator.setFrameShape(QFrame.Shape.HLine)
        second_section_separator.setFrameShadow(QFrame.Shadow.Sunken)
        second_section_separator.setStyleSheet("background-color: gray;")
        second_section_separator.setFixedHeight(2)
        self._top_container_layout.addWidget(second_section_separator)

        self._score_container: QWidget = QWidget()
        self._score_container_layout: QVBoxLayout = QVBoxLayout()
        self._score_container.setLayout(self._score_container_layout)

        self._score_container_title: QLabel = QLabel("Score nuclei")
        self._score_container_title.setStyleSheet("font-weight: bold")
        self._score_container_layout.addWidget(self._score_container_title)

        self._top_container_layout.addWidget(self._score_container)

        self._score_buttons_instances_dict: dict[str, CToolButton] = {}
        for class_name, class_ref in SCORE_BUTTONS_LIST.items():
            self._score_buttons_instances_dict[class_name] = class_ref(
                self._napari_viewer, main_widget_casted
            )

        for class_instance in self._score_buttons_instances_dict.values():
            button_vbox_container: QWidget = QWidget()
            button_vbox_container_layout = QVBoxLayout()
            button_vbox_container_layout.setContentsMargins(0, 0, 0, 5)
            button_vbox_container.setLayout(button_vbox_container_layout)
            self._score_container_layout.addWidget(button_vbox_container)
            button_vbox_container_layout.addWidget(class_instance.get_button())
            status_label: QLabel | None = class_instance.get_status_label()
            if status_label is not None:
                button_vbox_container_layout.addWidget(status_label)
                class_instance.set_status_label_state(False)

        third_section_separator: QFrame = QFrame(self)
        third_section_separator.setFrameShape(QFrame.Shape.HLine)
        third_section_separator.setFrameShadow(QFrame.Shadow.Sunken)
        third_section_separator.setStyleSheet("background-color: gray;")
        third_section_separator.setFixedHeight(2)
        self._top_container_layout.addWidget(third_section_separator)

        self._results_container: QWidget = QWidget()
        self._results_container_layout: QVBoxLayout = QVBoxLayout()
        self._results_container.setLayout(self._results_container_layout)

        self._results_container_title: QLabel = QLabel("Results")
        self._results_container_title.setStyleSheet("font-weight: bold")
        self._results_container_layout.addWidget(self._results_container_title)

        self._top_container_layout.addWidget(self._results_container)

        self._results_buttons_instances_dict: dict[str, CToolButton] = {}
        for class_name, class_ref in RESULTS_BUTTONS_LIST.items():
            self._results_buttons_instances_dict[class_name] = class_ref(
                self._napari_viewer, main_widget_casted
            )

        for class_instance in self._results_buttons_instances_dict.values():
            self._results_container_layout.addWidget(
                class_instance.get_button()
            )

        self._top_container_layout.addStretch()

        self._main_layout.addSpacing(12)
        speed_separator: QFrame = QFrame(self)
        speed_separator.setFrameShape(QFrame.Shape.HLine)
        speed_separator.setFrameShadow(QFrame.Shadow.Sunken)
        speed_separator.setStyleSheet("background-color: gray;")
        speed_separator.setFixedHeight(2)
        self._main_layout.addWidget(speed_separator)
        self._main_layout.addSpacing(12)

        self._global_scroll_speed_container: QWidget = QWidget()
        self._global_scroll_speed_container_layout: QHBoxLayout = QHBoxLayout()
        self._global_scroll_speed_container_layout.setContentsMargins(
            0, 6, 0, 0
        )
        self._global_scroll_speed_container.setLayout(
            self._global_scroll_speed_container_layout
        )
        self._main_layout.addWidget(self._global_scroll_speed_container)

        self._global_scroll_speed_label: QLabel = QLabel("Scroll speed")
        self._global_scroll_speed_container_layout.addWidget(
            self._global_scroll_speed_label
        )

        self._global_scroll_speed_slider: QSlider = QSlider(
            Qt.Orientation.Horizontal
        )
        self._global_scroll_speed_slider.setRange(
            self._scroll_interval_min_ms, self._scroll_interval_max_ms
        )
        self._global_scroll_speed_slider.setValue(
            self._interval_to_slider_value(self._scroll_interval_ms)
        )
        self._global_scroll_speed_slider.setSingleStep(10)
        self._global_scroll_speed_slider.setPageStep(10)
        self._global_scroll_speed_slider.valueChanged.connect(
            self._scroll_speed_slider_changed
        )
        self._global_scroll_speed_container_layout.addWidget(
            self._global_scroll_speed_slider
        )

    ##################################################################
    #   Button connections
    ##################################################################

    def set_prepare_widget(
        self, setting_widget: PrepareWidgetAPI | None, widget_name: str
    ) -> None:
        self.close_other_widgets()
        if setting_widget is None:
            return
        self._prepare_widget = setting_widget
        self._napari_viewer.window.add_dock_widget(
            setting_widget, name=widget_name
        )
        return

    def get_process_widget(self) -> ProcessWidgetAPI | None:
        return self._process_widget

    def set_process_widget(
        self, setting_widget: ProcessWidgetAPI | None, widget_name: str
    ) -> None:
        self.close_other_widgets()
        if setting_widget is None:
            return
        self._process_widget = setting_widget
        self._napari_viewer.window.add_dock_widget(
            setting_widget, name=widget_name
        )

    def get_score_widget(self) -> ScoreWidgetAPI | None:
        return self._score_widget

    def set_score_widget(
        self, setting_widget: ScoreWidgetAPI | None, widget_name: str
    ) -> None:
        if setting_widget is None:
            return
        if not validate_closed_layers(self._napari_viewer):
            self._safe_delete_later(cast(QWidget, setting_widget))
            return
        self.close_other_widgets()
        self._score_widget = setting_widget
        self._score_nuclei_widget = cast(QWidget, setting_widget)
        self._napari_viewer.window.add_dock_widget(
            setting_widget, name=widget_name
        )

    def _safe_delete_later(self, widget: object | None) -> None:
        if widget is None:
            return
        if not isinstance(widget, QWidget):
            return
        try:
            widget.deleteLater()
        except RuntimeError:
            return

    def close_other_widgets(self) -> None:
        if self._prepare_widget is not None:
            try:
                parent_dock_widget: QWidget | None = (
                    self._prepare_widget.parent()
                )
            except RuntimeError:
                parent_dock_widget = None
            self._safe_delete_later(cast(QWidget, self._prepare_widget))
            self._prepare_widget = None
            if isinstance(parent_dock_widget, QWidget):
                self._safe_delete_later(parent_dock_widget)
        if self._process_widget is not None:
            try:
                parent_dock_widget: QWidget | None = (
                    self._process_widget.parent()
                )
            except RuntimeError:
                parent_dock_widget = None
            self._safe_delete_later(cast(QWidget, self._process_widget))
            self._process_widget = None
            if isinstance(parent_dock_widget, QWidget):
                self._safe_delete_later(parent_dock_widget)
        if self._score_widget is not None:
            try:
                parent_dock_widget: QWidget | None = (
                    self._score_widget.parent()
                )
            except RuntimeError:
                parent_dock_widget = None
            self._safe_delete_later(cast(QWidget, self._score_widget))
            self._score_widget = None
            self._score_nuclei_widget = None
            if isinstance(parent_dock_widget, QWidget):
                self._safe_delete_later(parent_dock_widget)
        if self._summary_widget is not None:
            try:
                parent_dock_widget: QWidget | None = (
                    self._summary_widget.parent()
                )
            except RuntimeError:
                parent_dock_widget = None
            self._safe_delete_later(cast(QWidget, self._summary_widget))
            self._summary_widget = None
            if isinstance(parent_dock_widget, QWidget):
                self._safe_delete_later(parent_dock_widget)

    def get_process_control_images_and_paths(
        self,
    ) -> tuple[str, str, list[Image]] | None:
        obtained_images_and_paths: tuple[str, str, list[Image]] | None = (
            self._process_gonads_control_widget.get_images_and_paths()
        )
        return obtained_images_and_paths

    def set_image_path(self, image_path: str, image_layer: Image) -> None:
        self._image_path = image_path
        self._image_layer = image_layer

    def get_image_path(self) -> tuple[str, Image] | None:
        if self._image_path is None or self._image_layer is None:
            return None
        return (self._image_path, self._image_layer)

    def validate_process_results(self, image_path: str) -> None:
        for class_instance in self._buttons_instances_dict.values():
            class_instance.validate_property(image_path)

    def _install_keybindings(self) -> None:
        self._napari_viewer.bind_key(
            "j", self._scroll_z_down_hold, overwrite=True
        )
        self._napari_viewer.bind_key(
            "l", self._scroll_z_up_hold, overwrite=True
        )
        self._napari_viewer.bind_key(
            "u", self._confirm_score_nuclei, overwrite=True
        )
        self._napari_viewer.bind_key(
            "i", self._increase_scroll_speed, overwrite=True
        )
        self._napari_viewer.bind_key(
            "k", self._decrease_scroll_speed, overwrite=True
        )
        if self._scroll_timer is None:
            self._scroll_timer = QTimer(self)
            self._scroll_timer.setInterval(self._scroll_interval_ms)
            self._scroll_timer.timeout.connect(self._scroll_timer_tick)

    def _get_scroll_axis(self) -> int | None:
        dims = self._napari_viewer.dims
        non_displayed = [
            axis for axis in range(dims.ndim) if axis not in dims.displayed
        ]
        candidate_axes = (
            non_displayed if non_displayed else list(range(dims.ndim))
        )
        axis_labels = [label.lower() for label in dims.axis_labels]
        for axis in candidate_axes:
            nsteps = dims.nsteps[axis]
            if nsteps is None or nsteps < 2:
                continue
            if axis < len(axis_labels) and axis_labels[axis] in (
                "z",
                "depth",
                "slice",
            ):
                return axis
        for axis in candidate_axes:
            nsteps = dims.nsteps[axis]
            if nsteps is not None and nsteps > 1:
                return axis
        return None

    def _scroll_z(self, delta: int) -> None:
        axis = self._get_scroll_axis()
        if axis is None:
            return
        dims = self._napari_viewer.dims
        nsteps = dims.nsteps[axis]
        if nsteps is None or nsteps < 1:
            return
        current_step = int(dims.current_step[axis])
        new_step = max(0, min(current_step + delta, nsteps - 1))
        if new_step == current_step:
            return
        dims.set_current_step(axis, new_step)

    def _start_scroll(self, delta: int) -> None:
        self._scroll_direction = delta
        self._scroll_z(delta)
        if (
            self._scroll_timer is not None
            and not self._scroll_timer.isActive()
        ):
            self._scroll_timer.start()

    def _stop_scroll(self, delta: int) -> None:
        if self._scroll_direction != delta:
            return
        self._scroll_direction = 0
        if self._scroll_timer is not None:
            self._scroll_timer.stop()

    def _scroll_timer_tick(self) -> None:
        if self._scroll_direction == 0:
            return
        self._scroll_z(self._scroll_direction)

    def _adjust_scroll_speed(self, delta_ms: int) -> None:
        new_interval = self._scroll_interval_ms + delta_ms
        new_interval = max(
            self._scroll_interval_min_ms,
            min(new_interval, self._scroll_interval_max_ms),
        )
        if new_interval == self._scroll_interval_ms:
            return
        self._scroll_interval_ms = new_interval
        if self._scroll_timer is not None:
            self._scroll_timer.setInterval(self._scroll_interval_ms)
        self.set_scroll_speed_slider_value(self._scroll_interval_ms)

    def set_scroll_interval_ms(self, interval_ms: int) -> None:
        new_interval = max(
            self._scroll_interval_min_ms,
            min(interval_ms, self._scroll_interval_max_ms),
        )
        if new_interval == self._scroll_interval_ms:
            return
        self._scroll_interval_ms = new_interval
        if self._scroll_timer is not None:
            self._scroll_timer.setInterval(self._scroll_interval_ms)
        self.set_scroll_speed_slider_value(self._scroll_interval_ms)

    def _increase_scroll_speed(self, event=None) -> None:
        self._adjust_scroll_speed(-10)

    def _decrease_scroll_speed(self, event=None) -> None:
        self._adjust_scroll_speed(10)

    def _scroll_z_down_hold(self, event=None):
        self._start_scroll(-1)
        yield
        self._stop_scroll(-1)

    def _scroll_z_up_hold(self, event=None):
        self._start_scroll(1)
        yield
        self._stop_scroll(1)

    def _confirm_score_nuclei(self, event=None) -> None:
        if self._score_nuclei_widget is None:
            return
        if not self._score_nuclei_widget.isVisible():
            return
        if hasattr(self._score_nuclei_widget, "_confirm_button_pressed"):
            self._score_nuclei_widget._confirm_button_pressed()

    def _scroll_speed_slider_changed(self, value: int) -> None:
        self.set_scroll_interval_ms(self._slider_value_to_interval(value))

    def set_scroll_speed_slider_value(self, value: int) -> None:
        self._global_scroll_speed_slider.blockSignals(True)
        self._global_scroll_speed_slider.setValue(
            self._interval_to_slider_value(value)
        )
        self._global_scroll_speed_slider.blockSignals(False)

    def _slider_value_to_interval(self, value: int) -> int:
        min_value = self._global_scroll_speed_slider.minimum()
        max_value = self._global_scroll_speed_slider.maximum()
        return max_value - (value - min_value)

    def _interval_to_slider_value(self, interval: int) -> int:
        min_value = self._global_scroll_speed_slider.minimum()
        max_value = self._global_scroll_speed_slider.maximum()
        return max_value - (interval - min_value)
