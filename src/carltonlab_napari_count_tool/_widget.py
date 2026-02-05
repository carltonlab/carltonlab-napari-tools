from typing import TYPE_CHECKING, Protocol, cast

from qtpy.QtCore import QRect, QSize, Qt
from qtpy.QtGui import QPainter, QShowEvent
from qtpy.QtWidgets import (
    QDockWidget,
    QHBoxLayout,
    QMainWindow,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStyle,
    QStyleOptionButton,
    QVBoxLayout,
    QWidget,
)

from carltonlab_napari_count_tool._multi_gonad_widget import (
    MakeMultiGonadWidget,
)
from carltonlab_napari_count_tool._pick_nuclei_widget import PickNucleiWidget
from carltonlab_napari_count_tool._regions_widget import RegionWidget
from carltonlab_napari_count_tool._score_nuclei_widget import ScoreNucleiWidget

if TYPE_CHECKING:
    import napari
    from napari.components import ViewerModel


class VerticalButton(QPushButton):
    def __init__(self, text="", parent=None, rotation=-90):  # Defaulted to -90
        super().__init__(text, parent)
        self.rotation = rotation
        self.setSizePolicy(
            QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding
        )

    def sizeHint(self):
        s = super().sizeHint()
        # Uniform thickness based on font height
        thickness = self.fontMetrics().height() + 10
        return QSize(thickness, s.width())

    def minimumSizeHint(self):
        return self.sizeHint()

    def paintEvent(self, a0):
        painter = QPainter(self)
        option = QStyleOptionButton()
        self.initStyleOption(option)

        # We tell the style to draw into a rectangle
        # that matches the "flipped" dimensions.
        option.rect = QRect(0, 0, self.height(), self.width())

        if self.rotation == -90:
            # BOTTOM-TO-TOP (Counter-Clockwise)
            # 1. Move the 'origin' to the bottom-left of the button
            painter.translate(0, self.height())
            # 2. Rotate -90 degrees (upwards)
            painter.rotate(-90)
        else:
            # TOP-TO-BOTTOM (Clockwise)
            # 1. Move to top-right
            painter.translate(self.width(), 0)
            # 2. Rotate 90 degrees (downwards)
            painter.rotate(90)

        self.style().drawControl(
            QStyle.CE_PushButton,
            option,
            painter,
            self,
        )


class ToolButton(Protocol):
    _vert_button: QPushButton
    _hori_button: QPushButton
    _button_text: str
    _connecting_method_str: str

    def __init__(
        self, napari_viewer: "ViewerModel", main_widget: QWidget
    ) -> None: ...

    def get_button(self, orientation: str) -> QPushButton: ...
    def deactivate_buttons(self) -> None: ...
    def activate_buttons(self) -> None: ...


BUTTONS_LIST: dict[str, type[ToolButton]] = {}


def _tool_button(
    _setting_class: type[ToolButton],
) -> type[ToolButton]:
    BUTTONS_LIST[_setting_class.__name__] = _setting_class
    return _setting_class


@_tool_button
class RegionsToolButtons:
    _vert_button: QPushButton
    _hori_button: QPushButton
    _button_text: str
    _connecting_method_str: str

    def __init__(
        self, napari_viewer: "ViewerModel", main_widget: QWidget
    ) -> None:
        self._napari_viewer = napari_viewer
        self._main_widget = main_widget

        self._button_text = "1.Define Regions"

        self._vert_button = QPushButton(self._button_text)
        self._hori_button = VerticalButton(self._button_text)

        self._connecting_method_str = "_launch_regions_widget"

    def get_button(self, orientation: str) -> QPushButton:
        assert orientation in ["vertical", "horizontal"]
        if orientation == "vertical":
            return self._vert_button
        else:
            return self._hori_button

    def deactivate_buttons(self) -> None:
        self._vert_button.setEnabled(False)
        self._hori_button.setEnabled(False)

    def activate_buttons(self) -> None:
        self._vert_button.setEnabled(True)
        self._hori_button.setEnabled(True)


@_tool_button
class NucleiPickerToolButtons:
    _vert_button: QPushButton
    _hori_button: QPushButton
    _button_text: str
    _connecting_method_str: str

    def __init__(
        self, napari_viewer: "ViewerModel", main_widget: QWidget
    ) -> None:
        self._napari_viewer = napari_viewer
        self._main_widget = main_widget

        self._button_text = "2.Pick Nuclei"

        self._vert_button = QPushButton(self._button_text)
        self._hori_button = VerticalButton(self._button_text)

        self._connecting_method_str = "_launch_pick_nuclei_widget"

    def get_button(self, orientation: str) -> QPushButton:
        assert orientation in ["vertical", "horizontal"]
        if orientation == "vertical":
            return self._vert_button
        else:
            return self._hori_button

    def deactivate_buttons(self) -> None:
        self._vert_button.setEnabled(False)
        self._hori_button.setEnabled(False)

    def activate_buttons(self) -> None:
        self._vert_button.setEnabled(True)
        self._hori_button.setEnabled(True)


@_tool_button
class MakeMultiGonadProjectButton:
    _vert_button: QPushButton
    _hori_button: QPushButton
    _button_text: str
    _connecting_method_str: str

    def __init__(
        self, napari_viewer: "ViewerModel", main_widget: QWidget
    ) -> None:
        self._napari_viewer = napari_viewer
        self._main_widget = main_widget

        self._button_text = "3.Make multi gonad project"

        self._vert_button = QPushButton(self._button_text)
        self._hori_button = VerticalButton(self._button_text)

        self._connecting_method_str = "_launch_make_multi_gonad_widget"

    def get_button(self, orientation: str) -> QPushButton:
        assert orientation in ["vertical", "horizontal"]
        if orientation == "vertical":
            return self._vert_button
        else:
            return self._hori_button

    def deactivate_buttons(self) -> None:
        self._vert_button.setEnabled(False)
        self._hori_button.setEnabled(False)

    def activate_buttons(self) -> None:
        self._vert_button.setEnabled(True)
        self._hori_button.setEnabled(True)


@_tool_button
class ScoreNucleiButton:
    _vert_button: QPushButton
    _hori_button: QPushButton
    _button_text: str
    _connecting_method_str: str

    def __init__(
        self, napari_viewer: "ViewerModel", main_widget: QWidget
    ) -> None:
        self._napari_viewer = napari_viewer
        self._main_widget = main_widget

        self._button_text = "4.Score Nuclei"

        self._vert_button = QPushButton(self._button_text)
        self._hori_button = VerticalButton(self._button_text)

        self._connecting_method_str = "_launch_score_nuclei_widget"

    def get_button(self, orientation: str) -> QPushButton:
        assert orientation in ["vertical", "horizontal"]
        if orientation == "vertical":
            return self._vert_button
        else:
            return self._hori_button

    def deactivate_buttons(self) -> None:
        self._vert_button.setEnabled(False)
        self._hori_button.setEnabled(False)

    def activate_buttons(self) -> None:
        self._vert_button.setEnabled(True)
        self._hori_button.setEnabled(True)


@_tool_button
class GenerateProjectReports:
    _vert_button: QPushButton
    _hori_button: QPushButton
    _button_text: str
    _connecting_method_str: str

    def __init__(
        self, napari_viewer: "ViewerModel", main_widget: QWidget
    ) -> None:
        self._napari_viewer = napari_viewer
        self._main_widget = main_widget

        self._button_text = "6.Generate Project Reports"

        self._vert_button = QPushButton(self._button_text)
        self._hori_button = VerticalButton(self._button_text)

        self._connecting_method_str = (
            "_generate_projects_reports_button_pressed"
        )

    def get_button(self, orientation: str) -> QPushButton:
        assert orientation in ["vertical", "horizontal"]
        if orientation == "vertical":
            return self._vert_button
        else:
            return self._hori_button

    def deactivate_buttons(self) -> None:
        self._vert_button.setEnabled(False)
        self._hori_button.setEnabled(False)

    def activate_buttons(self) -> None:
        self._vert_button.setEnabled(True)
        self._hori_button.setEnabled(True)


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

        self._hori_layout = QHBoxLayout()
        self._hori_container = QWidget()
        self._hori_container.setLayout(self._hori_layout)

        self._hori_scroll_area = QScrollArea()
        self._hori_scroll_area.setWidget(self._hori_container)
        self._hori_scroll_area.setWidgetResizable(True)

        self._vert_layout = QVBoxLayout()
        self._vert_container = QWidget()
        self._vert_container.setLayout(self._vert_layout)

        self._vert_scroll_area = QScrollArea()
        self._vert_scroll_area.setWidget(self._vert_container)
        self._vert_scroll_area.setWidgetResizable(True)

        self._main_layout.addWidget(self._vert_scroll_area)
        self._main_layout.addWidget(self._hori_scroll_area)

        self._buttons_instances_dict: dict[str, ToolButton] = {}
        for class_name, class_ref in BUTTONS_LIST.items():
            self._buttons_instances_dict[class_name] = class_ref(
                self._napari_viewer, self
            )

        for class_instance in self._buttons_instances_dict.values():
            current_hori_button: QPushButton = class_instance.get_button(
                "horizontal"
            )
            self._hori_layout.addWidget(current_hori_button)
            self._vert_layout.addWidget(class_instance.get_button("vertical"))

        self._connect_buttons()

        self._hori_scroll_area.setVisible(False)
        self._vert_scroll_area.setVisible(False)

        self._hori_layout.addStretch()
        self._vert_layout.addStretch()

    def showEvent(self, a0: QShowEvent) -> None:
        if self._already_shown:
            return
        super().showEvent(a0)
        parent_widget: QWidget = cast(QWidget, self.parent())
        if isinstance(parent_widget, QDockWidget):
            self._parent_widget = parent_widget
            self._update_orientation()
            self._parent_widget.dockLocationChanged.connect(
                self._update_orientation
            )

    def _connect_buttons(self) -> None:
        for class_instance in self._buttons_instances_dict.values():
            connecting_method_str: str = class_instance._connecting_method_str
            hori_button: QPushButton = class_instance.get_button("horizontal")
            vert_button: QPushButton = class_instance.get_button("vertical")

            hori_button.clicked.connect(getattr(self, connecting_method_str))
            vert_button.clicked.connect(getattr(self, connecting_method_str))

    def _get_required_orientation(self) -> str | None:
        assert isinstance(self._parent_widget, QDockWidget)
        dock_widget: QDockWidget = cast(QDockWidget, self._parent_widget)
        main_window: QMainWindow = cast(QMainWindow, dock_widget.parent())
        dock_area: Qt.DockWidgetArea = main_window.dockWidgetArea(dock_widget)
        if (
            dock_area == Qt.LeftDockWidgetArea
            or dock_area == Qt.RightDockWidgetArea
            or dock_widget.isFloating()
        ):
            return "vertical"
        return "horizontal"

    def _update_orientation(self) -> None:
        required_orientation = self._get_required_orientation()
        if required_orientation == "vertical":
            self._vert_scroll_area.setVisible(True)
            self._hori_scroll_area.setVisible(False)
        else:
            self._vert_scroll_area.setVisible(False)
            self._hori_scroll_area.setVisible(True)

    def resizeEvent(self, a0):
        super().resizeEvent(a0)

        if not self._hori_scroll_area.isVisible():
            return

        viewport_height = self._hori_scroll_area.viewport().height()

        self._hori_container.setMinimumHeight(viewport_height)
        self._hori_container.setMaximumHeight(viewport_height)

        for i in range(self._hori_layout.count()):
            w = self._hori_layout.itemAt(i).widget()
            if w is not None:
                w.setFixedHeight(viewport_height)

    ##################################################################
    #   Button connections
    ##################################################################

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
