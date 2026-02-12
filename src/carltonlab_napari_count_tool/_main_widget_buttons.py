from typing import TYPE_CHECKING, Any

from qtpy.QtWidgets import QPushButton, QWidget

from carltonlab_napari_count_tool._protocols import CToolButton

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
    _launched_widget: QWidget

    def __init__(
        self, napari_viewer: "ViewerModel", main_widget: QWidget
    ) -> None:
        self._napari_viewer = napari_viewer
        self._main_widget = main_widget

        self._button_text = "1.Extract channels"

        self._button = QPushButton(self._button_text)

        self._connecting_method_str = "_launch_extract_channels_widget"

    def get_button(self) -> QPushButton:
        return self._button

    def deactivate_buttons(self) -> None:
        self._button.setEnabled(False)

    def activate_buttons(self) -> None:
        self._button.setEnabled(True)

    def launch_widget(
        self, context_dict: dict[str, Any] | None = None
    ) -> QWidget:
        return QWidget()


@_prepare_tools_buttons
class StitchGonads:
    _button: QPushButton
    _button_text: str
    _launched_widget: QWidget

    def __init__(
        self, napari_viewer: "ViewerModel", main_widget: QWidget
    ) -> None:
        self._napari_viewer = napari_viewer
        self._main_widget = main_widget

        self._button_text = "2.Stitch gonads"

        self._button = QPushButton(self._button_text)

        self._connecting_method_str = "_launch_stitch_gonads_widget"

    def get_button(self) -> QPushButton:
        return self._button

    def deactivate_buttons(self) -> None:
        self._button.setEnabled(False)

    def activate_buttons(self) -> None:
        self._button.setEnabled(True)

    def launch_widget(
        self, context_dict: dict[str, Any] | None = None
    ) -> QWidget:
        return QWidget()


@_tool_button
class SetContrastButton:
    _button: QPushButton
    _button_text: str
    _launched_widget: QWidget

    def __init__(
        self, napari_viewer: "ViewerModel", main_widget: QWidget
    ) -> None:
        self._napari_viewer = napari_viewer
        self._main_widget = main_widget

        self._button_text = "1.Set contrast"

        self._button = QPushButton(self._button_text)

        self._connecting_method_str = "_launch_set_contrast_widget"

    def get_button(self) -> QPushButton:
        return self._button

    def deactivate_buttons(self) -> None:
        self._button.setEnabled(False)

    def activate_buttons(self) -> None:
        self._button.setEnabled(True)

    def launch_widget(
        self, context_dict: dict[str, Any] | None = None
    ) -> QWidget:
        return QWidget()


@_tool_button
class RegionsToolButtons:
    _button: QPushButton
    _button_text: str
    _launched_widget: QWidget

    def __init__(
        self, napari_viewer: "ViewerModel", main_widget: QWidget
    ) -> None:
        self._napari_viewer = napari_viewer
        self._main_widget = main_widget

        self._button_text = "2.Define Regions"

        self._button: QPushButton = QPushButton(self._button_text)
        self._connecting_method_str = "_launch_regions_widget"

    def get_button(self) -> QPushButton:
        return self._button

    def deactivate_buttons(self) -> None:
        self._button.setEnabled(False)

    def activate_buttons(self) -> None:
        self._button.setEnabled(True)

    def launch_widget(
        self, context_dict: dict[str, Any] | None = None
    ) -> QWidget:
        return QWidget()


@_tool_button
class NucleiPickerToolButtons:
    _button: QPushButton
    _button_text: str
    _launched_widget: QWidget

    def __init__(
        self, napari_viewer: "ViewerModel", main_widget: QWidget
    ) -> None:
        self._napari_viewer = napari_viewer
        self._main_widget = main_widget

        self._button_text = "3.Pick Nuclei"

        self._button = QPushButton(self._button_text)

        self._connecting_method_str = "_launch_pick_nuclei_widget"

    def get_button(self) -> QPushButton:
        return self._button

    def deactivate_buttons(self) -> None:
        self._button.setEnabled(False)

    def activate_buttons(self) -> None:
        self._button.setEnabled(True)

    def launch_widget(
        self, context_dict: dict[str, Any] | None = None
    ) -> QWidget:
        return QWidget()


@_score_buttons
class MakeMultiGonadProjectButton:
    _button: QPushButton
    _button_text: str
    _launched_widget: QWidget

    def __init__(
        self, napari_viewer: "ViewerModel", main_widget: QWidget
    ) -> None:
        self._napari_viewer = napari_viewer
        self._main_widget = main_widget

        self._button_text = "1.Make multi gonad project"

        self._button = QPushButton(self._button_text)

        self._connecting_method_str = "_launch_make_multi_gonad_widget"

    def get_button(self) -> QPushButton:
        return self._button

    def deactivate_buttons(self) -> None:
        self._button.setEnabled(False)

    def activate_buttons(self) -> None:
        self._button.setEnabled(True)

    def launch_widget(
        self, context_dict: dict[str, Any] | None = None
    ) -> QWidget:
        return QWidget()


@_score_buttons
class ScoreNucleiButton:
    _button: QPushButton
    _button_text: str
    _launched_widget: QWidget

    def __init__(
        self, napari_viewer: "ViewerModel", main_widget: QWidget
    ) -> None:
        self._napari_viewer = napari_viewer
        self._main_widget = main_widget

        self._button_text = "2.Score Nuclei"

        self._button = QPushButton(self._button_text)

        self._connecting_method_str = "_launch_score_nuclei_widget"

    def get_button(self) -> QPushButton:
        return self._button

    def deactivate_buttons(self) -> None:
        self._button.setEnabled(False)

    def activate_buttons(self) -> None:
        self._button.setEnabled(True)

    def launch_widget(
        self, context_dict: dict[str, Any] | None = None
    ) -> QWidget:
        return QWidget()


@_results_buttons
class GenerateProjectReports:
    _button: QPushButton
    _button_text: str
    _launched_widget: QWidget

    def __init__(
        self, napari_viewer: "ViewerModel", main_widget: QWidget
    ) -> None:
        self._napari_viewer = napari_viewer
        self._main_widget = main_widget

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

    def launch_widget(
        self, context_dict: dict[str, Any] | None = None
    ) -> QWidget:
        return QWidget()
