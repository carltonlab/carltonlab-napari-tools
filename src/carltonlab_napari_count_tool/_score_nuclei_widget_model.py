import csv
import glob
import os
from configparser import ConfigParser
from pathlib import Path
from typing import Literal, cast

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import tifffile
from napari.layers import Image, Layer, Points
from napari.utils.notifications import show_error, show_info
from napari.viewer import ViewerModel
from qtpy.QtWidgets import QWidget

from carltonlab_napari_count_tool._model import (
    get_loaded_image_contrasts_from_file_path,
    get_tile_contrasts_file_path,
)
from carltonlab_napari_count_tool._regions_widget_model import SPLINE_FILE_NAME
from carltonlab_napari_count_tool._set_contrast_widget_model import (
    get_loaded_image_contrasts,
    set_layer_contrast_limits,
)
from carltonlab_napari_count_tool._shared_variables import (
    CUT_SBS_DIR_NAME,
    DEFAULT_PROJECT_NAME,
    MULTI_GONAD_FILE_EXTENSION,
    PICK_NUCLEI_DIR_NAME,
    POINTS_SUMMARY_FILE_NAME,
    REGIONS_DIR_NAME,
    SBS_FILE_NAME_EXTENSION,
    SBS_METADATA_FILE_NAME,
    SCORED_NUCLEI_DIR_NAME,
    SCORED_NUCLEI_PLOT_FILE_NAME,
    SCORED_NUCLEI_POINTS_FILE_NAME_EXTENSION,
    SCORED_NUCLEI_SUMMARY_FILE_NAME,
)
from carltonlab_napari_count_tool._shared_widgets import (
    confirm_dialog,
    get_directory,
    get_file,
)


class CLSPSbsObject:
    def __init__(
        self,
        napari_viewer: "ViewerModel",
        name: str,
        region_name: str,
        scored_nuclei_dir: str,
        sbs_file_path: str,
        gonad_file_name: str,
        crop_box_yx: tuple[int, int, int, int] | None = None,
        setting_contrast: dict[int, tuple[float, float]] | None = None,
        overlapping_tiles: list[int] | None = None,
        contrast_source: str = "stitched",
    ):
        self._napari_viewer = napari_viewer
        self._name: str = name
        self._region_name: str = region_name
        self._scored_nuclei_dir: str = scored_nuclei_dir
        self._points_layer_file_name: str = (
            region_name + "_" + name + SCORED_NUCLEI_POINTS_FILE_NAME_EXTENSION
        )
        self._zero_points_file_name: str = (
            region_name + "_" + name + "_zero_points.txt"
        )
        self._image_file_path: str = sbs_file_path
        self._gonad_file_name: str = gonad_file_name
        self._crop_box_yx: tuple[int, int, int, int] | None = crop_box_yx
        self._setting_contrast: dict[int, tuple[float, float]] | None = (
            setting_contrast
        )
        self._overlapping_tiles: list[int] = (
            [] if overlapping_tiles is None else overlapping_tiles
        )
        self._contrast_source: str = contrast_source
        self._number_of_points: int
        self._saved_state: bool

    def saved_state(self) -> bool:
        return self._saved_state

    def get_image_path(self) -> str:
        return self._image_file_path

    def get_display_name(self) -> str:
        return (
            self._gonad_file_name
            + " - "
            + self._region_name
            + " - "
            + self._name
        )

    def get_crop_box_yx(self) -> tuple[int, int, int, int] | None:
        return self._crop_box_yx

    @property
    def overlapping_tiles(self) -> list[int]:
        return self._overlapping_tiles

    @overlapping_tiles.setter
    def overlapping_tiles(self, value: list[int]) -> None:
        self._overlapping_tiles = value

    @property
    def contrast_source(self) -> str:
        return self._contrast_source

    @contrast_source.setter
    def contrast_source(self, value: str) -> None:
        self._contrast_source = value

    @property
    def setting_contrast(self) -> dict[int, tuple[float, float]] | None:
        return self._setting_contrast

    @setting_contrast.setter
    def setting_contrast(
        self, value: dict[int, tuple[float, float]] | None
    ) -> None:
        self._setting_contrast = value

    def load_number_of_points(self) -> int | None:
        points_file_path: str = os.path.join(
            self._scored_nuclei_dir, self._points_layer_file_name
        )
        if os.path.exists(points_file_path):
            pandas_df = pd.read_csv(points_file_path)
            number_of_points: int = len(pandas_df)
            self._number_of_points = number_of_points
            self._saved_state: bool = True
            return number_of_points
        elif os.path.exists(
            os.path.join(self._scored_nuclei_dir, self._zero_points_file_name)
        ):
            self._saved_state: bool = True
            self._number_of_points = 0
            return 0
        else:
            self._saved_state: bool = False
            self._number_of_points = 0

    def get_number_of_points(self) -> int:
        return self._number_of_points

    def get_points_file_path(self) -> str | None:
        points_file_path: str = os.path.join(
            self._scored_nuclei_dir, self._points_layer_file_name
        )
        if os.path.exists(points_file_path):
            return points_file_path
        return None

    def get_scored_nuclei_dir(self) -> str:
        return self._scored_nuclei_dir

    def get_gonad_dir(self) -> str:
        project_dir = os.path.dirname(self._scored_nuclei_dir)
        return os.path.dirname(project_dir)

    def save_zeros_file(self) -> None:
        points_file_path: str = os.path.join(
            self._scored_nuclei_dir, self._points_layer_file_name
        )
        if os.path.exists(points_file_path):
            os.remove(points_file_path)
        zeros_file_path: str = os.path.join(
            self._scored_nuclei_dir, self._zero_points_file_name
        )
        with open(zeros_file_path, "w") as _:
            pass

    def save_points_layer(self, saving_layer: Points) -> None:
        zeros_file_path: str = os.path.join(
            self._scored_nuclei_dir, self._zero_points_file_name
        )
        if os.path.exists(zeros_file_path):
            os.remove(zeros_file_path)
        points_file_path: str = os.path.join(
            self._scored_nuclei_dir, self._points_layer_file_name
        )
        saving_layer.save(points_file_path)


OpenFileReturns = Literal["failed"] | None | tuple[list[CLSPSbsObject], str]


def open_image_layer_from_clsp_object(
    napari_viewer: ViewerModel, clsp_object: CLSPSbsObject, blind: bool = False
) -> tuple[Image, Image]:
    image_path: str = clsp_object.get_image_path()
    layers_contrasts = clsp_object.setting_contrast
    print(f"The layers contrasts are: {layers_contrasts}")
    print(f"The image path is: {image_path}")
    image_data = tifffile.imread(image_path)
    images_layers: Image | list[Image] = napari_viewer.add_image(
        image_data, channel_axis=1
    )
    print(f"The image data is : {image_data.shape}")
    if isinstance(images_layers, Image):
        raise ValueError(
            f"Expected 2 channels along axis=1, but add_image returned a single layer"
            f"image_data.shape={image_data.shape}"
        )
    image_layers = cast(list[Image], images_layers)
    first_layer = image_layers[0]
    second_layer = image_layers[1]
    if layers_contrasts is not None:
        set_layer_contrast_limits(
            first_layer, layers_contrasts[0][0], layers_contrasts[0][1]
        )
        set_layer_contrast_limits(
            second_layer, layers_contrasts[1][0], layers_contrasts[1][1]
        )
        print(
            f"Contrasts set to {layers_contrasts[0]} and {layers_contrasts[1]}"
        )
    if blind:
        first_layer.name = "blind_dapi"
        second_layer.name = "blind_rad51"
    return (first_layer, second_layer)


def _load_layers_contrasts(
    project_path: str,
) -> dict[int, tuple[float, float]] | None:
    contrast_file_path: str = os.path.join(project_path, DEFAULT_PROJECT_NAME)
    print(f"The project path is: {contrast_file_path}")
    if not os.path.exists(contrast_file_path):
        print("Doesnt exist")
        return None
    loaded_contrasts: dict[int, tuple[float, float]] | None = (
        get_loaded_image_contrasts(contrast_file_path)
    )
    print(f"The loaded contrasts are: {loaded_contrasts}")
    return loaded_contrasts


def open_points_layer_from_clsp_object(
    napari_viewer: ViewerModel,
    clsp_object: CLSPSbsObject,
    points_size: int = 5,
    layer_dims: int | None = None,
):
    points_file_name: str | None = clsp_object.get_points_file_path()
    if points_file_name is None:
        ndim = layer_dims if layer_dims is not None else 2
        returning_points = napari_viewer.add_points(
            name="old_points", ndim=ndim
        )
        returning_points.size = points_size
        returning_points.current_size = points_size
        returning_points.refresh()
        return returning_points
    points_layers: list[Layer] = napari_viewer.open(points_file_name)
    first_point_layer: Points = cast(Points, points_layers[0])
    first_point_layer.name = "old_points"
    first_point_layer.size = points_size
    first_point_layer.current_size = points_size
    first_point_layer.refresh()
    return first_point_layer


def save_points_layer_from_clsp_object(
    saving_layer: Points,
    clsp_object: CLSPSbsObject,
):
    number_of_points: int = len(saving_layer.data)
    if number_of_points == 0:
        clsp_object.save_zeros_file()
    else:
        clsp_object.save_points_layer(saving_layer)


def _axis_columns_from_dataframe(df: pd.DataFrame) -> list[str]:
    axis_cols = [col for col in df.columns if col.startswith("axis-")]
    if not axis_cols:
        return []
    axis_cols.sort(key=lambda col: int(col.split("-")[-1]))
    return axis_cols


def _load_spline_polyline(spline_csv_path: str) -> np.ndarray | None:
    if not os.path.exists(spline_csv_path):
        return None
    df = pd.read_csv(spline_csv_path)
    axis_cols = _axis_columns_from_dataframe(df)
    if len(axis_cols) < 2:
        return None
    axis_cols = axis_cols[-2:]
    shape_df = df
    if "shape_type" in df.columns:
        shape_df = df[df["shape_type"] == "path"]
        if shape_df.empty:
            shape_df = df
    if "index" in shape_df.columns:
        min_index = shape_df["index"].min()
        shape_df = shape_df[shape_df["index"] == min_index]
    if "vertex_index" in shape_df.columns:  # type: ignore
        shape_df = shape_df.sort_values("vertex_index")  # type: ignore
    spline_points = shape_df[axis_cols].to_numpy()  # type: ignore
    if spline_points.ndim != 2 or spline_points.shape[0] < 2:
        return None
    return spline_points


def _project_point_to_polyline(
    point_yx: np.ndarray, polyline_yx: np.ndarray
) -> tuple[np.ndarray, float]:
    segments = polyline_yx[1:] - polyline_yx[:-1]
    seg_len2 = (segments**2).sum(axis=1)
    seg_len = np.sqrt(seg_len2)
    cumlen = np.concatenate(([0.0], np.cumsum(seg_len)))
    total_len = cumlen[-1]

    best_dist2 = None
    best_proj = None
    best_arc = 0.0
    for i, (p0, seg, seg_l2) in enumerate(
        zip(polyline_yx[:-1], segments, seg_len2, strict=True)
    ):
        if seg_l2 == 0:
            continue
        t = float(np.dot(point_yx - p0, seg) / seg_l2)
        t = min(1.0, max(0.0, t))
        proj = p0 + t * seg
        dist2 = float(np.dot(point_yx - proj, point_yx - proj))
        if best_dist2 is None or dist2 < best_dist2:
            best_dist2 = dist2
            best_proj = proj
            best_arc = float(cumlen[i] + t * seg_len[i])

    if best_proj is None:
        best_proj = polyline_yx[0]
        best_arc = 0.0
    norm_arc = 0.0 if total_len == 0 else best_arc / total_len
    return best_proj, norm_arc


def generate_scored_points_spline_summary(
    gonad_dir: str, output_csv_path: str | None = None
) -> str | None:
    project_dir = os.path.join(gonad_dir, DEFAULT_PROJECT_NAME)
    scored_nuclei_dir = os.path.join(project_dir, SCORED_NUCLEI_DIR_NAME)
    spline_csv_path = os.path.join(
        project_dir, REGIONS_DIR_NAME, SPLINE_FILE_NAME
    )
    metadata_csv_path = os.path.join(
        project_dir,
        PICK_NUCLEI_DIR_NAME,
        CUT_SBS_DIR_NAME,
        SBS_METADATA_FILE_NAME,
    )

    if not os.path.exists(scored_nuclei_dir):
        return None
    if not os.path.exists(metadata_csv_path):
        return None

    spline_points = _load_spline_polyline(spline_csv_path)
    if spline_points is None:
        return None

    metadata_df = pd.read_csv(metadata_csv_path)
    if "sbs_image_name" not in metadata_df.columns:
        return None
    metadata_map = {}
    for _, row in metadata_df.iterrows():
        y1 = int(cast(float, row["y1"]))
        x1 = int(cast(float, row["x1"]))
        metadata_map[row["sbs_image_name"]] = {
            "y1": y1,
            "x1": x1,
        }

    points_files = glob.glob(
        os.path.join(
            scored_nuclei_dir, f"*{SCORED_NUCLEI_POINTS_FILE_NAME_EXTENSION}"
        )
    )
    if not points_files:
        return None

    rows = []
    for points_file_path in points_files:
        points_df = pd.read_csv(points_file_path)
        axis_cols = _axis_columns_from_dataframe(points_df)
        if len(axis_cols) < 2:
            continue
        axis_cols = axis_cols[-2:]
        points_name = os.path.basename(points_file_path)
        sbs_image_name = points_name.replace(
            SCORED_NUCLEI_POINTS_FILE_NAME_EXTENSION, SBS_FILE_NAME_EXTENSION
        )
        if sbs_image_name not in metadata_map:
            continue
        offset = metadata_map[sbs_image_name]
        for idx, row in points_df.iterrows():
            point_index = int(cast(float, idx))
            point_yx = np.array(
                [row[axis_cols[0]], row[axis_cols[1]]], dtype=np.float64
            )
            y_pos = float(offset["y1"] + point_yx[0])
            x_pos = float(offset["x1"] + point_yx[1])
            proj_yx, norm_arc = _project_point_to_polyline(
                np.array([y_pos, x_pos], dtype=np.float64), spline_points
            )
            rows.append(
                {
                    "sbs_image_name": sbs_image_name,
                    "point_number": point_index + 1,
                    "x_position": x_pos,
                    "y_position": y_pos,
                    "x_y_coord_intersection_to_spline": f"{proj_yx[1]},{proj_yx[0]}",
                    "normalized_arc-length_to_spline": norm_arc,
                }
            )

    if not rows:
        return None
    if output_csv_path is None:
        output_csv_path = os.path.join(
            scored_nuclei_dir, SCORED_NUCLEI_SUMMARY_FILE_NAME
        )
    output_df = pd.DataFrame(
        rows,
        columns=[
            "sbs_image_name",
            "point_number",
            "x_position",
            "y_position",
            "x_y_coord_intersection_to_spline",
            "normalized_arc-length_to_spline",
        ],
    )
    output_df.to_csv(output_csv_path, index=False)
    return output_csv_path


def generate_scored_points_spline_plot(
    gonad_dir: str, summary_csv_path: str | None = None
) -> str | None:
    project_dir = os.path.join(gonad_dir, DEFAULT_PROJECT_NAME)
    scored_nuclei_dir = os.path.join(project_dir, SCORED_NUCLEI_DIR_NAME)
    if summary_csv_path is None:
        summary_csv_path = os.path.join(
            scored_nuclei_dir, SCORED_NUCLEI_SUMMARY_FILE_NAME
        )
    if not os.path.exists(summary_csv_path):
        summary_csv_path = generate_scored_points_spline_summary(gonad_dir)
        if summary_csv_path is None:
            return None
    summary_df = pd.read_csv(summary_csv_path)
    if "normalized_arc-length_to_spline" not in summary_df.columns:
        return None
    positions = (
        summary_df["normalized_arc-length_to_spline"]
        .dropna()
        .to_numpy(dtype=np.float64)
    )
    if positions.size == 0:
        return None
    positions = np.sort(positions)
    cumulative_counts = np.cumsum(np.ones_like(positions, dtype=np.int64))

    fig, ax = plt.subplots(figsize=(6, 4))
    ax.plot(
        positions, cumulative_counts, marker="o", markersize=3, linewidth=1
    )
    ax.set_xlabel("Relative spline position")
    ax.set_ylabel("Cumulative points")
    ax.set_xlim(0, 1)
    ax.grid(True, alpha=0.3)

    output_path = os.path.join(scored_nuclei_dir, SCORED_NUCLEI_PLOT_FILE_NAME)
    fig.tight_layout()
    fig.savefig(output_path, format="pdf")
    plt.close(fig)
    return output_path


def open_scoring_file(
    napari_viewer: "ViewerModel", parent_widget: QWidget
) -> OpenFileReturns:
    return _open_scoring_path(
        napari_viewer,
        parent_widget,
        get_file(
            parent_widget,
            f"Select scoring image (.tif) or multi gonad file (*{MULTI_GONAD_FILE_EXTENSION})",
        ),
    )


def open_scoring_zarr_directory(
    napari_viewer: "ViewerModel", parent_widget: QWidget
) -> OpenFileReturns:
    file_path = get_directory(
        parent_widget, "Select scoring OME.zarr directory"
    )
    print(f"open_scoring_zarr_directory: selected path={file_path}")
    if file_path is not None and not file_path.endswith(".zarr"):
        show_info("Please select a directory ending in .zarr")
        return None
    return _open_scoring_path(napari_viewer, parent_widget, file_path)


def _open_scoring_path(
    napari_viewer: "ViewerModel",
    parent_widget: QWidget,
    file_path: str | None,
) -> OpenFileReturns:
    print(f"_open_scoring_path: start with path={file_path}")
    if len(napari_viewer.layers) > 0:
        print(f"_open_scoring_path: layers open={len(napari_viewer.layers)}")
        confirmed_result: bool = confirm_dialog(
            napari_viewer,
            "Layers are open, it is required to close all layers before scoring. Confirm?",
        )
        if not confirmed_result:
            print("_open_scoring_path: user cancelled close layers")
            return None
    napari_viewer.layers.clear()
    if file_path is None:
        print("_open_scoring_path: no path provided")
        return None
    validated_parsers_dict: dict[str, ConfigParser] | Literal["invalid"]
    if file_path.endswith((".tif", ".ome.zarr")):
        print("_open_scoring_path: validating image path")
        validated_parsers_dict = validate_image_file_path(file_path)
    elif file_path.endswith(MULTI_GONAD_FILE_EXTENSION):
        print("_open_scoring_path: validating multigonad file")
        validated_parsers_dict = validate_multigonad_file_path(file_path)
    else:
        print("_open_scoring_path: invalid file extension")
        validated_parsers_dict = "invalid"
    if validated_parsers_dict == "invalid":
        print("_open_scoring_path: validation failed")
        return "failed"
    print(
        f"_open_scoring_path: validation ok, entries={len(validated_parsers_dict)}"
    )
    clsp_sbs_object_list: list[CLSPSbsObject] = []
    for gonad_file_path, gonad_parser in validated_parsers_dict.items():
        print(f"_open_scoring_path: processing gonad path={gonad_file_path}")
        gonad_file_name: str = os.path.basename(gonad_file_path)
        sbs_directory: str = os.path.join(
            gonad_file_path,
            DEFAULT_PROJECT_NAME,
            PICK_NUCLEI_DIR_NAME,
            CUT_SBS_DIR_NAME,
        )
        if not os.path.exists(sbs_directory):
            show_info(f"The sbs directory {sbs_directory} doesn't exist")
            print(f"The sbs directory {sbs_directory} doesn't exist")
            return "failed"
        metadata_by_sbs_name = _load_sbs_metadata_by_name(sbs_directory)
        tile_infos = _load_tile_infos_from_gonad_dir(gonad_file_path)
        scored_nuclei_dir: str = os.path.join(
            gonad_file_path, DEFAULT_PROJECT_NAME, SCORED_NUCLEI_DIR_NAME
        )
        os.makedirs(scored_nuclei_dir, exist_ok=True)
        for region_index in range(len(gonad_parser["NucleiCount"])):
            region_string = "region-" + str(region_index + 1)
            number_of_sbs: int = int(
                gonad_parser["NucleiCount"][region_string]
            )
            print(
                f"_open_scoring_path: region={region_string} sbs_count={number_of_sbs}"
            )
            for sbs_index in range(number_of_sbs):
                sbs_string: str = "sbs" + str(sbs_index + 1)
                sbs_file_name: str = (
                    region_string + "_" + sbs_string + SBS_FILE_NAME_EXTENSION
                )
                sbs_file_path: str = os.path.join(sbs_directory, sbs_file_name)
                if not os.path.exists(sbs_file_path):
                    show_info(
                        f"The sbs file with path {sbs_file_path} doesn't exist"
                    )
                    print(
                        f"The sbs file with path {sbs_file_path} doesn't exist"
                    )
                    return "failed"
                (
                    setting_contrast,
                    overlapping_tiles,
                    contrast_source,
                ) = _get_setting_contrast_for_sbs(
                    gonad_file_path,
                    metadata_by_sbs_name.get(sbs_file_name),
                    tile_infos,
                )
                current_sbs_object: CLSPSbsObject = CLSPSbsObject(
                    napari_viewer,
                    sbs_string,
                    region_string,
                    scored_nuclei_dir,
                    sbs_file_path,
                    gonad_file_name,
                    metadata_by_sbs_name.get(sbs_file_name),
                    setting_contrast,
                    overlapping_tiles,
                    contrast_source,
                )
                clsp_sbs_object_list.append(current_sbs_object)
    print(f"_open_scoring_path: built {len(clsp_sbs_object_list)} sbs objects")
    return (clsp_sbs_object_list, file_path)


def str_to_bool(string: str) -> bool:
    return string.lower() in {"true", "1"}


def _load_sbs_metadata_by_name(
    sbs_directory: str,
) -> dict[str, tuple[int, int, int, int]]:
    metadata_path = os.path.join(sbs_directory, SBS_METADATA_FILE_NAME)
    if not os.path.exists(metadata_path):
        return {}
    metadata_df = pd.read_csv(metadata_path)
    required_columns = {"sbs_image_name", "y1", "x1", "y2", "x2"}
    if not required_columns.issubset(metadata_df.columns):
        return {}
    metadata_by_name: dict[str, tuple[int, int, int, int]] = {}
    for _, row in metadata_df.iterrows():
        sbs_image_name = str(row["sbs_image_name"])
        y1 = int(cast(float, row["y1"]))
        x1 = int(cast(float, row["x1"]))
        y2 = int(cast(float, row["y2"]))
        x2 = int(cast(float, row["x2"]))
        metadata_by_name[sbs_image_name] = (
            y1,
            x1,
            y2,
            x2,
        )
    return metadata_by_name


def load_tile_bounding_boxes_from_gonad_dir(
    gonad_dir: str,
) -> dict[int, dict[str, int]]:
    tile_infos = _load_tile_infos_from_gonad_dir(gonad_dir)
    tile_bounding_boxes: dict[int, dict[str, int]] = {}
    for tile_index, tile_info in tile_infos.items():
        tile_bounding_boxes[tile_index] = {
            "y_min_px_index": tile_info["y_min_px_index"],
            "y_max_px_index_exclusive": tile_info["y_max_px_index_exclusive"],
            "x_min_px_index": tile_info["x_min_px_index"],
            "x_max_px_index_exclusive": tile_info["x_max_px_index_exclusive"],
        }
    return tile_bounding_boxes


def _load_tile_infos_from_gonad_dir(
    gonad_dir: str,
) -> dict[int, dict[str, int | str]]:
    tile_positions_paths = sorted(Path(gonad_dir).glob("*_tile_positions.csv"))
    if len(tile_positions_paths) == 0:
        return {}
    tile_positions_path = tile_positions_paths[0]
    tile_positions_stem = tile_positions_path.name[
        : -len("_tile_positions.csv")
    ]
    tiles_dir = Path(gonad_dir) / f"{tile_positions_stem}_tiles"
    with tile_positions_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = [dict(row) for row in reader]
    tile_infos: dict[int, dict[str, int | str]] = {}
    for tile_index, row in enumerate(rows):
        tile_info: dict[str, int | str] = {}
        tile_name = (row.get("tile_name") or "").strip()
        tile_path = (row.get("tile_path") or "").strip()
        resolved_tile_path = ""
        if tile_name != "":
            local_tile_path = tiles_dir / tile_name
            if local_tile_path.exists():
                resolved_tile_path = str(local_tile_path)
        if resolved_tile_path == "" and tile_path != "":
            resolved_tile_path = tile_path
        if resolved_tile_path != "":
            tile_info["tile_path"] = resolved_tile_path
        for dim in ("y", "x"):
            min_key = f"{dim}_min_px_index"
            max_key = f"{dim}_max_px_index_exclusive"
            min_value = (row.get(min_key) or "").strip()
            max_value = (row.get(max_key) or "").strip()
            if min_value != "":
                tile_info[min_key] = int(min_value)
            if max_value != "":
                tile_info[max_key] = int(max_value)
        if tile_info:
            tile_infos[tile_index] = tile_info
    return tile_infos


def _crop_box_intersects_tile(
    crop_box_yx: tuple[int, int, int, int],
    tile_info: dict[str, int | str],
) -> bool:
    y1, x1, y2, x2 = crop_box_yx
    tile_y1 = int(cast(int, tile_info["y_min_px_index"]))
    tile_y2 = int(cast(int, tile_info["y_max_px_index_exclusive"]))
    tile_x1 = int(cast(int, tile_info["x_min_px_index"]))
    tile_x2 = int(cast(int, tile_info["x_max_px_index_exclusive"]))
    return y1 < tile_y2 and y2 > tile_y1 and x1 < tile_x2 and x2 > tile_x1


def _get_setting_contrast_for_sbs(
    gonad_dir: str,
    crop_box_yx: tuple[int, int, int, int] | None,
    tile_infos: dict[int, dict[str, int | str]],
) -> tuple[dict[int, tuple[float, float]] | None, list[int], str]:
    stitched_project_dir = os.path.join(gonad_dir, DEFAULT_PROJECT_NAME)
    stitched_contrasts = get_loaded_image_contrasts(stitched_project_dir)
    if crop_box_yx is None:
        return stitched_contrasts, [], "stitched"
    overlapping_tiles = [
        tile_index
        for tile_index in sorted(tile_infos.keys())
        if _crop_box_intersects_tile(crop_box_yx, tile_infos[tile_index])
    ]
    if len(overlapping_tiles) == 0:
        return stitched_contrasts, [], "stitched"
    tile_info = tile_infos[overlapping_tiles[-1]]
    tile_path_value = tile_info.get("tile_path")
    if not isinstance(tile_path_value, str) or tile_path_value == "":
        return stitched_contrasts, overlapping_tiles, "stitched"
    tile_contrasts_path = get_tile_contrasts_file_path(tile_path_value)
    tile_contrasts = get_loaded_image_contrasts_from_file_path(
        tile_contrasts_path
    )
    if tile_contrasts is not None:
        return tile_contrasts, overlapping_tiles, "tile"
    return stitched_contrasts, overlapping_tiles, "stitched"


def get_valid_points_summary_parser_from_image_dir(
    image_dir: str,
) -> ConfigParser | None:
    summary_points_file_path: str = os.path.join(
        image_dir,
        DEFAULT_PROJECT_NAME,
        PICK_NUCLEI_DIR_NAME,
        POINTS_SUMMARY_FILE_NAME,
    )
    if not os.path.exists(summary_points_file_path):
        return None
    config_parser: ConfigParser = ConfigParser()
    config_parser.read(summary_points_file_path)
    if not config_parser.has_section("NucleiCount"):
        return None
    if len(config_parser["NucleiCount"]) <= 0:
        return None
    for region_index in range(len(config_parser["NucleiCount"])):
        region_string: str = "region-" + str(region_index + 1)
        saved_sbs_state: str = config_parser["SavedSbsState"][region_string]
        bool_saved_sbs_sate: bool = str_to_bool(saved_sbs_state)
        if not bool_saved_sbs_sate:
            show_info(
                f"The directory {image_dir} has not created all SBS files.ERROR"
            )
            return None
    return config_parser


def validate_image_file_path(
    file_path: str,
) -> dict[str, ConfigParser] | Literal["invalid"]:
    if os.path.isdir(file_path) and file_path.endswith(".zarr"):
        image_dir = os.path.dirname(file_path)
    else:
        image_dir = os.path.dirname(file_path)
    print(f"validate_image_file_path: image_dir={image_dir}")
    image_summary_points_parser: ConfigParser | None = (
        get_valid_points_summary_parser_from_image_dir(image_dir)
    )
    if image_summary_points_parser is None:
        print("validate_image_file_path: summary parser invalid")
        return "invalid"
    print("validate_image_file_path: summary parser ok")
    return {image_dir: image_summary_points_parser}


def validate_multigonad_file_path(
    file_path: str,
) -> dict[str, ConfigParser] | Literal["invalid"]:
    gonad_parser: ConfigParser = ConfigParser()
    gonad_parser.read(file_path)
    if not gonad_parser.has_section("GonadDirectoryPaths"):
        return "invalid"
    if len(gonad_parser["GonadDirectoryPaths"]) <= 0:
        return "invalid"
    individual_gonad_parsers: dict[str, ConfigParser] = {}
    for gonad_index in range(len(gonad_parser["GonadDirectoryPaths"])):
        gonad_str = "gonad-" + str(gonad_index + 1)
        gonad_path = gonad_parser["GonadDirectoryPaths"][gonad_str]
        validated_parser: ConfigParser | None = (
            get_valid_points_summary_parser_from_image_dir(gonad_path)
        )
        if validated_parser is None:
            show_info(
                f"The gonad path {gonad_path} had an invalid points summary file. ERROR"
            )
            return "invalid"
        individual_gonad_parsers[gonad_path] = validated_parser
    return individual_gonad_parsers


def read_file_flags(flags_path: str) -> list[str]:
    with open(flags_path) as f:
        return [line.strip() for line in f if line.strip() != ""]


def write_flags(flags_path: str, lines: list[str]) -> None:
    writing_lines: list[str] = [
        line.strip() for line in lines if line.strip() != ""
    ]
    writing_lines = sorted(set(writing_lines))
    print("")
    print(f"The writing lines are: {writing_lines}")
    with open(flags_path, "w") as f:
        f.write("\n".join(writing_lines))

    print(f"Lines written at {flags_path}")


def add_flag_to_sbs(image_path: str, passing_flag: str) -> None:
    flags_file_path: str = resolve_flags_file_name(image_path)
    print("")
    print(f"The flags file path is: {flags_file_path}")
    print("")
    lines = read_file_flags(flags_file_path)
    if passing_flag not in lines:
        lines.append(passing_flag)
        print("")
        print(f"The lines are: {lines}")
    else:
        show_error(f"The tag {passing_flag} already exists in the flags file.")
        return
    write_flags(flags_file_path, lines)
    return


def remove_flag_from_sbs(image_path: str, passing_flag: str) -> None:
    flags_file_path: str = resolve_flags_file_name(image_path)
    lines = read_file_flags(flags_file_path)
    if passing_flag in lines:
        lines.remove(passing_flag)
    else:
        show_error(f"The tag {passing_flag} does not exist in the flags file.")
        return
    write_flags(flags_file_path, lines)
    return


def flag_in_image(image_path: str, searching_flag: str) -> bool:
    return flag_exists(resolve_flags_file_name(image_path), searching_flag)


def flag_exists(flags_path: str, searching_flag: str) -> bool:
    flags: list[str] = read_file_flags(flags_path)
    return searching_flag in flags


def resolve_flags_file_name(image_path: str) -> str:
    image_dir: str = os.path.dirname(image_path)
    image_path_obj: Path = Path(image_path)
    image_path_obj_stem: str = image_path_obj.stem
    image_flag_file_name: str = image_path_obj_stem + "_flags.txt"
    image_flag_file_path: str = os.path.join(image_dir, image_flag_file_name)
    if not os.path.exists(image_flag_file_path):
        with open(image_flag_file_path, "w") as f:
            f.write("")
    return image_flag_file_path


class CLSPRegion:
    def __init__(
        self,
        napari_viewer: "ViewerModel",
        region_index: int,
        scored_nuclei_dir: str,
    ):
        self._napari_viewer = napari_viewer
        self._region_index: int = region_index
        self._score_nuclei_dir = scored_nuclei_dir

        self._sbs_dict: dict[str, CLSPSbsObject] = {}

    @property
    def region_index(self) -> int:
        return self._region_index

    @region_index.setter
    def region_index(self, value: int) -> None:
        self._region_index = value

    def name(self) -> str:
        return "region-" + str(self._region_index)
