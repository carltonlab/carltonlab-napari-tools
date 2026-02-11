from typing import TYPE_CHECKING, Protocol, cast

from qtpy.QtCore import QRect, QSize, Qt
from qtpy.QtGui import QPainter, QShowEvent
from qtpy.QtWidgets import (
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
    QLabel,
)

from carltonlab_napari_count_tool._set_contrast_widget import SetContrastWidget
from carltonlab_napari_count_tool._multi_gonad_widget import (
    MakeMultiGonadWidget,
)
from carltonlab_napari_count_tool._pick_nuclei_widget import PickNucleiWidget
from carltonlab_napari_count_tool._regions_widget import RegionWidget
from carltonlab_napari_count_tool._score_nuclei_widget import ScoreNucleiWidget

if TYPE_CHECKING:
    import napari
    from napari.components import ViewerModel


class CToolButton(Protocol):
    _button: QPushButton
    _button_text: str
    _connecting_method_str: str

    def __init__(
        self, napari_viewer: "ViewerModel", main_widget: QWidget
    ) -> None: ...

    def get_button(self) -> QPushButton: ...
    def deactivate_buttons(self) -> None: ...
    def activate_buttons(self) -> None: ...


PREPARE_BUTTONS_LIST: dict[str, type[CToolButton]] = {}
BUTTONS_LIST: dict[str, type[CToolButton]] = {}


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


@_prepare_tools_buttons
class ExtractChannelsButton:
    _button: QPushButton
    _button_text: str
    _connecting_method_str: str

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


@_prepare_tools_buttons
class StitchGonads:
    _button: QPushButton
    _button_text: str
    _connecting_method_str: str

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


@_prepare_tools_buttons
class SetContrastButton:
    _button: QPushButton
    _button_text: str
    _connecting_method_str: str

    def __init__(
        self, napari_viewer: "ViewerModel", main_widget: QWidget
    ) -> None:
        self._napari_viewer = napari_viewer
        self._main_widget = main_widget

        self._button_text = "3.Set contrast"

        self._button = QPushButton(self._button_text)

        self._connecting_method_str = "_launch_set_contrast_widget"

    def get_button(self) -> QPushButton:
        return self._button

    def deactivate_buttons(self) -> None:
        self._button.setEnabled(False)

    def activate_buttons(self) -> None:
        self._button.setEnabled(True)


@_tool_button
class RegionsToolButtons:
    _button: QPushButton
    _button_text: str
    _connecting_method_str: str

    def __init__(
        self, napari_viewer: "ViewerModel", main_widget: QWidget
    ) -> None:
        self._napari_viewer = napari_viewer
        self._main_widget = main_widget

        self._button_text = "1.Define Regions"

        self._button: QPushButton = QPushButton(self._button_text)
        self._connecting_method_str = "_launch_regions_widget"

    def get_button(self) -> QPushButton:
        return self._button

    def deactivate_buttons(self) -> None:
        self._button.setEnabled(False)

    def activate_buttons(self) -> None:
        self._button.setEnabled(True)


@_tool_button
class NucleiPickerToolButtons:
    _button: QPushButton
    _button_text: str
    _connecting_method_str: str

    def __init__(
        self, napari_viewer: "ViewerModel", main_widget: QWidget
    ) -> None:
        self._napari_viewer = napari_viewer
        self._main_widget = main_widget

        self._button_text = "2.Pick Nuclei"

        self._button = QPushButton(self._button_text)

        self._connecting_method_str = "_launch_pick_nuclei_widget"

    def get_button(self) -> QPushButton:
        return self._button

    def deactivate_buttons(self) -> None:
        self._button.setEnabled(False)

    def activate_buttons(self) -> None:
        self._button.setEnabled(True)


@_tool_button
class MakeMultiGonadProjectButton:
    _button: QPushButton
    _button_text: str
    _connecting_method_str: str

    def __init__(
        self, napari_viewer: "ViewerModel", main_widget: QWidget
    ) -> None:
        self._napari_viewer = napari_viewer
        self._main_widget = main_widget

        self._button_text = "3.Make multi gonad project"

        self._button = QPushButton(self._button_text)

        self._connecting_method_str = "_launch_make_multi_gonad_widget"

    def get_button(self) -> QPushButton:
        return self._button

    def deactivate_buttons(self) -> None:
        self._button.setEnabled(False)

    def activate_buttons(self) -> None:
        self._button.setEnabled(True)


@_tool_button
class ScoreNucleiButton:
    _button: QPushButton
    _button_text: str
    _connecting_method_str: str

    def __init__(
        self, napari_viewer: "ViewerModel", main_widget: QWidget
    ) -> None:
        self._napari_viewer = napari_viewer
        self._main_widget = main_widget

        self._button_text = "4.Score Nuclei"

        self._button = QPushButton(self._button_text)

        self._connecting_method_str = "_launch_score_nuclei_widget"

    def get_button(self) -> QPushButton:
        return self._button

    def deactivate_buttons(self) -> None:
        self._button.setEnabled(False)

    def activate_buttons(self) -> None:
        self._button.setEnabled(True)


@_tool_button
class GenerateProjectReports:
    _button: QPushButton
    _button_text: str
    _connecting_method_str: str

    def __init__(
        self, napari_viewer: "ViewerModel", main_widget: QWidget
    ) -> None:
        self._napari_viewer = napari_viewer
        self._main_widget = main_widget

        self._button_text = "6.Generate Project Reports"

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


class CarltonLabCountTool(QWidget):
    # your QWidget.__init__ can optionally request the napari viewer instance
    # use a type annotation of 'napari.viewer.Viewer' for any parameter
    def __init__(self, viewer: "napari.viewer.Viewer"):  # type: ignore
        super().__init__()
        self._napari_viewer = viewer
        self._already_shown = False
        self._parent_widget = None
        self._current_orientation = "none"

        self._initialize_gui()

    def _initialize_gui(self) -> None:
        self._main_layout = QVBoxLayout()
        self.setLayout(self._main_layout)

        self._top_container: QWidget = QWidget()
        self._top_container_layout: QVBoxLayout = QVBoxLayout()
        self._top_container.setLayout(self._top_container_layout)

        self._top_scroll_area: QScrollArea = QScrollArea()
        self._top_scroll_area.setWidgetResizable(True)
        self._main_layout.addWidget(self._top_scroll_area)
        self._top_scroll_area.setWidget(self._top_container)

        self._prepare_container: QWidget = QWidget()
        self._prepare_container_layout: QVBoxLayout = QVBoxLayout()
        self._prepare_container.setLayout(self._prepare_container_layout)

        self._prepare_container_title: QLabel = QLabel("Prepare images")
        self._prepare_container_title.setStyleSheet("font-weight: bold")
        self._prepare_container_layout.addWidget(self._prepare_container_title)

        self._top_container_layout.addWidget(self._prepare_container)

        self._prepare_buttons_instances_dict: dict[str, CToolButton] = {}
        for class_name, class_ref in PREPARE_BUTTONS_LIST.items():
            self._prepare_buttons_instances_dict[class_name] = class_ref(
                self._napari_viewer, self
            )

        for class_instance in self._prepare_buttons_instances_dict.values():
            self._prepare_container_layout.addWidget(
                class_instance.get_button()
            )

        self._process_container: QWidget = QWidget()
        self._process_container_layout: QVBoxLayout = QVBoxLayout()
        self._process_container.setLayout(self._process_container_layout)

        self._process_container_title: QLabel = QLabel("Process images")
        self._process_container_title.setStyleSheet("font-weight: bold")
        self._process_container_layout.addWidget(self._process_container_title)

        self._top_container_layout.addWidget(self._process_container)

        self._buttons_instances_dict: dict[str, CToolButton] = {}
        for class_name, class_ref in BUTTONS_LIST.items():
            self._buttons_instances_dict[class_name] = class_ref(
                self._napari_viewer, self
            )

        for class_instance in self._buttons_instances_dict.values():
            self._process_container_layout.addWidget(
                class_instance.get_button()
            )

        self._top_container_layout.addStretch()

        self._connect_buttons()

    def _connect_buttons(self) -> None:
        for class_instance in self._buttons_instances_dict.values():
            connecting_method_str: str = class_instance._connecting_method_str
            button: QPushButton = class_instance.get_button()
            button.clicked.connect(getattr(self, connecting_method_str))
        for class_instance in self._prepare_buttons_instances_dict.values():
            connecting_method_str: str = class_instance._connecting_method_str
            button: QPushButton = class_instance.get_button()
            button.clicked.connect(getattr(self, connecting_method_str))

    ##################################################################
    #   Button connections
    ##################################################################

    def _launch_extract_channels_widget(self) -> None:
        print("launching extract channels widget")

    def _launch_stitch_gonads_widget(self) -> None:
        print("launching stitch gonads widget")

    def _launch_set_contrast_widget(self) -> None:
        setting_widget: SetContrastWidget = SetContrastWidget(
            self._napari_viewer, self
        )
        self._napari_viewer.window.add_dock_widget(
            setting_widget, name="clt Set Contrast"
        )

    def _generate_projects_reports_button_pressed(self) -> None:
        print("generating project reports")

    def _launch_pick_nuclei_widget(self) -> None:
        setting_widget = PickNucleiWidget(self, self._napari_viewer)
        self._napari_viewer.window.add_dock_widget(
            setting_widget, name="clt Pick Nuclei"
        )

    def _launch_make_multi_gonad_widget(self) -> None:
        setting_widget = MakeMultiGonadWidget(self, self._napari_viewer)
        self._napari_viewer.window.add_dock_widget(
            setting_widget, name="clt Make Multi Gonad Project"
        )

    def _launch_regions_widget(self) -> None:
        setting_widget = RegionWidget(self, self._napari_viewer)
        self._napari_viewer.window.add_dock_widget(
            setting_widget, name="clt Regions"
        )

    def _launch_score_nuclei_widget(self) -> None:
        setting_widget = ScoreNucleiWidget(self, self._napari_viewer)
        self._napari_viewer.window.add_dock_widget(
            setting_widget, name="clt Score Nuclei"
        )
