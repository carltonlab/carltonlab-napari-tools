from collections.abc import Callable
from contextlib import suppress
from typing import TYPE_CHECKING
import tifffile

from napari.layers import Image, Layer, Points, Shapes

if TYPE_CHECKING:
    from napari.viewer import ViewerModel


def open_image_as_layer(
    napari_viewer: "ViewerModel",
    image_path: str,
    split_channel_axis: int | None = None,
) -> "Image | list[Image]":
    image_data = tifffile.imread(image_path)
    open_layers: Image | list[Image]
    if split_channel_axis is not None:
        open_layers = napari_viewer.add_image(
            image_data, channel_axis=split_channel_axis
        )
    else:
        open_layers = napari_viewer.add_image(image_data)
    return open_layers


def open_csv_as_shape_layer(
    napari_viewer: "ViewerModel", csv_path: str
) -> "Shapes | None":
    opened_layer = napari_viewer.open(csv_path)
    if isinstance(opened_layer[0], Shapes):
        return opened_layer[0]
    return None


def open_csv_as_points_layer(
    napari_viewer: "ViewerModel", csv_path: str
) -> "Points | None":
    opened_layer = napari_viewer.open(csv_path)
    if isinstance(opened_layer[0], Points):
        return opened_layer[0]
    return None


def create_points_layer(
    napari_viewer: "ViewerModel", layer_name: str, layer_dims: int = 2
) -> Points:
    points_layer = napari_viewer.add_points(name=layer_name, ndim=layer_dims)
    return points_layer


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


def get_image_contrasts(image_layer: Image) -> list[float | None]:
    contrasts: list[float | None] = image_layer.contrast_limits
    return contrasts


def get_image_path_from_layer(image_layer: Image) -> str | None:
    image_path: str | None = image_layer.source.path
    return image_path
