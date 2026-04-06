import csv
import os
import shutil
from collections.abc import Callable
from configparser import ConfigParser
from configparser import Error as ConfigParserError
from contextlib import suppress
from pathlib import Path
from typing import cast

import numpy as np
import tifffile
from napari.layers import Image, Layer, Points, Shapes
from napari.utils.notifications import show_info
from napari.viewer import ViewerModel

from carltonlab_napari_count_tool._shared_variables import (
    DEFAULT_PROJECT_EXTENSION,
    DEFAULT_PROJECT_NAME,
    EDITED_REGIONS_EXPANSION_VALUES_FILE_NAME,
    EDITED_REGIONS_FILE_NAME,
    IMAGE_CONTRASTS_FILE_NAME,
    PICK_NUCLEI_DIR_NAME,
    POINTS_SUMMARY_FILE_NAME,
    REGIONS_DIR_NAME,
    RESULTS_DIR,
    SCORED_NUCLEI_DIR_NAME,
)
from carltonlab_napari_count_tool._shared_widgets import (
    confirm_dialog,
)


def close_all_non_set_image_layers(
    napari_viewer: ViewerModel, keeping_images: tuple[Image, ...]
) -> bool:
    closing_layers_list: list[Layer] = []
    for layer in napari_viewer.layers:
        if layer not in keeping_images:
            closing_layers_list.append(layer)
    if len(closing_layers_list) > 0:
        print("Asking to close layers")
        confirm_answer: bool = confirm_dialog(
            napari_viewer,
            "Any layer that is not a project image must be closed to proceed. Close all other layers?",
            no_mode=True,
        )
        if not confirm_answer:
            return False
    for layer in closing_layers_list:
        napari_viewer.layers.remove(layer)
    return True


def validate_closed_layers(napari_viewer: ViewerModel) -> bool:
    number_of_layers: int = len(napari_viewer.layers)
    if number_of_layers <= 0:
        return True
    confirm_answer: bool = confirm_dialog(
        napari_viewer,
        "All layers must be closed to open a new project image. Proceed?",
        no_mode=True,
    )
    if not confirm_answer:
        return False
    napari_viewer.layers.clear()
    return True


def open_project_image(
    napari_viewer: ViewerModel, image_path: str
) -> tuple[str, list[Image], str] | None:
    is_zarr_dir = os.path.isdir(image_path) and image_path.endswith(".zarr")
    image_dir: str = os.path.dirname(image_path)
    project_files_dir: str = os.path.join(image_dir, DEFAULT_PROJECT_NAME)
    if not os.path.exists(project_files_dir):
        confirm_answer: bool = confirm_dialog(
            napari_viewer,
            "The image is not part of a project. Create a new project?",
            no_mode=True,
        )
        if confirm_answer:
            try:
                new_image_path = create_project_dir_structure(image_path)
            except (FileNotFoundError, ValueError, FileExistsError) as exc:
                show_info(str(exc))
                return None
            image_path = new_image_path
            image_dir = os.path.dirname(image_path)
            project_files_dir = os.path.join(image_dir, DEFAULT_PROJECT_NAME)
        else:
            return None
    image_list: list[Image] = []
    if is_zarr_dir:
        opened_layers = napari_viewer.open(image_path)
        if not isinstance(opened_layers, list):
            opened_layers = [opened_layers]
        opened_images = [
            layer for layer in opened_layers if isinstance(layer, Image)
        ]
        if len(opened_images) == 0:
            show_info("No image layers were opened from the OME.zarr path")
            return None
        if len(opened_images) == 1:
            image_layer = opened_images[0]
            image_data = image_layer.data
            if hasattr(image_data, "ndim") and image_data.ndim >= 4:
                napari_viewer.layers.remove(image_layer)
                split_layers = napari_viewer.add_image(
                    image_data, channel_axis=1
                )
                if isinstance(split_layers, Image):
                    show_info(
                        "Only one image open when trying to split channels from OME.zarr"
                    )
                    return None
                image_list = cast(list[Image], split_layers)
            else:
                image_list = opened_images
        else:
            image_list = opened_images
    else:
        image_data = tifffile.imread(image_path)
        if len(image_data.shape) != 4:
            showing_string: str = (
                f"The image shape is: {image_data.shape}, expected 4 dimensions (ZCYX). ERROR"
            )
            show_info(showing_string)
            print(showing_string)
            return None
        image_opened: list[Image] | Image = open_image_as_layer(
            napari_viewer, image_path, split_channel_axis=1
        )
        if isinstance(image_opened, Image):
            showing_string: str = (
                "Only one image open when trying to open multiple channels. ERROR"
            )
            show_info(showing_string)
            print(showing_string)
            return None
        image_list = cast(list[Image], image_opened)
    contrast_validation: bool = verify_image_contrasts_file(image_path)
    if contrast_validation:
        contrasts: dict[int, tuple[float, float]] | None = (
            get_loaded_image_contrasts(project_files_dir)
        )
        if contrasts is not None:
            for image_index in range(len(image_list)):
                image_layer: Image = image_list[image_index]
                setting_contrast: tuple[float, float] = contrasts[image_index]
                image_layer.contrast_limits = _coerce_contrast_limits(
                    image_layer, setting_contrast
                )
    return (image_path, image_list, project_files_dir)


def _coerce_contrast_limits(
    image_layer: Image, contrast_tuple: tuple[float, float]
) -> tuple[float, float]:
    min_contrast, max_contrast = contrast_tuple
    if min_contrast > max_contrast:
        min_contrast, max_contrast = max_contrast, min_contrast
    dtype = np.asarray(image_layer.data).dtype
    if np.issubdtype(dtype, np.integer):
        dtype_info = np.iinfo(dtype)
        dtype_min = float(dtype_info.min)
        dtype_max = float(dtype_info.max)
    else:
        dtype_info = np.finfo(dtype)
        dtype_min = float(dtype_info.min)
        dtype_max = float(dtype_info.max)
    min_contrast = max(dtype_min, min_contrast)
    max_contrast = min(dtype_max, max_contrast)
    min_gap = 1.0
    if max_contrast - min_contrast < min_gap:
        if min_contrast <= dtype_min:
            max_contrast = min_contrast + min_gap
        elif max_contrast >= dtype_max:
            min_contrast = max_contrast - min_gap
        else:
            max_contrast = min_contrast + min_gap
    return (min_contrast, max_contrast)


def open_image_as_layer(
    napari_viewer: "ViewerModel",
    image_path: str,
    split_channel_axis: int | None = None,
) -> "Image | list[Image]":
    image_data = tifffile.imread(image_path)
    open_layers: Image | list[Image]
    image_path_path_object: Path = Path(image_path)
    image_file_no_ext: str = image_path_path_object.stem
    if split_channel_axis is not None:
        open_layers = napari_viewer.add_image(
            image_data, channel_axis=split_channel_axis
        )
        layers_list = cast(list[Image], open_layers)
        for layer_index, layer in enumerate(layers_list):
            channel_string: str = f" - c{layer_index + 1}"
            layer.name = image_file_no_ext + channel_string
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
        try:
            new_image_path: str = create_project_dir_structure(image_path)
        except (FileNotFoundError, ValueError, FileExistsError) as exc:
            show_info(str(exc))
            return False
        return new_image_path
    return False


def _strip_ome_zarr_suffix(name: str) -> str:
    if name.endswith(".ome.zarr"):
        return name[: -len(".ome.zarr")]
    return Path(name).stem


def _get_tile_positions_csv_path(image_path: str) -> Path:
    image_path_obj = Path(image_path)
    return image_path_obj.parent / (
        f"{_strip_ome_zarr_suffix(image_path_obj.name)}_tile_positions.csv"
    )


def _get_tiles_directory_path(image_path: str) -> Path:
    image_path_obj = Path(image_path)
    return image_path_obj.parent / (
        f"{_strip_ome_zarr_suffix(image_path_obj.name)}_tiles"
    )


def _read_tile_positions_rows(csv_path: Path) -> list[dict[str, str]]:
    with csv_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = [dict(row) for row in reader]
    return rows


def _get_project_tile_sources(image_path: str) -> tuple[Path, Path] | None:
    image_path_obj = Path(image_path)
    if not image_path_obj.name.endswith(".ome.zarr"):
        return None

    csv_path = _get_tile_positions_csv_path(image_path)
    if not csv_path.exists():
        return None

    rows = _read_tile_positions_rows(csv_path)
    if len(rows) == 0:
        raise ValueError(f"Tile positions CSV is empty: {csv_path}")

    image_dir = image_path_obj.parent.resolve()
    tiles_dir = _get_tiles_directory_path(image_path).resolve()
    if not tiles_dir.exists():
        raise FileNotFoundError(
            f"Tiles directory for stitched image was not found: {tiles_dir}"
        )
    if not tiles_dir.is_dir():
        raise ValueError(f"Tiles path is not a directory: {tiles_dir}")

    tile_paths: list[Path] = []
    for row in rows:
        tile_path_value = (row.get("tile_path") or "").strip()
        tile_name_value = (row.get("tile_name") or "").strip()
        if tile_name_value != "":
            tile_path = tiles_dir / tile_name_value
        elif tile_path_value != "":
            tile_path = Path(tile_path_value)
        else:
            raise ValueError(
                f"Tile positions CSV row is missing tile_path/tile_name: {csv_path}"
            )

        if not tile_path.is_absolute():
            tile_path = image_dir / tile_path

        tile_path = tile_path.resolve()
        if not tile_path.exists():
            raise FileNotFoundError(
                f"Tile OME-Zarr directory listed in CSV was not found: {tile_path}"
            )
        if not tile_path.is_dir() or not tile_path.name.endswith(".ome.zarr"):
            raise ValueError(
                f"Tile path from CSV is not an OME-Zarr directory: {tile_path}"
            )
        tile_paths.append(tile_path)

    if len(set(tile_paths)) != len(tile_paths):
        raise ValueError(
            f"Tile positions CSV contains duplicate tile paths: {csv_path}"
        )
    for tile_path in tile_paths:
        if tile_path.parent != tiles_dir:
            raise ValueError(
                "Tile positions CSV must point to tiles inside the stitched "
                f"tiles directory. Offending tile: {tile_path}"
            )
    return csv_path, tiles_dir


def _move_path_into_directory(
    source_path: Path, destination_dir: Path
) -> Path:
    destination_path = destination_dir / source_path.name
    if destination_path.exists():
        raise FileExistsError(
            f"Destination already exists while creating project: {destination_path}"
        )
    shutil.move(str(source_path), str(destination_path))
    return destination_path


def _rewrite_tile_positions_csv(
    csv_path: Path, tile_paths: list[Path]
) -> None:
    rows = _read_tile_positions_rows(csv_path)
    if len(rows) != len(tile_paths):
        raise ValueError(
            "Tile positions CSV row count changed during project creation."
        )

    fieldnames = list(rows[0].keys())
    for row, tile_path in zip(rows, tile_paths, strict=True):
        if "tile_path" in row:
            row["tile_path"] = str(tile_path)
        if "tile_name" in row:
            row["tile_name"] = tile_path.name

    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _create_project_files_dirs(project_files_dir: Path) -> None:
    os.makedirs(project_files_dir, exist_ok=True)
    os.makedirs(project_files_dir / REGIONS_DIR_NAME, exist_ok=True)
    os.makedirs(project_files_dir / PICK_NUCLEI_DIR_NAME, exist_ok=True)
    os.makedirs(project_files_dir / SCORED_NUCLEI_DIR_NAME, exist_ok=True)
    os.makedirs(project_files_dir / RESULTS_DIR, exist_ok=True)


def create_project_dir_structure(image_path: str) -> str:
    parent_dir_path: str = os.path.dirname(image_path)
    image_file_path_object: Path = Path(image_path)
    image_file_name_no_ext: str = image_file_path_object.stem
    if "".join(image_file_path_object.suffixes).endswith(".ome.zarr"):
        image_file_name_no_ext = image_file_path_object.name[
            : -len(".ome.zarr")
        ]
    new_project_path: str = os.path.join(
        parent_dir_path, image_file_name_no_ext + DEFAULT_PROJECT_EXTENSION
    )
    os.makedirs(new_project_path, exist_ok=True)
    new_project_path_obj = Path(new_project_path)

    tile_sources = _get_project_tile_sources(image_path)
    new_image_path = _move_path_into_directory(
        image_file_path_object, new_project_path_obj
    )

    if tile_sources is not None:
        csv_path, tiles_dir = tile_sources
        new_csv_path = _move_path_into_directory(
            csv_path, new_project_path_obj
        )
        moved_tiles_dir = _move_path_into_directory(
            tiles_dir, new_project_path_obj
        )
        moved_tile_paths = sorted(moved_tiles_dir.glob("*.ome.zarr"))
        _rewrite_tile_positions_csv(new_csv_path, moved_tile_paths)

    project_files_dir = new_project_path_obj / DEFAULT_PROJECT_NAME
    _create_project_files_dirs(project_files_dir)
    return str(new_image_path)


def get_file_name_from_path(file_path: str) -> tuple[str, str, str]:
    file_path_object: Path = Path(file_path)
    file_name: str = file_path_object.name
    file_name_no_ext: str = file_path_object.stem
    dir_path: str = os.path.dirname(file_path)
    return (file_name, file_name_no_ext, dir_path)


def get_project_files_dir_from_image_path(image_path: str) -> str:
    image_dir: str = os.path.dirname(image_path)
    project_files_dir: str = os.path.join(image_dir, DEFAULT_PROJECT_NAME)
    return project_files_dir


def verify_image_contrasts_file(image_path: str | None) -> bool:
    if image_path is None:
        return False
    image_dir: str = os.path.dirname(image_path)
    saving_contrasts_file_path: str = os.path.join(
        image_dir, DEFAULT_PROJECT_NAME, IMAGE_CONTRASTS_FILE_NAME
    )
    return os.path.exists(saving_contrasts_file_path)


def get_loaded_image_contrasts(
    project_dir: str,
) -> dict[int, tuple[float, float]] | None:
    if not os.path.exists(project_dir):
        print(f"The project directory {project_dir} doesn't exist")
        return
    contrasts_file_path: str = os.path.join(
        project_dir, IMAGE_CONTRASTS_FILE_NAME
    )
    if not os.path.exists(contrasts_file_path):
        print(
            f"The contrast file with path: {contrasts_file_path} doesn't exist"
        )
        return
    config_parser: ConfigParser = ConfigParser()
    config_parser.read(contrasts_file_path)
    number_of_channels: int = int(
        config_parser["ImageContrasts"]["NumberOfChannels"]
    )
    returning_dict: dict[int, tuple[float, float]] = {}
    for channel_index in range(number_of_channels):
        channel_name: str = "channel-" + str(channel_index + 1)
        values_str: str = config_parser["ImageContrasts"][channel_name]
        values_strings: list[str] = values_str.split(",")
        values: tuple[float, float] = (
            float(values_strings[0]),
            float(values_strings[1]),
        )
        returning_dict[channel_index] = values
    return returning_dict


def verify_edited_regions_file(image_path: str | None) -> bool:
    if image_path is None:
        return False
    image_dir: str = os.path.dirname(image_path)
    saving_extended_regions_file_path: str = os.path.join(
        image_dir,
        DEFAULT_PROJECT_NAME,
        REGIONS_DIR_NAME,
        EDITED_REGIONS_FILE_NAME,
    )
    return os.path.exists(saving_extended_regions_file_path)


def get_number_of_saved_regions(project_directory: str) -> int:
    editable_regions_config_path: str = os.path.join(
        project_directory,
        REGIONS_DIR_NAME,
        EDITED_REGIONS_EXPANSION_VALUES_FILE_NAME,
    )
    if not os.path.exists(editable_regions_config_path):
        return 0
    edited_regions_parser: ConfigParser = ConfigParser()
    try:
        edited_regions_parser.read(editable_regions_config_path)
    except ConfigParserError:
        show_info("Couldn't load the edited regions config file")
        return 0
    number_of_regions: int = len(edited_regions_parser["ExpandedRegions"])
    return number_of_regions


def str_to_bool(value: str) -> bool:
    return value.lower() in {"true", "1"}


def load_points_summary_file(summary_file_path) -> ConfigParser | None:
    loaded_parser: ConfigParser | None = ConfigParser()
    try:
        read_file = loaded_parser.read(summary_file_path)
        if not read_file:
            loaded_parser = None
    except ConfigParserError:
        show_info("Couldn't load the points summary file")
        loaded_parser = None
        return loaded_parser
    return loaded_parser


def create_summary_file(
    pick_nuclei_directory: str, number_of_regions
) -> ConfigParser:
    config_file_path: str = os.path.join(
        pick_nuclei_directory, POINTS_SUMMARY_FILE_NAME
    )
    summary_file_parser: ConfigParser = ConfigParser()
    summary_file_parser.add_section("NucleiCount")
    summary_file_parser.add_section("SavedPointsState")
    summary_file_parser.add_section("SavedSquaresState")
    summary_file_parser.add_section("SavedSbsState")
    for region_index in range(number_of_regions):
        region_string: str = "region-" + str(region_index + 1)
        summary_file_parser["NucleiCount"][region_string] = "0"
        print(
            f"Set the nuclei count of {region_string} to {summary_file_parser['NucleiCount'][region_string]}"
        )
        summary_file_parser["SavedPointsState"][region_string] = "False"
        print(f"Set the points state of {region_string} to False")
        summary_file_parser["SavedSquaresState"][region_string] = "False"
        print(f"Set the squares state of {region_string} to False")
        summary_file_parser["SavedSbsState"][region_string] = "False"
        print(f"Set the sbs state of {region_string} to False")
    with open(config_file_path, "w") as config_file:
        summary_file_parser.write(config_file)
    return summary_file_parser


def get_points_saved_list(
    pick_nuclei_directory, number_of_regions: int
) -> list[tuple[int, bool, bool, bool] | None]:
    points_saved_list: list[None | tuple[int, bool, bool, bool]] = []
    project_directory: str = os.path.dirname(pick_nuclei_directory)
    number_of_saved_regions: int = get_number_of_saved_regions(
        project_directory
    )
    for _ in range(number_of_saved_regions):
        points_saved_list.append(None)
    points_summary_file_path: str = os.path.join(
        pick_nuclei_directory, POINTS_SUMMARY_FILE_NAME
    )
    summary_parser = load_points_summary_file(points_summary_file_path)
    if summary_parser is None:
        summary_parser = create_summary_file(
            pick_nuclei_directory, number_of_regions
        )
    if len(summary_parser["NucleiCount"]) <= 0:
        return points_saved_list
    for region_index in range(len(summary_parser["NucleiCount"])):
        region_str: str = "region-" + str(region_index + 1)
        number_of_points: int = int(summary_parser["NucleiCount"][region_str])
        saved_points_state: bool = str_to_bool(
            summary_parser["SavedPointsState"][region_str]
        )
        saved_squares_state: bool = str_to_bool(
            summary_parser["SavedSquaresState"][region_str]
        )
        saved_sbs_state: bool = str_to_bool(
            summary_parser["SavedSbsState"][region_str]
        )
        setting_tuple: tuple[int, bool, bool, bool] = (
            number_of_points,
            saved_points_state,
            saved_squares_state,
            saved_sbs_state,
        )
        points_saved_list[region_index] = setting_tuple
    return points_saved_list


def verify_all_sbs_created(image_path: str | None) -> bool:
    if image_path is None:
        return False
    project_files_dir: str = get_project_files_dir_from_image_path(image_path)
    number_of_regions: int = get_number_of_saved_regions(project_files_dir)
    if number_of_regions <= 0:
        return False
    pick_nuclei_directory: str = os.path.join(
        project_files_dir, PICK_NUCLEI_DIR_NAME
    )
    if not os.path.exists(pick_nuclei_directory):
        create_summary_file(pick_nuclei_directory, number_of_regions)
    points_saved_list = get_points_saved_list(
        pick_nuclei_directory, number_of_regions
    )
    if points_saved_list is None:
        return False
    if len(points_saved_list) <= 0:
        return False
    for sbs_element in points_saved_list:
        if sbs_element is None:
            print("")
            print("This if false false")
            print(f"The points saved list is: {points_saved_list}")
            return False
    if any(sbs_element is None for sbs_element in points_saved_list):
        return False
    saved_sbs_list: list[bool] = [
        sbs_element[3] for sbs_element in points_saved_list
    ]
    return all(saved_sbs_list)
