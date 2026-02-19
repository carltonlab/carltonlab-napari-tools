import os
from collections.abc import Callable
from contextlib import suppress
from pathlib import Path
from typing import TYPE_CHECKING

import tifffile
from napari.layers import Image, Layer, Points, Shapes

from carltonlab_napari_count_tool._shared_variables import (
    DEFAULT_PROJECT_EXTENSION,
    DEFAULT_PROJECT_NAME,
    PICK_NUCLEI_DIR_NAME,
    REGIONS_DIR_NAME,
    RESULTS_DIR,
    SCORED_NUCLEI_DIR_NAME,
)

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


def verify_project_directory_from_image_path(
    image_path: str, create_project_if_not_exist: bool = False
) -> bool | str:
    image_dir_name: str = os.path.dirname(image_path)
    searching_project_path: str = os.path.join(
        image_dir_name, DEFAULT_PROJECT_NAME
    )
    if os.path.exists(searching_project_path):
        return True
    if create_project_if_not_exist:
        new_image_path: str = create_project_dir_structure(image_path)
        return new_image_path
    return False


def create_project_dir_structure(image_path: str) -> str:
    parent_dir_path: str = os.path.dirname(image_path)
    image_file_path_object: Path = Path(image_path)
    image_file_name_no_ext: str = image_file_path_object.stem
    image_file_name: str = image_file_path_object.name
    new_project_path: str = os.path.join(
        parent_dir_path, image_file_name_no_ext + DEFAULT_PROJECT_EXTENSION
    )
    os.makedirs(new_project_path, exist_ok=True)
    new_image_path: str = os.path.join(new_project_path, image_file_name)
    if not os.path.exists(new_image_path):
        os.rename(image_path, new_image_path)
    project_files_dir: str = os.path.join(
        new_project_path, DEFAULT_PROJECT_NAME
    )
    os.makedirs(project_files_dir, exist_ok=True)
    regions_path: str = os.path.join(project_files_dir, REGIONS_DIR_NAME)
    os.makedirs(regions_path, exist_ok=True)
    pick_nuclei_dir: str = os.path.join(
        project_files_dir, PICK_NUCLEI_DIR_NAME
    )
    os.makedirs(pick_nuclei_dir, exist_ok=True)
    score_nuclei_dir: str = os.path.join(
        project_files_dir, SCORED_NUCLEI_DIR_NAME
    )
    os.makedirs(score_nuclei_dir, exist_ok=True)
    results_path: str = os.path.join(project_files_dir, RESULTS_DIR)
    os.makedirs(results_path, exist_ok=True)
    return new_image_path


def get_file_name_from_path(file_path: str) -> tuple[str, str, str]:
    file_path_object: Path = Path(file_path)
    file_name: str = file_path_object.name
    file_name_no_ext: str = file_path_object.stem
    dir_path: str = os.path.dirname(file_path)
    return (file_name, file_name_no_ext, dir_path)
