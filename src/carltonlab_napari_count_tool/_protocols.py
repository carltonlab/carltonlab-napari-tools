from typing import TYPE_CHECKING, Any, Protocol

from qtpy.QtWidgets import QPushButton, QWidget

if TYPE_CHECKING:
    from napari.viewer import ViewerModel


class MainWidgetCallBacks(Protocol):
    def set_current_widget(self, setting_widget: QWidget): ...


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
    def launch_widget(
        self, context_dict: dict[str, Any] | None = None
    ) -> QWidget | None: ...
