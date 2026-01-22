from collections.abc import Callable
from contextlib import suppress
from typing import TYPE_CHECKING

from napari.layers import Image, Layer, Shapes

if TYPE_CHECKING:
    from napari.viewer import ViewerModel


def open_image_as_layer(
    napari_viewer: "ViewerModel", image_path: str
) -> "Image | None":
    opened_layer = napari_viewer.open(image_path)
    if isinstance(opened_layer[0], Image):
        return opened_layer[0]
    return None


def open_csv_as_shape_layer(
    napari_viewer: "ViewerModel", csv_path: str
) -> "Shapes | None":
    opened_layer = napari_viewer.open(csv_path)
    if isinstance(opened_layer[0], Shapes):
        return opened_layer[0]
    return None


def save_layer_as_csv(layer: Layer, csv_path: str) -> None:
    layer.save(csv_path)


def connect_callback_to_shape_double_click(
    layer: Layer, callback_function: Callable
) -> None:
    layer.mouse_double_click_callbacks.append(callback_function)


def disconnect_callback_to_shape_double_click(
    layer: Layer, callback_function: Callable
) -> None:
    with suppress(TypeError, ValueError):
        layer.mouse_double_click_callbacks.remove(callback_function)
