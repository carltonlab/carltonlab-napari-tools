from typing import TYPE_CHECKING

from napari.layers import Image
from napari.utils.notifications import show_info
from qtpy.QtWidgets import QPushButton, QWidget

from carltonlab_napari_count_tool._protocols import (
    CToolButton,
    MainWidgetCallBacks,
)
from carltonlab_napari_count_tool._set_contrast_widget import SetContrastWidget

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

    def __init__(
        self, napari_viewer: "ViewerModel", main_widget: MainWidgetCallBacks
    ) -> None:
        self._napari_viewer = napari_viewer
        self._main_widget: MainWidgetCallBacks = main_widget
        self._widget_name = "clt Extract Channels"

        self._button_text = "1.Extract channels"

        self._button = QPushButton(self._button_text)
        self._button.clicked.connect(self.launch_widget)

        self._launched_widget = None

        self._connecting_method_str = "_launch_extract_channels_widget"

    def get_button(self) -> QPushButton:
        return self._button

    def deactivate_buttons(self) -> None:
        self._button.setEnabled(False)

    def activate_buttons(self) -> None:
        self._button.setEnabled(True)

    def launch_widget(self) -> QWidget | None:
        return


@_prepare_tools_buttons
class StitchGonads:
    _button: QPushButton
    _button_text: str
    _launched_widget: QWidget | None
    _widget_name: str

    def __init__(
        self, napari_viewer: "ViewerModel", main_widget: MainWidgetCallBacks
    ) -> None:
        self._napari_viewer = napari_viewer
        self._main_widget = main_widget
        self._widget_name = "clt Stitch Gonads"

        self._button_text = "2.Stitch gonads"

        self._launched_widget = None

        self._button = QPushButton(self._button_text)

        self._connecting_method_str = "_launch_stitch_gonads_widget"

    def get_button(self) -> QPushButton:
        return self._button

    def deactivate_buttons(self) -> None:
        self._button.setEnabled(False)

    def activate_buttons(self) -> None:
        self._button.setEnabled(True)

    def launch_widget(self) -> QWidget:
        return QWidget()


@_tool_button
class SetContrastButton:
    _button: QPushButton
    _button_text: str
    _launched_widget: QWidget | None
    _widget_name: str

    def __init__(
        self, napari_viewer: "ViewerModel", main_widget: MainWidgetCallBacks
    ) -> None:
        self._napari_viewer = napari_viewer
        self._main_widget = main_widget
        self._widget_name = "clt Set Contrast"

        self._button_text = "1.Set contrast"

        self._button = QPushButton(self._button_text)
        self._button.clicked.connect(self.launch_widget)

        self._connecting_method_str = "_launch_set_contrast_widget"

    def get_button(self) -> QPushButton:
        return self._button

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
        image_path: str = images_and_paths[0]
        images: tuple[Image, ...] = tuple(images_and_paths[2])
        self._launched_widget = SetContrastWidget(
            self._napari_viewer, self._main_widget, images, image_path
        )
        self._main_widget.set_current_widget(
            self._launched_widget, self._widget_name
        )
        return self._launched_widget


@_tool_button
class RegionsToolButtons:
    _button: QPushButton
    _button_text: str
    _launched_widget: QWidget | None
    _widget_name: str

    def __init__(
        self, napari_viewer: "ViewerModel", main_widget: MainWidgetCallBacks
    ) -> None:
        self._napari_viewer = napari_viewer
        self._main_widget = main_widget
        self._widget_name = "clt Regions"

        self._button_text = "2.Define Regions"

        self._button: QPushButton = QPushButton(self._button_text)
        self._connecting_method_str = "_launch_regions_widget"

    def get_button(self) -> QPushButton:
        return self._button

    def deactivate_buttons(self) -> None:
        self._button.setEnabled(False)

    def activate_buttons(self) -> None:
        self._button.setEnabled(True)

    def launch_widget(self) -> QWidget:
        return QWidget()


@_tool_button
class NucleiPickerToolButtons:
    _button: QPushButton
    _button_text: str
    _launched_widget: QWidget | None
    _widget_name: str

    def __init__(
        self, napari_viewer: "ViewerModel", main_widget: MainWidgetCallBacks
    ) -> None:
        self._napari_viewer = napari_viewer
        self._main_widget = main_widget
        self._widget_name = "clt Pick Nuclei"

        self._button_text = "3.Pick Nuclei"

        self._button = QPushButton(self._button_text)

        self._connecting_method_str = "_launch_pick_nuclei_widget"

    def get_button(self) -> QPushButton:
        return self._button

    def deactivate_buttons(self) -> None:
        self._button.setEnabled(False)

    def activate_buttons(self) -> None:
        self._button.setEnabled(True)

    def launch_widget(self) -> QWidget:
        return QWidget()


@_score_buttons
class MakeMultiGonadProjectButton:
    _button: QPushButton
    _button_text: str
    _launched_widget: QWidget | None
    _widget_name: str

    def __init__(
        self, napari_viewer: "ViewerModel", main_widget: MainWidgetCallBacks
    ) -> None:
        self._napari_viewer = napari_viewer
        self._main_widget = main_widget
        self._widget_name = "clt Make Multi Gonad Project"

        self._button_text = "1.Make multi gonad project"

        self._button = QPushButton(self._button_text)

        self._connecting_method_str = "_launch_make_multi_gonad_widget"

    def get_button(self) -> QPushButton:
        return self._button

    def deactivate_buttons(self) -> None:
        self._button.setEnabled(False)

    def activate_buttons(self) -> None:
        self._button.setEnabled(True)

    def launch_widget(self) -> QWidget:
        return QWidget()


@_score_buttons
class ScoreNucleiButton:
    _button: QPushButton
    _button_text: str
    _launched_widget: QWidget | None
    _widget_name: str

    def __init__(
        self, napari_viewer: "ViewerModel", main_widget: MainWidgetCallBacks
    ) -> None:
        self._napari_viewer = napari_viewer
        self._main_widget = main_widget
        self._widget_name = "clt Score Nuclei"

        self._button_text = "2.Score Nuclei"

        self._button = QPushButton(self._button_text)

        self._connecting_method_str = "_launch_score_nuclei_widget"

    def get_button(self) -> QPushButton:
        return self._button

    def deactivate_buttons(self) -> None:
        self._button.setEnabled(False)

    def activate_buttons(self) -> None:
        self._button.setEnabled(True)

    def launch_widget(self) -> QWidget:
        return QWidget()


@_results_buttons
class GenerateProjectReports:
    _button: QPushButton
    _button_text: str
    _launched_widget: QWidget | None
    _widget_name: str

    def __init__(
        self, napari_viewer: "ViewerModel", main_widget: MainWidgetCallBacks
    ) -> None:
        self._napari_viewer = napari_viewer
        self._main_widget = main_widget
        self._widget_name = "clt Generate Reports"

        self._button_text = "1.Generate Project Reports"

        self._button = QPushButton(self._button_text)

        self._connecting_method_str = (
            "_generate_projects_reports_button_pressed"
        )

    def get_button(self) -> QPushButton:
        return self._button

    def deactivate_buttons(self) -> None:
        self._button.setEnabled(False)

    def activate_buttons(self) -> None:
        self._button.setEnabled(True)

    def launch_widget(self) -> QWidget:
        return QWidget()
