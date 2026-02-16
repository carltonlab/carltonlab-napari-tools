from typing import Protocol

from napari.layers import Image
from napari.viewer import ViewerModel
from qtpy.QtWidgets import QPushButton, QWidget


class ProcessWidgetAPI(Protocol):
    def new_image_open(
        self, image_tuple: tuple[Image, ...] | None, image_path: str | None
    ): ...
    def deleteLater(self): ...


class MainWidgetCallBacks(Protocol):
    def set_process_widget(
        self, setting_widget: ProcessWidgetAPI, widget_name: str
    ): ...
    def get_process_control_images_and_paths(
        self,
    ) -> tuple[str, str, list[Image]] | None: ...
    def get_process_widget(self) -> ProcessWidgetAPI | None: ...


class CToolButton(Protocol):
    _button: QPushButton
    _button_text: str
    _launched_widget: QWidget | None
    _widget_name: str

    def __init__(
        self, napari_viewer: "ViewerModel", main_widget: MainWidgetCallBacks
    ) -> None: ...

    def get_button(self) -> QPushButton: ...
    def deactivate_buttons(self) -> None: ...
    def activate_buttons(self) -> None: ...
    def launch_widget(self) -> QWidget | None: ...
