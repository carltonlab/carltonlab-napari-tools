from typing import TYPE_CHECKING, cast

from napari.layers import Image
from napari.utils.notifications import show_info
from qtpy.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from carltonlab_napari_tools._extract_channel_widget import (
    ExctractChannelsWidget,
)
from carltonlab_napari_tools._generate_results_widget import (
    GenerateResultsWidget,
)
from carltonlab_napari_tools._model import (
    close_all_non_set_image_layers,
    verify_all_sbs_created,
    verify_edited_regions_file,
    verify_image_contrasts_file,
)
from carltonlab_napari_tools._multi_gonad_widget import (
    MakeMultiGonadWidget,
)
from carltonlab_napari_tools._pick_nuclei_widget import PickNucleiWidget
from carltonlab_napari_tools._protocols import (
    CToolButton,
    MainWidgetCallBacks,
    ProcessWidgetAPI,
    ScoreWidgetAPI,
    ScoreWidgetButtonAPI,
)
from carltonlab_napari_tools._regions_widget import RegionWidget
from carltonlab_napari_tools._score_nuclei_widget import ScoreNucleiWidget
from carltonlab_napari_tools._set_contrast_widget import SetContrastWidget
from carltonlab_napari_tools.foci_count_widgets._stitch_widget import (
    StitchOmeZarrWidget,
)

if TYPE_CHECKING:
    from napari.viewer import ViewerModel

PREPARE_BUTTONS_LIST: dict[str, type[CToolButton]] = {}
BUTTONS_LIST: dict[str, type[CToolButton]] = {}
SCORE_BUTTONS_LIST: dict[str, type[CToolButton]] = {}
RESULTS_BUTTONS_LIST: dict[str, type[CToolButton]] = {}


def _tool_button(
    _setting_class: type[CToolButton],
) -> type[CToolButton]:
    BUTTONS_LIST[_setting_class.__name__] = _setting_class
    return _setting_class


def _prepare_tools_buttons(
    _setting_class: type[CToolButton],
) -> type[CToolButton]:
    PREPARE_BUTTONS_LIST[_setting_class.__name__] = _setting_class
    return _setting_class


def _score_buttons(
    _setting_class: type[CToolButton],
) -> type[CToolButton]:
    SCORE_BUTTONS_LIST[_setting_class.__name__] = _setting_class
    return _setting_class


def _results_buttons(
    _setting_class: type[CToolButton],
) -> type[CToolButton]:
    RESULTS_BUTTONS_LIST[_setting_class.__name__] = _setting_class
    return _setting_class


@_prepare_tools_buttons
class ExtractChannelsButton:
    _button: QPushButton
    _button_text: str
    _launched_widget: QWidget | None
    _widget_name: str
    _status_label: QLabel | None

    def __init__(
        self, napari_viewer: "ViewerModel", main_widget: MainWidgetCallBacks
    ) -> None:
        self._napari_viewer = napari_viewer
        self._main_widget: MainWidgetCallBacks = main_widget
        self._widget_name = "clt Extract Channels"
        self._status_label = None

        self._button_text = "1.Extract channels"

        self._button = QPushButton(self._button_text)
        self._button.clicked.connect(self.launch_widget)

        self._launched_widget = None

    def get_button(self) -> QPushButton:
        return self._button

    def get_status_label(self) -> QLabel | None:
        return self._status_label

    def deactivate_buttons(self) -> None:
        self._button.setEnabled(False)

    def activate_buttons(self) -> None:
        self._button.setEnabled(True)

    def launch_widget(self) -> QWidget | None:
        self._launched_widget = ExctractChannelsWidget(
            self._napari_viewer, self._main_widget, self
        )
        self._main_widget.set_prepare_widget(
            self._launched_widget, "clt Extract Channels"
        )

        return

    def set_status_label_state(self, state: bool) -> None:
        _ = state

    def validate_property(self, image_path: str) -> None:
        _ = image_path


@_prepare_tools_buttons
class StitchGonads:
    _button: QPushButton
    _button_text: str
    _launched_widget: QWidget | None
    _widget_name: str
    _status_label: QLabel | None

    def __init__(
        self, napari_viewer: "ViewerModel", main_widget: MainWidgetCallBacks
    ) -> None:
        self._napari_viewer = napari_viewer
        self._main_widget = main_widget
        self._widget_name = "clt Stitch Gonads"
        self._status_label = None

        self._button_text = "2.Stitch gonads"

        self._launched_widget = None

        self._button = QPushButton(self._button_text)
        self._button.clicked.connect(self.launch_widget)

    def get_button(self) -> QPushButton:
        return self._button

    def get_status_label(self) -> QLabel | None:
        return self._status_label

    def deactivate_buttons(self) -> None:
        self._button.setEnabled(False)

    def activate_buttons(self) -> None:
        self._button.setEnabled(True)

    def launch_widget(self) -> QWidget | None:
        self._launched_widget = StitchOmeZarrWidget(
            self._napari_viewer, self._main_widget, self
        )
        self._main_widget.set_prepare_widget(
            self._launched_widget, "clt Stitch OME.zarr"
        )
        return

    def set_status_label_state(self, state: bool) -> None:
        _ = state

    def validate_property(self, image_path: str) -> None:
        _ = image_path


@_tool_button
class SetContrastButton:
    _button: QPushButton
    _button_text: str
    _launched_widget: QWidget | None
    _widget_name: str
    _status_label: QLabel | None

    def __init__(
        self, napari_viewer: "ViewerModel", main_widget: MainWidgetCallBacks
    ) -> None:
        self._napari_viewer = napari_viewer
        self._main_widget = main_widget
        self._widget_name = "clt Set Contrast"
        self._status_label = QLabel("")

        self._button_text = "1.Set contrast"

        self._button = QPushButton(self._button_text)
        self._button.clicked.connect(self.launch_widget)

    def get_button(self) -> QPushButton:
        return self._button

    def get_status_label(self) -> QLabel | None:
        return self._status_label

    def deactivate_buttons(self) -> None:
        self._button.setEnabled(False)

    def activate_buttons(self) -> None:
        self._button.setEnabled(True)

    def launch_widget(self) -> QWidget | None:
        images_and_paths: tuple[str, str, list[Image]] | None = (
            self._main_widget.get_process_control_images_and_paths()
        )
        if images_and_paths is None:
            show_info(
                "Cannot open the contrast widget. No images and paths found at the control widget"
            )
            return
        continue_launch: bool = close_all_non_set_image_layers(
            self._napari_viewer, tuple(images_and_paths[2])
        )
        if not continue_launch:
            return
        image_path: str = images_and_paths[0]
        images: tuple[Image, ...] = tuple(images_and_paths[2])
        self._launched_widget = SetContrastWidget(
            self._napari_viewer, self._main_widget, images, image_path, self
        )
        process_widget: ProcessWidgetAPI = cast(
            ProcessWidgetAPI, self._launched_widget
        )
        self._main_widget.set_process_widget(process_widget, self._widget_name)
        return self._launched_widget

    def set_status_label_state(self, state: bool) -> None:
        if self._status_label is None:
            return
        if state:
            self._status_label.setText("Contrast set")
            self._status_label.setStyleSheet("color: green")
        else:
            self._status_label.setText("Contrast not set")
            self._status_label.setStyleSheet("color: red")

    def validate_property(self, image_path: str) -> None:
        verified_contrast_file: bool = verify_image_contrasts_file(image_path)
        self.set_status_label_state(verified_contrast_file)


@_tool_button
class RegionsToolButtons:
    _button: QPushButton
    _button_text: str
    _launched_widget: QWidget | None
    _widget_name: str
    _status_label: QLabel | None

    def __init__(
        self, napari_viewer: "ViewerModel", main_widget: MainWidgetCallBacks
    ) -> None:
        self._napari_viewer = napari_viewer
        self._main_widget = main_widget
        self._widget_name = "clt Regions"
        self._status_label = QLabel("")

        self._button_text = "2.Define Regions"

        self._button: QPushButton = QPushButton(self._button_text)
        self._button.clicked.connect(self.launch_widget)

    def get_button(self) -> QPushButton:
        return self._button

    def get_status_label(self) -> QLabel | None:
        return self._status_label

    def deactivate_buttons(self) -> None:
        self._button.setEnabled(False)

    def activate_buttons(self) -> None:
        self._button.setEnabled(True)

    def launch_widget(self) -> QWidget | None:
        images_and_paths: tuple[str, str, list[Image]] | None = (
            self._main_widget.get_process_control_images_and_paths()
        )
        if images_and_paths is None:
            show_info(
                "Cannot open the regions widget. No images and paths found at the control widget"
            )
            return
        continue_launch: bool = close_all_non_set_image_layers(
            self._napari_viewer, tuple(images_and_paths[2])
        )
        if not continue_launch:
            return
        image_path: str = images_and_paths[0]
        images: tuple[Image, ...] = tuple(images_and_paths[2])
        self._launched_widget = RegionWidget(
            self._napari_viewer, self._main_widget, images, image_path, self
        )
        process_widget: ProcessWidgetAPI = cast(
            ProcessWidgetAPI, self._launched_widget
        )
        self._main_widget.set_process_widget(process_widget, self._widget_name)
        return self._launched_widget

    def set_status_label_state(self, state: bool) -> None:
        if self._status_label is None:
            return
        if state:
            self._status_label.setText("Regions set")
            self._status_label.setStyleSheet("color: green")
        else:
            self._status_label.setText("Regions not set")
            self._status_label.setStyleSheet("color: red")

    def validate_property(self, image_path: str) -> None:
        verified_regions_file: bool = verify_edited_regions_file(image_path)
        self.set_status_label_state(verified_regions_file)


@_tool_button
class NucleiPickerToolButtons:
    _button: QPushButton
    _button_text: str
    _launched_widget: QWidget | None
    _widget_name: str
    _status_label: QLabel | None

    def __init__(
        self, napari_viewer: "ViewerModel", main_widget: MainWidgetCallBacks
    ) -> None:
        self._napari_viewer = napari_viewer
        self._main_widget = main_widget
        self._widget_name = "clt Pick Nuclei"
        self._status_label = QLabel("")

        self._button_text = "3.Pick Nuclei"

        self._button = QPushButton(self._button_text)
        self._button.clicked.connect(self.launch_widget)

    def get_button(self) -> QPushButton:
        return self._button

    def get_status_label(self) -> QLabel | None:
        return self._status_label

    def deactivate_buttons(self) -> None:
        self._button.setEnabled(False)

    def activate_buttons(self) -> None:
        self._button.setEnabled(True)

    def launch_widget(self) -> QWidget | None:
        images_and_paths: tuple[str, str, list[Image]] | None = (
            self._main_widget.get_process_control_images_and_paths()
        )
        if images_and_paths is None:
            show_info(
                "Cannot open the pick nuclei widget. No images and paths found at the control widget"
            )
            return
        continue_launch: bool = close_all_non_set_image_layers(
            self._napari_viewer, tuple(images_and_paths[2])
        )
        if not continue_launch:
            return
        image_path: str = images_and_paths[0]
        images: tuple[Image, ...] = tuple(images_and_paths[2])
        self._launched_widget = PickNucleiWidget(
            self._napari_viewer, self._main_widget, images, image_path, self
        )
        process_widget: ProcessWidgetAPI = cast(
            ProcessWidgetAPI, self._launched_widget
        )
        self._main_widget.set_process_widget(process_widget, self._widget_name)
        return self._launched_widget

    def set_status_label_state(self, state: bool) -> None:
        if self._status_label is None:
            return
        if state:
            self._status_label.setText("Nuclei set")
            self._status_label.setStyleSheet("color: green")
        else:
            self._status_label.setText("Nuclei not set")
            self._status_label.setStyleSheet("color: red")

    def validate_property(self, image_path: str) -> None:
        print(f"validating pick nuclei for image: {image_path}")
        self.set_status_label_state(verify_all_sbs_created(image_path))


@_score_buttons
class MakeMultiGonadProjectButton:
    _button: QPushButton
    _button_text: str
    _launched_widget: QWidget | None
    _widget_name: str
    _status_label: QLabel | None

    def __init__(
        self, napari_viewer: "ViewerModel", main_widget: MainWidgetCallBacks
    ) -> None:
        self._napari_viewer = napari_viewer
        self._main_widget = main_widget
        self._widget_name = "clt Make Multi Gonad Project"
        self._status_label = None

        self._button_text = "1.Make multi gonad project"

        self._button = QPushButton(self._button_text)
        self._button.clicked.connect(self.launch_widget)

    def get_button(self) -> QPushButton:
        return self._button

    def get_status_label(self) -> QLabel | None:
        return self._status_label

    def deactivate_buttons(self) -> None:
        self._button.setEnabled(False)

    def activate_buttons(self) -> None:
        self._button.setEnabled(True)

    def launch_widget(self) -> QWidget | None:
        self._launched_widget = MakeMultiGonadWidget(
            self._napari_viewer, self._main_widget
        )
        score_widget: ScoreWidgetAPI = cast(
            ScoreWidgetAPI, self._launched_widget
        )
        self._main_widget.set_score_widget(
            score_widget, "clt Make Multi Gonad Project"
        )
        return self._launched_widget

    def set_status_label_state(self, state: bool) -> None:
        _ = state

    def validate_property(self, image_path: str) -> None:
        _ = image_path


@_score_buttons
class ScoreNucleiButton:
    _button: QPushButton
    _button_text: str
    _launched_widget: QWidget | None
    _widget_name: str
    _status_label: QLabel | None

    def __init__(
        self, napari_viewer: "ViewerModel", main_widget: MainWidgetCallBacks
    ) -> None:
        self._napari_viewer = napari_viewer
        self._main_widget = main_widget
        self._widget_name = "clt Score Nuclei"
        self._status_label = None

        self._button_text = "2.Score Nuclei"

        self._button = QPushButton(self._button_text)
        self._button.clicked.connect(self.launch_widget)

        self._blind_checkbox: QCheckBox = QCheckBox("Blind file names")
        self._blind_checkbox.setChecked(True)
        self._shuffle_checkbox: QCheckBox = QCheckBox("Shuffle file list")
        self._shuffle_checkbox.setChecked(True)

        self._widgets_container: QWidget = QWidget()
        self._widgets_container_layout: QVBoxLayout = QVBoxLayout()
        self._widgets_container.setLayout(self._widgets_container_layout)
        self._widgets_container_layout.setContentsMargins(0, 0, 0, 0)
        self._widgets_container_layout.addWidget(self._button)
        self._checkboxes_container: QWidget = QWidget()
        self._checkboxes_container_layout: QHBoxLayout = QHBoxLayout()
        self._widgets_container_layout.addWidget(self._checkboxes_container)
        self._checkboxes_container.setLayout(self._checkboxes_container_layout)
        self._checkboxes_container_layout.setContentsMargins(0, 0, 0, 0)
        self._checkboxes_container_layout.addWidget(self._blind_checkbox)
        self._checkboxes_container_layout.addWidget(self._shuffle_checkbox)
        self._checkboxes_container_layout.addStretch()

    def get_button(self) -> QWidget:
        return self._widgets_container

    def get_blind_checkbox_state(self) -> bool:
        return self._blind_checkbox.isChecked()

    def get_shuffle_checkbox_state(self) -> bool:
        return self._shuffle_checkbox.isChecked()

    def get_status_label(self) -> QLabel | None:
        return self._status_label

    def deactivate_buttons(self) -> None:
        self._button.setEnabled(False)

    def activate_buttons(self) -> None:
        self._button.setEnabled(True)

    def launch_widget(self) -> QWidget:
        reference_as_API: ScoreWidgetButtonAPI = cast(
            ScoreWidgetButtonAPI, self
        )
        self._launched_widget = ScoreNucleiWidget(
            self._napari_viewer, self._main_widget, reference_as_API
        )
        self._launched_widget.set_blind_state(self.get_blind_checkbox_state())
        self._launched_widget.set_shuffle_state(
            self.get_shuffle_checkbox_state()
        )
        self._blind_checkbox.stateChanged.connect(
            lambda state: self._launched_widget.set_blind_state(bool(state))
        )
        self._shuffle_checkbox.stateChanged.connect(
            lambda state: self._launched_widget.set_shuffle_state(bool(state))
        )
        score_widget: ScoreWidgetAPI = cast(
            ScoreWidgetAPI, self._launched_widget
        )
        self._main_widget.set_score_widget(score_widget, "clt Score Nuclei")
        return self._launched_widget

    def set_status_label_state(self, state: bool) -> None:
        _ = state

    def validate_property(self, image_path: str) -> None:
        _ = image_path


@_results_buttons
class GenerateProjectReports:
    _button: QPushButton
    _button_text: str
    _launched_widget: QWidget | None
    _widget_name: str
    _status_label: QLabel | None

    def __init__(
        self, napari_viewer: "ViewerModel", main_widget: MainWidgetCallBacks
    ) -> None:
        self._napari_viewer = napari_viewer
        self._main_widget = main_widget
        self._widget_name = "clt Generate Reports"
        self._status_label = None

        self._button_text = "1.Generate Project Reports"

        self._button = QPushButton(self._button_text)
        self._button.clicked.connect(self.launch_widget)

    def get_button(self) -> QPushButton:
        return self._button

    def get_status_label(self) -> QLabel | None:
        return self._status_label

    def deactivate_buttons(self) -> None:
        self._button.setEnabled(False)

    def activate_buttons(self) -> None:
        self._button.setEnabled(True)

    def launch_widget(self) -> QWidget:
        self._launched_widget = GenerateResultsWidget(
            self._napari_viewer, self._main_widget
        )
        self._main_widget.set_prepare_widget(
            self._launched_widget, "clt Generate Project Reports"
        )
        return self._launched_widget

    def set_status_label_state(self, state: bool) -> None:
        _ = state

    def validate_property(self, image_path: str) -> None:
        _ = image_path
