import csv
import os
from configparser import ConfigParser
from pathlib import Path

import numpy as np
import tifffile
from napari.layers import Image
from napari.viewer import ViewerModel
from qtpy.QtWidgets import QWidget

from carltonlab_napari_count_tool._model import (
    get_file_name_from_path,
    get_loaded_image_contrasts,
    get_loaded_image_contrasts_from_file_path,
    get_tile_contrasts_file_path,
    is_tile_image_path,
    verify_project_directory_from_image_path,
)
from carltonlab_napari_count_tool._shared_variables import (
    DEFAULT_PROJECT_NAME,
    IMAGE_CONTRASTS_FILE_NAME,
)
from carltonlab_napari_count_tool._shared_widgets import (
    confirm_dialog,
    get_file,
)


def set_layer_contrast_limits(
    image_layer: Image, min_contrast: float, max_contrast: float
):
    min_gap = 1.0
    dtype = np.asarray(image_layer.data).dtype
    if np.issubdtype(dtype, np.integer):
        dtype_info = np.iinfo(dtype)
        dtype_min = float(dtype_info.min)
        dtype_max = float(dtype_info.max)
    else:
        dtype_info = np.finfo(dtype)
        dtype_min = float(dtype_info.min)
        dtype_max = float(dtype_info.max)
    if min_contrast > max_contrast:
        min_contrast, max_contrast = max_contrast, min_contrast
    min_contrast = max(dtype_min, min_contrast)
    max_contrast = min(dtype_max, max_contrast)
    if max_contrast - min_contrast < min_gap:
        if min_contrast <= 0:
            max_contrast = min_contrast + min_gap
        elif max_contrast >= dtype_max:
            min_contrast = max_contrast - min_gap
        else:
            max_contrast = min_contrast + min_gap
    image_layer.contrast_limits = (min_contrast, max_contrast)
    image_layer.refresh()


def open_image_contrasts(
    napari_viewer: ViewerModel, parent_widget: QWidget
) -> tuple[list[Image], str] | None:
    open_image_path: str | None = get_file(
        parent_widget, "Select image to get contrasts"
    )
    if open_image_path is None:
        return None
    new_image_path: bool | str = verify_project_directory_from_image_path(
        open_image_path, create_project_if_not_exist=True
    )
    if isinstance(new_image_path, str):
        open_image_path = new_image_path
    image_data = tifffile.imread(open_image_path)
    if len(image_data.shape) < 4:
        raise ValueError(
            f"The image shape is: {image_data.shape}, expected at least 4 dimensions"
            f"The cannel axis must be index 1"
        )
    image_layers: list[Image] | Image = napari_viewer.add_image(
        image_data, channel_axis=1
    )
    file_name_tuple: tuple[str, str, str] = get_file_name_from_path(
        open_image_path
    )
    if isinstance(image_layers, Image):
        raise ValueError(
            f"Expected 2 channels along axis=1, but add_image returned a single layer"
            f"The image shape is: {image_data.shape}"
        )
    for image_index, image_layer in enumerate(image_layers):
        channel_string: str = f"c{image_index + 1}"
        image_layer.name = file_name_tuple[1] + " - " + channel_string
    return (image_layers, open_image_path)


def save_contrasts(
    napari_viewer: ViewerModel,
    saving_dict: dict[int, tuple[float, float]],
    image_path: str,
) -> None:
    main_dir: str = os.path.dirname(image_path)
    saving_contrasts_file_path: str = os.path.join(
        main_dir, DEFAULT_PROJECT_NAME, IMAGE_CONTRASTS_FILE_NAME
    )
    if os.path.exists(saving_contrasts_file_path):
        confirm_answer = confirm_dialog(
            napari_viewer, "Contrast already set, replace?"
        )
        if not confirm_answer:
            return
    config_parser: ConfigParser = ConfigParser()
    config_parser.add_section("ImageContrasts")
    config_parser["ImageContrasts"]["NumberOfChannels"] = str(len(saving_dict))
    for contrast_index in range(len(saving_dict.keys())):
        contrast_string: str = "channel-" + str(contrast_index + 1)
        contrast_values: tuple[float, float] = saving_dict[contrast_index]
        config_parser["ImageContrasts"][contrast_string] = (
            str(contrast_values[0]) + "," + str(contrast_values[1])
        )
    with open(saving_contrasts_file_path, "w") as config_file:
        config_parser.write(config_file)


def save_tile_contrasts(
    saving_dict: dict[int, tuple[float, float]], tile_image_path: str
) -> None:
    tile_path = Path(tile_image_path)
    tile_name = tile_path.name
    if tile_name.endswith(".ome.zarr"):
        tile_stem = tile_name[: -len(".ome.zarr")]
    else:
        tile_stem = tile_path.stem
    saving_contrasts_file_path = (
        tile_path.parent / f"{tile_stem}_contrasts.config"
    )
    config_parser: ConfigParser = ConfigParser()
    config_parser.add_section("ImageContrasts")
    config_parser["ImageContrasts"]["NumberOfChannels"] = str(len(saving_dict))
    for contrast_index in range(len(saving_dict.keys())):
        contrast_string: str = "channel-" + str(contrast_index + 1)
        contrast_values: tuple[float, float] = saving_dict[contrast_index]
        config_parser["ImageContrasts"][contrast_string] = (
            str(contrast_values[0]) + "," + str(contrast_values[1])
        )
    with saving_contrasts_file_path.open("w") as config_file:
        config_parser.write(config_file)


def get_tile_pixel_positions(
    stitched_image_path: str, tile_index: int
) -> dict[str, int] | None:
    stitched_path = Path(stitched_image_path)
    stitched_name = stitched_path.name
    if stitched_name.endswith(".ome.zarr"):
        stitched_stem = stitched_name[: -len(".ome.zarr")]
    else:
        stitched_stem = stitched_path.stem
    tile_positions_path = (
        stitched_path.parent / f"{stitched_stem}_tile_positions.csv"
    )
    if not tile_positions_path.exists():
        return None
    with tile_positions_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = [dict(row) for row in reader]
    if tile_index < 0 or tile_index >= len(rows):
        return None
    row = rows[tile_index]
    pixel_positions: dict[str, int] = {}
    for dim in ("z", "y", "x"):
        min_key = f"{dim}_min_px_index"
        max_key = f"{dim}_max_px_index_exclusive"
        min_value = (row.get(min_key) or "").strip()
        max_value = (row.get(max_key) or "").strip()
        if min_value != "":
            pixel_positions[min_key] = int(min_value)
        if max_value != "":
            pixel_positions[max_key] = int(max_value)
    return pixel_positions


def set_tile_images_xy_translate(
    image_layers: tuple[Image, ...] | list[Image],
    tile_pixel_positions: dict[str, int] | None,
) -> None:
    if tile_pixel_positions is None:
        return
    y_translate = float(tile_pixel_positions.get("y_min_px_index", 0))
    x_translate = float(tile_pixel_positions.get("x_min_px_index", 0))
    for image_layer in image_layers:
        translate = [0.0] * image_layer.ndim
        if image_layer.ndim >= 2:
            translate[-2] = y_translate
            translate[-1] = x_translate
        image_layer.translate = tuple(translate)


def get_image_contrasts_from_file(
    image_path: str, images: tuple[Image, ...]
) -> dict[int, tuple[float, float]] | None:
    if is_tile_image_path(image_path):
        tile_contrasts_file_path = get_tile_contrasts_file_path(image_path)
        returning_dict = get_loaded_image_contrasts_from_file_path(
            tile_contrasts_file_path
        )
    else:
        image_dir: str = os.path.dirname(image_path)
        project_file_dir: str = os.path.join(image_dir, DEFAULT_PROJECT_NAME)
        returning_dict = get_loaded_image_contrasts(project_file_dir)
    if returning_dict is None:
        return returning_dict
    for layer_index, contrast_tuple in returning_dict.items():
        image_layer: Image = images[layer_index]
        set_layer_contrast_limits(
            image_layer, contrast_tuple[0], contrast_tuple[1]
        )
    return returning_dict
