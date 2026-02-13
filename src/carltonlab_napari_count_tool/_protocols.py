from typing import TYPE_CHECKING, Protocol

from qtpy.QtWidgets import QPushButton, QWidget

if TYPE_CHECKING:
    from napari.layers import Image
    from napari.viewer import ViewerModel


class MainWidgetCallBacks(Protocol):
    def set_current_widget(self, setting_widget: QWidget): ...
    def get_process_control_images_and_paths(
        self,
    ) -> tuple[str, str, list[Image]] | None: ...


class CToolButton(Protocol):
    _button: QPushButton
    _button_text: str
    _launched_widget: QWidget | None

    def __init__(
        self, napari_viewer: "ViewerModel", main_widget: MainWidgetCallBacks
    ) -> None: ...

    def get_button(self) -> QPushButton: ...
    def deactivate_buttons(self) -> None: ...
    def activate_buttons(self) -> None: ...
    def launch_widget(self) -> QWidget | None: ...
