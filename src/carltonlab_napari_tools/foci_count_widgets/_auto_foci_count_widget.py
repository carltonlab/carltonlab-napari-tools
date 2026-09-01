from __future__ import annotations

import configparser
import csv
import importlib
import threading
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd
from matplotlib.path import Path as MplPath
from multiview_stitcher import ngff_utils
from napari.layers import Image
from napari.utils.notifications import show_warning
from numpy.typing import NDArray
from qtpy.QtCore import QMetaObject, Qt, Slot
from qtpy.QtWidgets import (
    QDoubleSpinBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)
from tifffile import imwrite

from carltonlab_napari_tools._shared_variables import (
    AUTO_COUNT_DIR_NAME,
    CUT_SBS_DIR_NAME,
    EDITED_REGIONS_FILE_NAME,
    PICK_NUCLEI_DIR_NAME,
    POINTS_SUMMARY_FILE_NAME,
    PROJECT_FILE_DIR_NAME,
    REGIONS_CONFIGURATION_FILE_NAME,
    REGIONS_DIR_NAME,
    SBS_FILE_NAME_EXTENSION,
    SBS_METADATA_FILE_NAME,
    SCORED_NUCLEI_DIR_NAME,
    SCORED_NUCLEI_FOCI_SUMMARY_FILE_NAME,
    SCORED_NUCLEI_POINTS_FILE_NAME_EXTENSION,
    SEGMENTATION_DIR_NAME,
    SQUARES_FILE_NAME_EXTENSION,
    STITCHED_IMAGE_DIR_NAME,
    TILES_CONFIG_FILE_NAME,
    TILES_DIR_NAME,
)
from carltonlab_napari_tools._shared_widgets import get_directory
from carltonlab_napari_tools._tile_utils import (
    ensure_tiles_config,
    load_tile_contrasts,
    move_tiles,
)
from carltonlab_napari_tools._utils import (
    create_project_structure,
    get_clsp_project_path,
    is_supported_image_entry,
    parse_channel_string,
    resolve_clsp_project_path,
)
from carltonlab_napari_tools._viewer_utils import (
    close_image_layers,
)
from carltonlab_napari_tools.automatic_foci_count._auto_foci_count import (
    auto_count_binary_mask_outputs_exist,
    auto_count_outputs_exist,
    auto_count_preprocessed_spots_outputs_exist,
    compute_shared_masked_normalization_bounds,
    get_auto_count_output_paths,
    run_auto_count_on_paths,
    save_points_csv_for_napari,
)
from carltonlab_napari_tools.channel_extraction import extract_project_tiles
from carltonlab_napari_tools.general_widgets._project_list_widget import (
    CLTProjectListWidget,
)
from carltonlab_napari_tools.image_stitching import (
    get_stitched_output_path,
    stitch_ome_zarr_images,
)
from carltonlab_napari_tools.image_stitching._stitching_options_widget import (
    CLTStitchingOptionsWidget,
)
from carltonlab_napari_tools.segmentation import (
    clean_segmentation_file,
    get_cleaned_segmentation_output_path,
    load_segmentation_npy,
    run_segmentation_subprocess,
)
from carltonlab_napari_tools.segmentation._segmentation import (
    load_ome_zarr_image_zyx,
)
from carltonlab_napari_tools.spline_manager._spline_manager import (
    load_regions_configuration,
)

if TYPE_CHECKING:
    from napari.components import ViewerModel


def _get_ome_zarr_channel_count(image_path: str | Path) -> int:
    source_sim = ngff_utils.read_sim_from_ome_zarr(
        str(image_path),
        transform_key="stage_metadata",
    )
    dims = [str(dim).lower() for dim in source_sim.dims]
    if "c" not in dims:
        return 1

    c_dim = source_sim.dims[dims.index("c")]
    return int(source_sim.sizes[c_dim])


def load_cleaned_segmentation_labels(
    segmentation_path: str | Path,
) -> NDArray[np.uint32]:
    cleaned_path = get_cleaned_segmentation_output_path(segmentation_path)
    labels = load_segmentation_npy(cleaned_path)
    if labels.ndim != 3:
        raise ValueError(
            "Cleaned segmentation labels must be 3D ZYX. "
            f"Got shape {labels.shape} from {cleaned_path}"
        )
    return np.asarray(labels, dtype=np.uint32)


def build_tile_local_squares_from_labels(
    labels_zyx: NDArray[np.uint32],
) -> NDArray[np.float32]:
    square_records = build_tile_local_square_records_from_labels(labels_zyx)
    if len(square_records) == 0:
        return np.empty((0, 4, 2), dtype=np.float32)
    return np.asarray(
        [record["square_yx"] for record in square_records],
        dtype=np.float32,
    )


def build_tile_local_square_records_from_labels(
    labels_zyx: NDArray[np.uint32],
) -> list[dict[str, object]]:
    labels = np.asarray(labels_zyx)
    if labels.ndim != 3:
        raise ValueError(f"Expected 3D ZYX labels, got shape {labels.shape}")

    object_ids = np.unique(labels)
    object_ids = object_ids[object_ids > 0]
    if len(object_ids) == 0:
        return []

    square_records: list[dict[str, object]] = []
    for object_id in object_ids:
        zyx_coords = np.argwhere(labels == object_id)
        if zyx_coords.size == 0:
            continue

        z_coords = zyx_coords[:, 0]
        y_coords = zyx_coords[:, 1]
        x_coords = zyx_coords[:, 2]
        z_min = int(z_coords.min())
        z_max_exclusive = int(z_coords.max() + 1)
        y_min = float(y_coords.min())
        y_max = float(y_coords.max() + 1)
        x_min = float(x_coords.min())
        x_max = float(x_coords.max() + 1)

        height = y_max - y_min
        width = x_max - x_min
        side_length = max(height, width)

        y_center = (y_min + y_max) / 2.0
        x_center = (x_min + x_max) / 2.0
        half_side = side_length / 2.0

        square_y_min = y_center - half_side
        square_y_max = y_center + half_side
        square_x_min = x_center - half_side
        square_x_max = x_center + half_side

        square_yx = np.asarray(
            [
                [square_y_min, square_x_min],
                [square_y_min, square_x_max],
                [square_y_max, square_x_max],
                [square_y_max, square_x_min],
            ],
            dtype=np.float32,
        )
        square_records.append(
            {
                "label_id": int(object_id),
                "square_yx": square_yx,
                "z1": z_min,
                "z2": z_max_exclusive,
            }
        )

    return square_records


def get_tile_stitched_pixel_offsets(
    stitched_image_path: str | Path,
    tile_index: int,
) -> tuple[float, float]:
    stitched_path = Path(stitched_image_path)
    stitched_name = stitched_path.name
    if stitched_name.endswith(".ome.zarr"):
        stitched_stem = stitched_name[: -len(".ome.zarr")]
    else:
        stitched_stem = stitched_path.stem

    tile_positions_path = (
        stitched_path.parent
        / TILES_DIR_NAME
        / f"{stitched_stem}_tile_positions.csv"
    )
    if not tile_positions_path.exists():
        raise FileNotFoundError(
            f"Tile positions file not found: {tile_positions_path}"
        )

    with tile_positions_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = [dict(row) for row in reader]

    if tile_index < 0 or tile_index >= len(rows):
        raise IndexError(
            f"Tile index {tile_index} is out of bounds for {tile_positions_path}"
        )

    row = rows[tile_index]
    y_offset = float((row.get("y_min_px_index") or "0").strip())
    x_offset = float((row.get("x_min_px_index") or "0").strip())
    return y_offset, x_offset


def load_napari_points_csv(
    points_path: str | Path,
) -> NDArray[np.float32]:
    points_df = pd.read_csv(points_path)
    axis_columns = sorted(
        [column for column in points_df.columns if column.startswith("axis-")],
        key=lambda column: int(column.split("-")[-1]),
    )
    if len(axis_columns) == 0:
        return np.empty((0, 0), dtype=np.float32)
    if len(points_df) == 0:
        return np.empty((0, len(axis_columns)), dtype=np.float32)
    return points_df[axis_columns].to_numpy(dtype=np.float32)


def map_tile_local_points_to_stitched_image(
    tile_local_points_zyx: NDArray[np.float32],
    stitched_image_path: str | Path,
    tile_index: int,
) -> NDArray[np.float32]:
    points = np.asarray(tile_local_points_zyx, dtype=np.float32)
    if points.ndim != 2 or points.shape[1] != 3:
        raise ValueError(
            f"Expected tile-local points with shape (N, 3), got {points.shape}"
        )
    if len(points) == 0:
        return np.empty((0, 3), dtype=np.float32)

    y_offset, x_offset = get_tile_stitched_pixel_offsets(
        stitched_image_path, tile_index
    )
    stitched_points = points.copy()
    stitched_points[:, 1] += y_offset
    stitched_points[:, 2] += x_offset
    return stitched_points


def filter_points_inside_label(
    points_zyx: NDArray[np.float32],
    labels_zyx: NDArray[np.uint32],
    label_id: int,
) -> NDArray[np.float32]:
    filtered, _rejected = filter_points_inside_label_with_rejections(
        points_zyx, labels_zyx, label_id
    )
    return filtered


def filter_points_inside_label_with_rejections(
    points_zyx: NDArray[np.float32],
    labels_zyx: NDArray[np.uint32],
    label_id: int,
) -> tuple[NDArray[np.float32], NDArray[np.float32]]:
    points = np.asarray(points_zyx, dtype=np.float32)
    labels = np.asarray(labels_zyx, dtype=np.uint32)
    if points.ndim != 2 or points.shape[1] != 3:
        raise ValueError(
            f"Expected points with shape (N, 3), got {points.shape}"
        )
    if labels.ndim != 3:
        raise ValueError(f"Expected 3D labels, got shape {labels.shape}")
    if len(points) == 0:
        return np.empty((0, 3), dtype=np.float32), points

    rounded_indices = np.rint(points).astype(np.int64)
    valid = (
        (rounded_indices[:, 0] >= 0)
        & (rounded_indices[:, 0] < labels.shape[0])
        & (rounded_indices[:, 1] >= 0)
        & (rounded_indices[:, 1] < labels.shape[1])
        & (rounded_indices[:, 2] >= 0)
        & (rounded_indices[:, 2] < labels.shape[2])
    )
    if not np.any(valid):
        return np.empty((0, 3), dtype=np.float32), points

    valid_indices = rounded_indices[valid]
    inside_label = labels[
        valid_indices[:, 0],
        valid_indices[:, 1],
        valid_indices[:, 2],
    ] == np.uint32(label_id)
    valid_points = points[valid]
    return (
        valid_points[inside_label].astype(np.float32, copy=False),
        np.concatenate((points[~valid], valid_points[~inside_label])).astype(
            np.float32, copy=False
        ),
    )


def get_scored_nuclei_output_paths(
    scored_nuclei_dir: str | Path,
    sbs_name: str,
) -> tuple[Path, Path]:
    scored_nuclei_path = Path(scored_nuclei_dir)
    sbs_stem = sbs_name[: -len(SBS_FILE_NAME_EXTENSION)]
    return (
        scored_nuclei_path
        / f"{sbs_stem}{SCORED_NUCLEI_POINTS_FILE_NAME_EXTENSION}",
        scored_nuclei_path / f"{sbs_stem}_zero_points.txt",
    )


def map_tile_local_squares_to_stitched_image(
    tile_local_squares_yx: NDArray[np.float32],
    stitched_image_path: str | Path,
    tile_index: int,
) -> NDArray[np.float32]:
    squares = np.asarray(tile_local_squares_yx, dtype=np.float32)
    if squares.ndim != 3 or squares.shape[1:] != (4, 2):
        raise ValueError(
            "Expected square polygons with shape (N, 4, 2), "
            f"got {squares.shape}"
        )
    if len(squares) == 0:
        return np.empty((0, 4, 2), dtype=np.float32)

    y_offset, x_offset = get_tile_stitched_pixel_offsets(
        stitched_image_path, tile_index
    )
    offset_yx = np.asarray([y_offset, x_offset], dtype=np.float32)
    return squares + offset_yx


def map_tile_local_square_records_to_stitched_image(
    square_records: list[dict[str, object]],
    stitched_image_path: str | Path,
    tile_index: int,
) -> list[dict[str, object]]:
    if len(square_records) == 0:
        return []
    y_offset, x_offset = get_tile_stitched_pixel_offsets(
        stitched_image_path, tile_index
    )
    offset_yx = np.asarray([y_offset, x_offset], dtype=np.float32)
    stitched_records: list[dict[str, object]] = []
    for record in square_records:
        square_yx = np.asarray(record["square_yx"], dtype=np.float32)
        stitched_records.append(
            {
                "label_id": int(record["label_id"]),
                "tile_index": tile_index,
                "square_yx": square_yx + offset_yx,
                "z1": int(record["z1"]),
                "z2": int(record["z2"]),
            }
        )
    return stitched_records


def load_expanded_region_polygons(
    edited_regions_csv_path: str | Path,
) -> list[NDArray[np.float32]]:
    edited_regions_path = Path(edited_regions_csv_path)
    if not edited_regions_path.exists():
        raise FileNotFoundError(
            f"Edited regions file not found: {edited_regions_path}"
        )

    df = pd.read_csv(edited_regions_path)
    required_columns = {"index", "vertex-index", "axis-0", "axis-1"}
    missing_columns = required_columns - set(df.columns)
    if missing_columns:
        raise ValueError(
            "Edited regions CSV is missing required columns: "
            f"{sorted(missing_columns)}"
        )

    polygons: list[NDArray[np.float32]] = []
    for shape_index in sorted(df["index"].astype(int).unique()):
        shape_df = df[df["index"].astype(int) == shape_index].copy()
        shape_df = shape_df.sort_values("vertex-index")
        polygon = shape_df[["axis-0", "axis-1"]].to_numpy(dtype=np.float32)
        if polygon.ndim != 2 or polygon.shape[0] < 3:
            continue
        polygons.append(polygon)
    return polygons


def get_square_centers(
    squares_yx: NDArray[np.float32],
) -> NDArray[np.float32]:
    squares = np.asarray(squares_yx, dtype=np.float32)
    if squares.ndim != 3 or squares.shape[1:] != (4, 2):
        raise ValueError(
            "Expected square polygons with shape (N, 4, 2), "
            f"got {squares.shape}"
        )
    if len(squares) == 0:
        return np.empty((0, 2), dtype=np.float32)
    return squares.mean(axis=1, dtype=np.float32)


def assign_stitched_squares_to_regions(
    stitched_squares_yx: NDArray[np.float32],
    region_polygons_yx: list[NDArray[np.float32]],
) -> tuple[dict[int, NDArray[np.float32]], NDArray[np.float32]]:
    squares = np.asarray(stitched_squares_yx, dtype=np.float32)
    if squares.ndim != 3 or squares.shape[1:] != (4, 2):
        raise ValueError(
            "Expected square polygons with shape (N, 4, 2), "
            f"got {squares.shape}"
        )

    grouped_squares: dict[int, list[np.ndarray]] = {
        region_index: [] for region_index in range(len(region_polygons_yx))
    }
    unassigned_squares: list[np.ndarray] = []

    square_centers = get_square_centers(squares)
    region_paths = [
        MplPath(np.asarray(poly, dtype=np.float32))
        for poly in region_polygons_yx
    ]

    for square, center in zip(squares, square_centers, strict=True):
        assigned = False
        for region_index, region_path in enumerate(region_paths):
            if region_path.contains_point(center):
                grouped_squares[region_index].append(
                    np.asarray(square, dtype=np.float32)
                )
                assigned = True
                break
        if not assigned:
            unassigned_squares.append(np.asarray(square, dtype=np.float32))

    grouped_arrays: dict[int, NDArray[np.float32]] = {}
    for region_index, region_squares in grouped_squares.items():
        if len(region_squares) == 0:
            grouped_arrays[region_index] = np.empty(
                (0, 4, 2), dtype=np.float32
            )
        else:
            grouped_arrays[region_index] = np.asarray(
                region_squares, dtype=np.float32
            )

    if len(unassigned_squares) == 0:
        unassigned_array = np.empty((0, 4, 2), dtype=np.float32)
    else:
        unassigned_array = np.asarray(unassigned_squares, dtype=np.float32)

    return grouped_arrays, unassigned_array


def assign_stitched_square_records_to_regions(
    stitched_square_records: list[dict[str, object]],
    region_polygons_yx: list[NDArray[np.float32]],
) -> tuple[dict[int, list[dict[str, object]]], list[dict[str, object]]]:
    grouped_records: dict[int, list[dict[str, object]]] = {
        region_index: [] for region_index in range(len(region_polygons_yx))
    }
    unassigned_records: list[dict[str, object]] = []
    region_paths = [
        MplPath(np.asarray(poly, dtype=np.float32))
        for poly in region_polygons_yx
    ]

    for record in stitched_square_records:
        square_yx = np.asarray(record["square_yx"], dtype=np.float32)
        center = square_yx.mean(axis=0, dtype=np.float32)
        assigned = False
        for region_index, region_path in enumerate(region_paths):
            if region_path.contains_point(center):
                grouped_records[region_index].append(record)
                assigned = True
                break
        if not assigned:
            unassigned_records.append(record)

    return grouped_records, unassigned_records


def _concatenate_square_batches(
    square_batches: list[NDArray[np.float32]],
) -> NDArray[np.float32]:
    non_empty_batches = [
        np.asarray(batch, dtype=np.float32)
        for batch in square_batches
        if len(batch) > 0
    ]
    if len(non_empty_batches) == 0:
        return np.empty((0, 4, 2), dtype=np.float32)
    return np.concatenate(non_empty_batches, axis=0).astype(np.float32)


def build_region_squares_from_cleaned_segmentations(
    segmentation_paths_by_tile: dict[int, str | Path],
    stitched_image_path: str | Path,
    edited_regions_csv_path: str | Path,
) -> tuple[dict[int, NDArray[np.float32]], NDArray[np.float32]]:
    region_records_by_index, unassigned_records = (
        build_region_square_records_from_cleaned_segmentations(
            segmentation_paths_by_tile=segmentation_paths_by_tile,
            stitched_image_path=stitched_image_path,
            edited_regions_csv_path=edited_regions_csv_path,
        )
    )
    grouped_region_squares: dict[int, NDArray[np.float32]] = {
        region_index: (
            np.asarray(
                [record["square_yx"] for record in records],
                dtype=np.float32,
            )
            if len(records) > 0
            else np.empty((0, 4, 2), dtype=np.float32)
        )
        for region_index, records in region_records_by_index.items()
    }
    unassigned_array = (
        np.asarray(
            [record["square_yx"] for record in unassigned_records],
            dtype=np.float32,
        )
        if len(unassigned_records) > 0
        else np.empty((0, 4, 2), dtype=np.float32)
    )
    return grouped_region_squares, unassigned_array


def build_region_square_records_from_cleaned_segmentations(
    segmentation_paths_by_tile: dict[int, str | Path],
    stitched_image_path: str | Path,
    edited_regions_csv_path: str | Path,
) -> tuple[dict[int, list[dict[str, object]]], list[dict[str, object]]]:
    region_polygons_yx = load_expanded_region_polygons(edited_regions_csv_path)
    region_record_batches: dict[int, list[dict[str, object]]] = {
        region_index: [] for region_index in range(len(region_polygons_yx))
    }
    all_unassigned_records: list[dict[str, object]] = []

    for tile_index, segmentation_path in sorted(
        segmentation_paths_by_tile.items()
    ):
        labels_zyx = load_cleaned_segmentation_labels(segmentation_path)
        tile_local_square_records = (
            build_tile_local_square_records_from_labels(labels_zyx)
        )
        stitched_square_records = (
            map_tile_local_square_records_to_stitched_image(
                tile_local_square_records,
                stitched_image_path=stitched_image_path,
                tile_index=tile_index,
            )
        )
        grouped_records, unassigned_records = (
            assign_stitched_square_records_to_regions(
                stitched_square_records,
                region_polygons_yx,
            )
        )
        for region_index, region_records in grouped_records.items():
            region_record_batches[region_index].extend(region_records)
        all_unassigned_records.extend(unassigned_records)

    return region_record_batches, all_unassigned_records


def save_region_squares_csvs(
    region_squares_by_index: dict[int, NDArray[np.float32]],
    pick_nuclei_directory: str | Path,
) -> list[tuple[int, bool, bool, bool]]:
    pick_nuclei_path = Path(pick_nuclei_directory)
    pick_nuclei_path.mkdir(parents=True, exist_ok=True)
    points_saved_list = get_points_saved_list(
        str(pick_nuclei_path),
        number_of_regions=len(region_squares_by_index),
    )
    updated_points_saved_list: list[tuple[int, bool, bool, bool]] = []

    for region_index in range(len(region_squares_by_index)):
        region_string = f"region-{region_index + 1}"
        region_squares = np.asarray(
            region_squares_by_index[region_index],
            dtype=np.float32,
        )
        previous_state = points_saved_list[region_index]
        if previous_state is None:
            saved_points = False
            saved_sbs = False
        else:
            saved_points = previous_state[1]
            saved_sbs = previous_state[3]

        nuclei_count = int(len(region_squares))
        has_squares = nuclei_count > 0
        if has_squares:
            square_rows: list[dict[str, float | int | str]] = []
            for square_index, square in enumerate(region_squares):
                for vertex_index, vertex in enumerate(square):
                    square_rows.append(
                        {
                            "index": square_index,
                            "shape-type": "polygon",
                            "vertex-index": vertex_index,
                            "axis-0": float(vertex[0]),
                            "axis-1": float(vertex[1]),
                        }
                    )
            region_squares_df = pd.DataFrame(square_rows)
            region_squares_path = (
                pick_nuclei_path
                / f"{region_string}{SQUARES_FILE_NAME_EXTENSION}"
            )
            region_squares_df.to_csv(region_squares_path, index=False)

        updated_points_saved_list.append(
            (nuclei_count, saved_points, has_squares, saved_sbs)
        )

    save_points_summary_file(
        updated_points_saved_list,
        str(pick_nuclei_path),
    )
    return updated_points_saved_list


def save_auto_cut_sbs_files_from_region_records(
    region_records_by_index: dict[int, list[dict[str, object]]],
    pick_nuclei_directory: str | Path,
    stitched_image_path: str | Path,
) -> list[tuple[int, bool, bool, bool]]:
    pick_nuclei_path = Path(pick_nuclei_directory)
    cut_sbs_dir = pick_nuclei_path / CUT_SBS_DIR_NAME
    cut_sbs_dir.mkdir(parents=True, exist_ok=True)

    channel_count = _get_ome_zarr_channel_count(stitched_image_path)
    stitched_channels = [
        load_ome_zarr_image_zyx(stitched_image_path, channel_index)[0]
        for channel_index in range(channel_count)
    ]
    stitched_stack = np.stack(stitched_channels, axis=1)
    max_z, _, max_y, max_x = stitched_stack.shape

    metadata_rows: list[dict[str, int | str]] = []
    points_saved_list = get_points_saved_list(
        str(pick_nuclei_path),
        number_of_regions=len(region_records_by_index),
    )
    updated_points_saved_list: list[tuple[int, bool, bool, bool]] = []

    for region_index in range(len(region_records_by_index)):
        region_string = f"region-{region_index + 1}"
        region_records = region_records_by_index[region_index]
        previous_state = points_saved_list[region_index]
        saved_points = False if previous_state is None else previous_state[1]
        saved_squares = False if previous_state is None else previous_state[2]

        for sbs_index, record in enumerate(region_records, start=1):
            square_yx = np.asarray(record["square_yx"], dtype=np.float32)
            z1 = max(0, int(record["z1"]))
            z2 = min(max_z, int(record["z2"]))
            y1, x1 = np.floor(square_yx.min(axis=0)).astype(int)
            y2, x2 = np.floor(square_yx.max(axis=0)).astype(int) + 1
            y1 = max(0, y1)
            x1 = max(0, x1)
            y2 = min(max_y, y2)
            x2 = min(max_x, x2)
            if z2 <= z1 or y2 <= y1 or x2 <= x1:
                continue

            sbs_name = (
                f"{region_string}_sbs{sbs_index}{SBS_FILE_NAME_EXTENSION}"
            )
            sbs_path = cut_sbs_dir / sbs_name
            cropped = stitched_stack[z1:z2, :, y1:y2, x1:x2]
            imwrite(
                sbs_path,
                cropped,
                imagej=True,
                metadata={"axes": "ZCYX"},
            )
            metadata_rows.append(
                {
                    "sbs_image_name": sbs_name,
                    "z1": int(z1),
                    "z2": int(z2),
                    "y1": int(y1),
                    "x1": int(x1),
                    "y2": int(y2),
                    "x2": int(x2),
                }
            )

        updated_points_saved_list.append(
            (
                int(len(region_records)),
                saved_points,
                saved_squares,
                True,
            )
        )

    metadata_path = cut_sbs_dir / SBS_METADATA_FILE_NAME
    existing_rows: dict[str, dict[str, int | str]] = {}
    if metadata_path.exists():
        with metadata_path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                sbs_name = str(row.get("sbs_image_name", ""))
                if sbs_name != "":
                    existing_rows[sbs_name] = dict(row)
    for row in metadata_rows:
        existing_rows[str(row["sbs_image_name"])] = row
    with metadata_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "sbs_image_name",
                "z1",
                "z2",
                "y1",
                "x1",
                "y2",
                "x2",
            ],
        )
        writer.writeheader()
        for row in existing_rows.values():
            writer.writerow(row)

    save_points_summary_file(updated_points_saved_list, str(pick_nuclei_path))
    return updated_points_saved_list


def save_auto_scored_nuclei_files_from_region_records(
    region_records_by_index: dict[int, list[dict[str, object]]],
    directory_path: str | Path,
    tile_paths: list[Path],
    stitched_image_path: str | Path,
) -> bool:
    project_files_dir = _get_project_files_path(directory_path)
    metadata_path = (
        project_files_dir
        / PICK_NUCLEI_DIR_NAME
        / CUT_SBS_DIR_NAME
        / SBS_METADATA_FILE_NAME
    )
    if not metadata_path.exists():
        show_warning(
            "Cannot save automatic scored nuclei files because the SBS "
            f"metadata file does not exist: {metadata_path}"
        )
        return False

    metadata_df = pd.read_csv(metadata_path)
    required_columns = {"sbs_image_name", "z1", "z2", "y1", "x1", "y2", "x2"}
    missing_columns = required_columns - set(metadata_df.columns)
    if missing_columns:
        raise ValueError(
            "SBS metadata is missing required columns: "
            f"{sorted(missing_columns)}"
        )

    metadata_by_name: dict[str, dict[str, int]] = {}
    for _, row in metadata_df.iterrows():
        sbs_name = str(row["sbs_image_name"])
        metadata_by_name[sbs_name] = {
            "z1": int(row["z1"]),
            "z2": int(row["z2"]),
            "y1": int(row["y1"]),
            "x1": int(row["x1"]),
            "y2": int(row["y2"]),
            "x2": int(row["x2"]),
        }

    auto_count_output_dir = project_files_dir / AUTO_COUNT_DIR_NAME
    filtered_points_by_tile: dict[int, NDArray[np.float32]] = {}
    labels_by_tile: dict[int, NDArray[np.uint32]] = {}
    segmentation_paths_by_tile: dict[int, Path] = {}
    for tile_index, tile_path in enumerate(tile_paths):
        segmentation_paths_by_tile[tile_index] = (
            _get_segmentation_output_path_for_tile(directory_path, tile_path)
        )
        _, _, filtered_points_path = get_auto_count_output_paths(
            tile_path, auto_count_output_dir
        )
        if filtered_points_path.exists():
            filtered_points_by_tile[tile_index] = load_napari_points_csv(
                filtered_points_path
            )
        else:
            filtered_points_by_tile[tile_index] = np.empty(
                (0, 3), dtype=np.float32
            )

    scored_nuclei_dir = project_files_dir / SCORED_NUCLEI_DIR_NAME
    scored_nuclei_dir.mkdir(parents=True, exist_ok=True)

    for region_index in range(len(region_records_by_index)):
        region_string = f"region-{region_index + 1}"
        region_records = region_records_by_index[region_index]
        for sbs_index, record in enumerate(region_records, start=1):
            sbs_name = (
                f"{region_string}_sbs{sbs_index}{SBS_FILE_NAME_EXTENSION}"
            )
            metadata = metadata_by_name.get(sbs_name)
            if metadata is None:
                raise ValueError(f"Missing SBS metadata row for {sbs_name}")

            tile_index = int(record["tile_index"])
            label_id = int(record["label_id"])
            if tile_index not in labels_by_tile:
                labels_by_tile[tile_index] = load_cleaned_segmentation_labels(
                    segmentation_paths_by_tile[tile_index]
                )

            tile_points = filtered_points_by_tile[tile_index]
            label_points_local, rejected_label_points = (
                filter_points_inside_label_with_rejections(
                    tile_points,
                    labels_by_tile[tile_index],
                    label_id,
                )
            )
            label_rejected_path = (
                scored_nuclei_dir
                / f"{sbs_name[: -len(SBS_FILE_NAME_EXTENSION)]}"
                "_rejected_cellpose_label_points.csv"
            )
            save_points_csv_for_napari(
                label_rejected_path, rejected_label_points
            )
            stitched_points = map_tile_local_points_to_stitched_image(
                label_points_local,
                stitched_image_path=stitched_image_path,
                tile_index=tile_index,
            )

            if len(stitched_points) > 0:
                inside_crop = (
                    (stitched_points[:, 0] >= metadata["z1"])
                    & (stitched_points[:, 0] < metadata["z2"])
                    & (stitched_points[:, 1] >= metadata["y1"])
                    & (stitched_points[:, 1] < metadata["y2"])
                    & (stitched_points[:, 2] >= metadata["x1"])
                    & (stitched_points[:, 2] < metadata["x2"])
                )
                local_points = stitched_points[inside_crop].copy()
                rejected_crop_points = stitched_points[~inside_crop]
                crop_rejected_path = (
                    scored_nuclei_dir
                    / f"{sbs_name[: -len(SBS_FILE_NAME_EXTENSION)]}"
                    "_rejected_sbs_crop_points.csv"
                )
                save_points_csv_for_napari(
                    crop_rejected_path, rejected_crop_points
                )
                if len(local_points) > 0:
                    local_points[:, 0] -= metadata["z1"]
                    local_points[:, 1] -= metadata["y1"]
                    local_points[:, 2] -= metadata["x1"]
            else:
                local_points = np.empty((0, 3), dtype=np.float32)
                crop_rejected_path = (
                    scored_nuclei_dir
                    / f"{sbs_name[: -len(SBS_FILE_NAME_EXTENSION)]}"
                    "_rejected_sbs_crop_points.csv"
                )
                save_points_csv_for_napari(
                    crop_rejected_path, np.empty((0, 3), dtype=np.float32)
                )

            points_output_path, zero_output_path = (
                get_scored_nuclei_output_paths(scored_nuclei_dir, sbs_name)
            )
            if len(local_points) == 0:
                if points_output_path.exists():
                    points_output_path.unlink()
                zero_output_path.write_text("", encoding="utf-8")
            else:
                if zero_output_path.exists():
                    zero_output_path.unlink()
                save_points_csv_for_napari(points_output_path, local_points)

    return True


def _get_segmentation_output_path_for_tile(
    directory_path: str | Path,
    tile_path: str | Path,
) -> Path:
    tile_path_obj = Path(tile_path)
    segmentation_output_dir = (
        _get_project_files_path(directory_path) / SEGMENTATION_DIR_NAME
    )
    return segmentation_output_dir / (
        f"{tile_path_obj.name[: -len('.ome.zarr')]}_meiotic_3d_crops_masks.npy"
    )


def _get_expected_source_image_count(directory_path: str | Path) -> int:
    directory = Path(directory_path)
    return sum(
        1 for entry in directory.iterdir() if is_supported_image_entry(entry)
    )


def _get_project_path(starting_path: str | Path) -> Path:
    project_path = resolve_clsp_project_path(Path(starting_path))
    if project_path is None:
        raise ValueError(
            f"No CLSP project found for starting path: {starting_path}"
        )
    return project_path


def _get_project_files_path(starting_path: str | Path) -> Path:
    return _get_project_path(starting_path) / PROJECT_FILE_DIR_NAME


def _get_project_tiles_path(starting_path: str | Path) -> Path:
    return _get_project_path(starting_path) / TILES_DIR_NAME


class AutoFociCountWidget(QWidget):
    def __init__(
        self,
        viewer: ViewerModel,
        parent: QWidget,
        project_list_widget: CLTProjectListWidget,
        set_contrasts_callback: Callable[[], None],
    ):
        super().__init__(parent=parent)
        self._viewer: ViewerModel = viewer
        self._parent: QWidget = parent
        self._project_list_widget = project_list_widget
        self._set_contrasts_callback = set_contrasts_callback

        self._helper_widget: QWidget
        self._helper_widget_layout: QVBoxLayout
        self._helper_content_widget: QWidget | None = None
        self._current_project_files_dir: str | None = None
        self._current_image_path: str | None = None
        self._current_stitched_images: list[Image] = []
        self._current_tile_paths: dict[int, str] = {}
        self._current_tile_image_layers: list[Image] = []
        self._batch_fc_running = False
        self._spotiflow_model_name = "synth_3d"

        self._layout: QVBoxLayout = QVBoxLayout()
        self._layout.setContentsMargins(2, 2, 2, 2)
        self.setLayout(self._layout)
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )

        self._all_c: QWidget = QWidget(parent=self)
        self._layout.addWidget(self._all_c)
        self._all_layout: QHBoxLayout = QHBoxLayout()
        self._all_layout.setContentsMargins(0, 0, 0, 0)
        self._all_layout.setSpacing(6)
        self._all_c.setLayout(self._all_layout)

        self._run_all_ts: QToggleSwitch = QToggleSwitch(parent=self)
        self._run_all_ts.setChecked(True)
        self._runn_all_l: QLabel = QLabel("Run entire workflow", parent=self)
        self._all_layout.addWidget(self._run_all_ts)
        self._all_layout.addWidget(self._runn_all_l)
        self._all_layout.addStretch()

        self._keep_channel_c: QWidget = QWidget(parent=self)
        self._layout.addWidget(self._keep_channel_c)
        self._keep_channel_layout: QVBoxLayout = QVBoxLayout()
        self._keep_channel_layout.setContentsMargins(0, 0, 0, 0)
        self._keep_channel_layout.setSpacing(6)
        self._keep_channel_c.setLayout(self._keep_channel_layout)

        self._keep_channel_l: QLabel = QLabel("Keeping channels")
        self._keep_channel_l.setStyleSheet("font-weight: bold")
        self._keep_channel_layout.addWidget(self._keep_channel_l)

        self._channel_edit_c: QWidget = QWidget(parent=self)
        self._keep_channel_layout.addWidget(self._channel_edit_c)
        self._channel_edit_layout: QHBoxLayout = QHBoxLayout()
        self._channel_edit_layout.setContentsMargins(0, 0, 0, 0)
        self._channel_edit_layout.setSpacing(6)
        self._channel_edit_c.setLayout(self._channel_edit_layout)

        self._keep_channel_ts: QToggleSwitch = QToggleSwitch()
        self._channel_edit_layout.addWidget(self._keep_channel_ts)
        self._keep_channel_ts.clicked.connect(self._keep_ts_toggled)

        self._keep_channel_le: QLineEdit = QLineEdit(parent=self)
        self._keep_channel_le.setSizePolicy(
            QSizePolicy(
                QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
            )
        )
        self._keep_channel_le.setText("1,2")
        self._channel_edit_layout.addWidget(self._keep_channel_le)
        self._keep_channel_ts.setChecked(True)

        self._keep_channel_ex_l: QLabel = QLabel("e.g. 1-2,4", parent=self)
        self._keep_channel_ex_l.setSizePolicy(
            QSizePolicy(
                QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred
            )
        )
        self._channel_edit_layout.addWidget(self._keep_channel_ex_l)

        self._stitching_options_widget = CLTStitchingOptionsWidget(parent=self)
        self._stitching_options_widget.set_gpu_enabled(True)
        self._stitching_options_widget.connect_gpu_toggle(
            self._use_gpu_ts_toggled
        )
        self._layout.addWidget(self._stitching_options_widget)

        self._binary_mask_filter_c: QWidget = QWidget(parent=self)
        self._layout.addWidget(self._binary_mask_filter_c)
        self._binary_mask_filter_layout: QVBoxLayout = QVBoxLayout()
        self._binary_mask_filter_layout.setContentsMargins(0, 0, 0, 0)
        self._binary_mask_filter_layout.setSpacing(6)
        self._binary_mask_filter_c.setLayout(self._binary_mask_filter_layout)

        self._binary_mask_filter_row_c: QWidget = QWidget(parent=self)
        self._binary_mask_filter_layout.addWidget(
            self._binary_mask_filter_row_c
        )
        self._binary_mask_filter_row_layout: QHBoxLayout = QHBoxLayout()
        self._binary_mask_filter_row_layout.setContentsMargins(0, 0, 0, 0)
        self._binary_mask_filter_row_layout.setSpacing(6)
        self._binary_mask_filter_row_c.setLayout(
            self._binary_mask_filter_row_layout
        )

        self._binary_mask_filter_ts: QToggleSwitch = QToggleSwitch(parent=self)
        self._binary_mask_filter_ts.setChecked(True)
        self._binary_mask_filter_ts.clicked.connect(
            self._binary_mask_filter_ts_toggled
        )
        self._binary_mask_filter_row_layout.addWidget(
            self._binary_mask_filter_ts
        )

        self._binary_mask_filter_l: QLabel = QLabel(
            "Filter channels", parent=self
        )
        self._binary_mask_filter_row_layout.addWidget(
            self._binary_mask_filter_l
        )

        self._binary_mask_channels_le: QLineEdit = QLineEdit(parent=self)
        self._binary_mask_channels_le.setSizePolicy(
            QSizePolicy(
                QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
            )
        )
        self._binary_mask_channels_le.setText("1")
        self._binary_mask_filter_row_layout.addWidget(
            self._binary_mask_channels_le
        )
        self._minimum_colocalization_intensity_ratio_c = QWidget(parent=self)
        self._layout.addWidget(self._minimum_colocalization_intensity_ratio_c)
        self._minimum_colocalization_intensity_ratio_layout = QHBoxLayout()
        self._minimum_colocalization_intensity_ratio_layout.setContentsMargins(
            0, 0, 0, 0
        )
        self._minimum_colocalization_intensity_ratio_c.setLayout(
            self._minimum_colocalization_intensity_ratio_layout
        )
        self._minimum_colocalization_intensity_ratio_l = QLabel(
            "Minimum colocalization intensity ratio",
            parent=self,
        )
        self._minimum_colocalization_intensity_ratio_layout.addWidget(
            self._minimum_colocalization_intensity_ratio_l
        )
        self._minimum_colocalization_intensity_ratio_sb = QDoubleSpinBox(
            parent=self
        )
        self._minimum_colocalization_intensity_ratio_sb.setRange(0.0, 1.0)
        self._minimum_colocalization_intensity_ratio_sb.setSingleStep(0.05)
        self._minimum_colocalization_intensity_ratio_sb.setDecimals(2)
        self._minimum_colocalization_intensity_ratio_sb.setValue(0.25)
        self._minimum_colocalization_intensity_ratio_layout.addWidget(
            self._minimum_colocalization_intensity_ratio_sb
        )
        self._minimum_colocalization_intensity_ratio_layout.addStretch()
        self._binary_mask_filter_ts_toggled()

        self._set_contrasts_b: QPushButton = QPushButton(
            "Set contrasts",
            parent=self,
        )
        self._set_contrasts_b.clicked.connect(
            self._set_contrasts_button_pressed
        )
        self._layout.addWidget(self._set_contrasts_b)

        self._count_foci_b: QPushButton = QPushButton(
            "Count foci",
            parent=self,
        )
        self._count_foci_b.clicked.connect(self._start_fc_button_pressed)
        self._layout.addWidget(self._count_foci_b)

        self._set_regions_b: QPushButton = QPushButton(
            "Set regions",
            parent=self,
        )
        self._layout.addWidget(self._set_regions_b)

        self._plot_path_container = QWidget(parent=self)
        self._plot_path_layout = QVBoxLayout(self._plot_path_container)
        self._plot_path_layout.setContentsMargins(0, 0, 0, 0)
        self._plot_path_layout.setSpacing(6)
        self._plot_path_label = QLabel("Saving plot path:", parent=self)
        self._plot_path_label.setStyleSheet("font-weight: bold")
        self._plot_path_layout.addWidget(self._plot_path_label)

        self._plot_path_row = QWidget(parent=self)
        self._plot_path_row_layout = QHBoxLayout(self._plot_path_row)
        self._plot_path_row_layout.setContentsMargins(0, 0, 0, 0)
        self._plot_path_row_layout.setSpacing(6)
        self._plot_path_le = QLineEdit(parent=self)
        self._plot_path_row_layout.addWidget(self._plot_path_le)
        self._plot_path_select_button = QPushButton("Select dir", parent=self)
        self._plot_path_select_button.clicked.connect(
            self._select_plot_path_button_pressed
        )
        self._plot_path_row_layout.addWidget(self._plot_path_select_button)
        self._plot_path_layout.addWidget(self._plot_path_row)
        self._layout.addWidget(self._plot_path_container)

        helper_separator: QFrame = QFrame(self)
        helper_separator.setFrameShape(QFrame.Shape.HLine)
        helper_separator.setFrameShadow(QFrame.Shadow.Sunken)
        helper_separator.setStyleSheet("background-color: gray;")
        helper_separator.setFixedHeight(2)
        self._layout.addWidget(helper_separator)

        self._helper_widget = QWidget(parent=self)
        self._helper_widget.setObjectName("helper_widget")
        self._helper_widget.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self._helper_widget_layout: QVBoxLayout = QVBoxLayout()
        self._helper_widget_layout.setContentsMargins(0, 0, 0, 0)
        self._helper_widget_layout.setSpacing(0)
        self._helper_widget.setLayout(self._helper_widget_layout)
        self._layout.addWidget(self._helper_widget, 1)

    def _prepare_project_for_contrasts(
        self,
        starting_path: Path,
        channels: list[int],
    ) -> bool:
        try:
            project_path = get_clsp_project_path(starting_path)

            if not create_project_structure(project_path, "clsp"):
                return False

            tiles_path = project_path / TILES_DIR_NAME
            if (
                tiles_path.is_dir()
                and not any(tiles_path.iterdir())
                and not move_tiles(starting_path, project_path)
            ):
                return False

            if not ensure_tiles_config(project_path):
                return False

            tile_paths = extract_project_tiles(project_path, channels)
            if tile_paths is None:
                return False

            self._project_list_widget.refresh_rows()

            stitched_path = project_path / STITCHED_IMAGE_DIR_NAME
            if any(stitched_path.glob("*.ome.zarr")):
                return True

            stitching_succeeded = stitch_ome_zarr_images(
                image_list=tile_paths,
                output_dir=stitched_path,
                **self._stitching_options_widget.get_stitching_options(),
            )
            self._project_list_widget.refresh_rows()
            return stitching_succeeded
        except (OSError, ValueError, RuntimeError) as exc:
            show_warning(f"Could not prepare project {starting_path}:\n{exc}")
            return False

    def _set_contrasts_button_pressed(self) -> None:
        project_paths = self._project_list_widget.get_project_paths()
        if not project_paths:
            return

        if self._keep_channel_ts.isChecked():
            channels = parse_channel_string(self._keep_channel_le.text())
            if not channels:
                show_warning("Enter a valid channel selection.")
                return
        else:
            channels = []

        failed_projects: list[str] = []
        prepared_projects = 0
        for starting_path in project_paths:
            project_prepared = self._prepare_project_for_contrasts(
                starting_path,
                channels,
            )
            self._project_list_widget.refresh_rows()
            if not project_prepared:
                failed_projects.append(str(starting_path))
            else:
                prepared_projects += 1

        if failed_projects:
            show_warning(
                "The following projects were skipped or could not be prepared:\n\n"
                + "\n".join(failed_projects)
            )

        if prepared_projects > 0:
            self._set_contrasts_callback()

    @Slot()
    def _refresh_qlist_on_gui_thread(self) -> None:
        self._project_list_widget.refresh_rows()

    def _clear_helper_widget(self) -> None:
        while self._helper_widget_layout.count():
            q_item = self._helper_widget_layout.takeAt(0)
            q_widget = q_item.widget()
            if q_widget is not None:
                q_widget.setParent(None)
                q_widget.deleteLater()
        self.close_process_control_tile_images()
        self._helper_content_widget = None

    def set_image_path(
        self, image_path: str, image_layer: object | None
    ) -> None:
        _ = image_layer
        self._current_image_path = image_path

    def get_process_control_images_and_paths(
        self,
    ) -> tuple[str, str, list[Image]] | None:
        if (
            self._current_image_path is None
            or self._current_project_files_dir is None
            or len(self._current_stitched_images) == 0
        ):
            return None
        return (
            self._current_image_path,
            self._current_project_files_dir,
            self._current_stitched_images,
        )

    def get_process_control_tiles(self) -> dict[int, str]:
        return self._current_tile_paths

    def open_process_control_tile_images(
        self, tile_index: int
    ) -> list[Image] | None:
        tile_image_path = self._current_tile_paths.get(tile_index)
        if tile_image_path is None:
            return None
        self.close_process_control_tile_images()
        opened_tile_layers = open_tile_image(self._viewer, tile_image_path)
        if opened_tile_layers is None:
            return None
        self._current_tile_image_layers = opened_tile_layers
        return opened_tile_layers

    def close_process_control_tile_images(self) -> None:
        if len(self._current_tile_image_layers) > 0:
            close_image_layers(self._viewer, self._current_tile_image_layers)
            self._current_tile_image_layers = []

    def _get_directory_tile_paths(self, directory_path: str) -> dict[int, str]:
        tile_paths = self._get_ready_tile_paths(directory_path)
        return {
            tile_index: str(tile_path)
            for tile_index, tile_path in enumerate(tile_paths)
        }

    def _build_auto_region_square_csvs(
        self, directory_path: str | Path
    ) -> bool:
        print("")
        print(f"Building auto region square CSVs for {directory_path}")
        tiles_dir = _get_project_tiles_path(directory_path)
        stitched_image_path = Path(get_stitched_output_path(tiles_dir))
        if not stitched_image_path.exists():
            show_warning(
                "Cannot build auto region squares because the stitched image "
                f"does not exist: {stitched_image_path}"
            )
            return False

        project_files_dir = _get_project_files_path(directory_path)
        edited_regions_csv_path = (
            project_files_dir / REGIONS_DIR_NAME / EDITED_REGIONS_FILE_NAME
        )
        print(f"Using stitched image: {stitched_image_path}")
        print(f"Using edited regions file: {edited_regions_csv_path}")
        if not edited_regions_csv_path.exists():
            show_warning(
                "Cannot build auto region squares because the edited regions "
                f"file does not exist: {edited_regions_csv_path}"
            )
            return False

        tile_paths = self._get_ready_tile_paths(directory_path)
        print(f"Found {len(tile_paths)} prepared tiles")
        if len(tile_paths) == 0:
            show_warning(
                "Cannot build auto region squares because no prepared tiles "
                f"were found for {directory_path}"
            )
            return False

        segmentation_paths_by_tile: dict[int, str] = {}
        missing_cleaned_paths: list[str] = []
        for tile_index, tile_path in enumerate(tile_paths):
            segmentation_output_path = _get_segmentation_output_path_for_tile(
                directory_path, tile_path
            )
            cleaned_segmentation_path = get_cleaned_segmentation_output_path(
                segmentation_output_path
            )
            print(
                f"Tile {tile_index + 1}/{len(tile_paths)}: "
                f"raw={segmentation_output_path.exists()} "
                f"cleaned={cleaned_segmentation_path.exists()} "
                f"path={cleaned_segmentation_path}"
            )
            if not cleaned_segmentation_path.exists():
                missing_cleaned_paths.append(str(cleaned_segmentation_path))
                continue
            segmentation_paths_by_tile[tile_index] = str(
                segmentation_output_path
            )

        if missing_cleaned_paths:
            show_warning(
                "Cannot build auto region squares because cleaned "
                "segmentation files are missing.\n\n"
                + "\n".join(missing_cleaned_paths)
            )
            return False

        print(
            f"Building stitched-region squares from "
            f"{len(segmentation_paths_by_tile)} cleaned segmentations"
        )
        (
            region_records_by_index,
            unassigned_records,
        ) = build_region_square_records_from_cleaned_segmentations(
            segmentation_paths_by_tile=segmentation_paths_by_tile,
            stitched_image_path=stitched_image_path,
            edited_regions_csv_path=edited_regions_csv_path,
        )
        region_squares_by_index = {
            region_index: (
                np.asarray(
                    [record["square_yx"] for record in records],
                    dtype=np.float32,
                )
                if len(records) > 0
                else np.empty((0, 4, 2), dtype=np.float32)
            )
            for region_index, records in region_records_by_index.items()
        }
        print(
            f"Built squares for {len(region_squares_by_index)} regions; "
            f"unassigned squares: {len(unassigned_records)}"
        )
        print(
            "Saving region square CSVs to "
            f"{project_files_dir / PICK_NUCLEI_DIR_NAME}"
        )
        save_region_squares_csvs(
            region_squares_by_index=region_squares_by_index,
            pick_nuclei_directory=project_files_dir / PICK_NUCLEI_DIR_NAME,
        )
        save_auto_cut_sbs_files_from_region_records(
            region_records_by_index=region_records_by_index,
            pick_nuclei_directory=project_files_dir / PICK_NUCLEI_DIR_NAME,
            stitched_image_path=stitched_image_path,
        )
        print(
            "Built automatic region square CSVs for "
            f"{directory_path}. Unassigned squares: {len(unassigned_records)}"
        )
        return True

    def _tiles_are_ready(self, directory_path: str | Path) -> bool:
        tile_paths = self._get_ready_tile_paths(directory_path)
        tiles_config_path = (
            _get_project_tiles_path(directory_path) / TILES_CONFIG_FILE_NAME
        )
        config = configparser.ConfigParser()
        try:
            config.read(tiles_config_path)
            expected_count = len(config.items("tiles"))
        except (configparser.Error, OSError, ValueError):
            return False

        return expected_count > 0 and len(tile_paths) >= expected_count

    def _get_ready_tile_paths(self, directory_path: str | Path) -> list[Path]:
        tiles_dir = _get_project_tiles_path(directory_path)
        if not tiles_dir.exists():
            return []
        return sorted(tiles_dir.glob("*.ome.zarr"))

    def _get_project_files_dir_for_directory(
        self, directory_path: str | Path
    ) -> Path:
        return _get_project_files_path(directory_path)

    def _load_sbs_names_for_directory(
        self, directory_path: str | Path
    ) -> list[str]:
        metadata_path = (
            self._get_project_files_dir_for_directory(directory_path)
            / PICK_NUCLEI_DIR_NAME
            / CUT_SBS_DIR_NAME
            / SBS_METADATA_FILE_NAME
        )
        if not metadata_path.exists():
            return []
        metadata_df = pd.read_csv(metadata_path)
        if "sbs_image_name" not in metadata_df.columns:
            return []
        return metadata_df["sbs_image_name"].astype(str).tolist()

    def _region_square_outputs_exist_for_directory(
        self, directory_path: str | Path
    ) -> bool:
        project_files_dir = self._get_project_files_dir_for_directory(
            directory_path
        )
        pick_nuclei_dir = project_files_dir / PICK_NUCLEI_DIR_NAME
        if not pick_nuclei_dir.exists():
            return False
        if not (pick_nuclei_dir / POINTS_SUMMARY_FILE_NAME).exists():
            return False
        regions_configuration_path = (
            project_files_dir
            / REGIONS_DIR_NAME
            / REGIONS_CONFIGURATION_FILE_NAME
        )
        regions_configuration = load_regions_configuration(
            regions_configuration_path
        )
        if regions_configuration is None:
            return False

        _, number_of_regions, _ = regions_configuration
        if number_of_regions is None or number_of_regions <= 0:
            return False
        return all(
            (
                pick_nuclei_dir
                / f"region-{region_index + 1}{SQUARES_FILE_NAME_EXTENSION}"
            ).exists()
            for region_index in range(number_of_regions)
        )

    def _cut_sbs_outputs_exist_for_directory(
        self, directory_path: str | Path
    ) -> bool:
        project_files_dir = self._get_project_files_dir_for_directory(
            directory_path
        )
        cut_sbs_dir = (
            project_files_dir / PICK_NUCLEI_DIR_NAME / CUT_SBS_DIR_NAME
        )
        sbs_names = self._load_sbs_names_for_directory(directory_path)
        if not cut_sbs_dir.exists() or not sbs_names:
            return False
        return all((cut_sbs_dir / sbs_name).exists() for sbs_name in sbs_names)

    def _tile_fc_outputs_exist_for_directory(
        self, directory_path: str | Path
    ) -> bool:
        tile_paths = self._get_ready_tile_paths(directory_path)
        if not tile_paths:
            return False
        auto_count_output_dir = (
            self._get_project_files_dir_for_directory(directory_path)
            / AUTO_COUNT_DIR_NAME
        )
        try:
            colocalization_channels_filter = (
                self._get_colocalization_channels_filter()
            )
        except ValueError:
            return False
        requested_channel_indices = [
            int(channel) - 1 for channel in colocalization_channels_filter
        ]
        return all(
            auto_count_outputs_exist(tile_path, auto_count_output_dir)
            and auto_count_preprocessed_spots_outputs_exist(
                tile_path, auto_count_output_dir
            )
            and auto_count_binary_mask_outputs_exist(
                tile_path,
                auto_count_output_dir,
                requested_channel_indices,
            )
            for tile_path in tile_paths
        )

    def _scored_nuclei_outputs_exist_for_directory(
        self, directory_path: str | Path
    ) -> bool:
        project_files_dir = self._get_project_files_dir_for_directory(
            directory_path
        )
        scored_nuclei_dir = project_files_dir / SCORED_NUCLEI_DIR_NAME
        sbs_names = self._load_sbs_names_for_directory(directory_path)
        if not scored_nuclei_dir.exists() or not sbs_names:
            return False
        for sbs_name in sbs_names:
            scored_points_path, zero_points_path = (
                get_scored_nuclei_output_paths(scored_nuclei_dir, sbs_name)
            )
            if (
                not scored_points_path.exists()
                and not zero_points_path.exists()
            ):
                return False
        return True

    def _foci_summary_exists_for_directory(
        self, directory_path: str | Path
    ) -> bool:
        project_files_dir = self._get_project_files_dir_for_directory(
            directory_path
        )
        return (
            project_files_dir
            / SCORED_NUCLEI_DIR_NAME
            / SCORED_NUCLEI_FOCI_SUMMARY_FILE_NAME
        ).exists()

    def _stitched_image_is_ready(self, directory_path: str | Path) -> bool:
        stitched_directory = Path(directory_path) / STITCHED_IMAGE_DIR_NAME
        return any(stitched_directory.glob("*.ome.zarr"))

    def _start_ns_button_pressed(self) -> None:
        project_paths = self._project_list_widget.get_project_paths()
        if not project_paths:
            return

        invalid_directory_messages: list[str] = []
        ready_project_paths: list[Path] = []
        stitching_projects: list[tuple[Path, list[Path]]] = []

        for directory_path in project_paths:
            try:
                project_directory = get_clsp_project_path(Path(directory_path))
                if not create_project_structure(project_directory, "clsp"):
                    invalid_directory_messages.append(
                        f"Could not create project structure for "
                        f"{directory_path}"
                    )
                    continue
            except (OSError, ValueError) as exc:
                invalid_directory_messages.append(str(exc))
                continue

            starting_path = Path(directory_path)
            project_path = project_directory
            tiles_path = project_path / TILES_DIR_NAME
            if (
                tiles_path.is_dir()
                and not any(tiles_path.iterdir())
                and not move_tiles(starting_path, project_path)
            ):
                invalid_directory_messages.append(
                    f"Could not move tiles into {tiles_path} "
                    f"for {directory_path}"
                )
                continue

            if not ensure_tiles_config(project_path):
                invalid_directory_messages.append(
                    f"Could not create or read tiles.config in {tiles_path}"
                )
                continue

            if self._keep_channel_ts.isChecked():
                channels = parse_channel_string(self._keep_channel_le.text())
                if not channels:
                    invalid_directory_messages.append(
                        f"Invalid channel selection for {directory_path}"
                    )
                    continue
            else:
                channels = []

            created_tile_paths = extract_project_tiles(
                project_path,
                channels,
            )
            if created_tile_paths is None:
                invalid_directory_messages.append(
                    f"Could not prepare tiles for {directory_path}"
                )
                continue

            if not self._tiles_are_ready(project_path):
                invalid_directory_messages.append(
                    "Not all expected tiles exist for "
                    f"{directory_path} after tile preparation"
                )
                continue

            if self._tiles_are_ready(project_path):
                ready_project_paths.append(project_path)
                if self._stitched_image_is_ready(project_path):
                    print(
                        f"Stitched image already exists for {directory_path}; skipping stitching"
                    )
                    continue
                stitching_projects.append((project_path, created_tile_paths))

        if invalid_directory_messages:
            invalid_directory_text = "\n\n".join(invalid_directory_messages)
            show_warning(
                f"{len(invalid_directory_messages)} directories failed:\n\n"
                f"{invalid_directory_text}"
            )
            return

        for project_path, tile_paths in stitching_projects:
            stitched_ok = stitch_ome_zarr_images(
                image_list=tile_paths,
                output_dir=project_path / STITCHED_IMAGE_DIR_NAME,
                **self._stitching_options_widget.get_stitching_options(),
            )
            if not stitched_ok:
                return
        if self._run_all_ts.isChecked():
            for project_path in ready_project_paths:
                self._call_segmentation(project_path)

        self._project_list_widget.refresh_rows()

    def _get_project_status_ready(
        self, directory_path: str | Path
    ) -> tuple[bool, bool, bool]:
        tile_paths = self._get_ready_tile_paths(directory_path)

        segmentation_ready = (
            self._tiles_are_ready(directory_path)
            and self._stitched_image_is_ready(directory_path)
            and len(tile_paths) > 0
            and all(
                (
                    segmentation_path := _get_segmentation_output_path_for_tile(
                        directory_path,
                        tile_path,
                    )
                ).exists()
                and get_cleaned_segmentation_output_path(
                    segmentation_path
                ).exists()
                for tile_path in tile_paths
            )
        )

        regions_ready = self._regions_are_complete(directory_path)

        contrasts_ready = len(tile_paths) > 0 and all(
            bool(load_tile_contrasts(tile_path)) for tile_path in tile_paths
        )

        return segmentation_ready, regions_ready, contrasts_ready

    def _start_fc_button_pressed(self) -> None:
        if self._batch_fc_running:
            print("Run batch FC is already running")
            return
        plot_directory = Path(self._plot_path_le.text().strip())
        if not plot_directory.is_dir():
            show_warning("Select a valid directory for the foci-count plot.")
            return
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        plot_path = plot_directory / f"foci_count_plot_{timestamp}.pdf"
        if plot_path.exists():
            show_warning(f"Plot file already exists: {plot_path}")
            return
        try:
            colocalization_channels_filter = (
                self._get_colocalization_channels_filter()
            )
        except ValueError as exc:
            show_warning(str(exc))
            return
        minimum_colocalization_intensity_ratio = float(
            self._minimum_colocalization_intensity_ratio_sb.value()
        )

        invalid_directories: list[str] = []
        directory_paths = self._project_list_widget.get_project_paths()

        for directory_path in directory_paths:
            ns_ready, re_ready, co_ready = self._get_project_status_ready(
                directory_path
            )
            if not (ns_ready and re_ready and co_ready):
                invalid_states: list[str] = []
                if not ns_ready:
                    invalid_states.append("NS")
                if not re_ready:
                    invalid_states.append("RE")
                if not co_ready:
                    invalid_states.append("CO")
                invalid_directories.append(
                    f"{Path(directory_path).name}: missing {', '.join(invalid_states)}"
                )

        if invalid_directories:
            show_warning(
                "Run batch FC stopped.\n\n"
                "The following directories are not ready:\n\n"
                + "\n".join(invalid_directories)
            )
            return

        self._batch_fc_running = True
        directory_paths = [str(path) for path in directory_paths]
        plot_gonad_entries = [
            (
                str(_get_project_path(directory_path)),
                Path(directory_path).parent.name,
            )
            for directory_path in directory_paths
        ]
        print(f"Run batch FC started for {len(directory_paths)} directories")
        worker = threading.Thread(
            target=self._run_batch_fc_worker,
            args=(
                directory_paths,
                plot_gonad_entries,
                colocalization_channels_filter,
                minimum_colocalization_intensity_ratio,
                plot_path,
            ),
            daemon=True,
        )
        worker.start()

    def _run_batch_fc_worker(
        self,
        directory_paths: list[str],
        plot_gonad_entries: list[tuple[str, str]],
        colocalization_channels_filter: list[str],
        minimum_colocalization_intensity_ratio: float,
        plot_path: Path,
    ) -> None:
        try:
            for directory_index, directory_path in enumerate(
                directory_paths, start=1
            ):
                print("")
                print(
                    "Run batch FC "
                    f"[{directory_index}/{len(directory_paths)}] "
                    f"starting {directory_path}"
                )
                tile_paths = self._get_ready_tile_paths(directory_path)
                project_files_dir = _get_project_files_path(directory_path)
                edited_regions_csv_path = (
                    project_files_dir
                    / REGIONS_DIR_NAME
                    / EDITED_REGIONS_FILE_NAME
                )
                stitched_image_path = Path(
                    get_stitched_output_path(
                        _get_project_tiles_path(directory_path)
                    )
                )
                need_region_stage = (
                    not self._region_square_outputs_exist_for_directory(
                        directory_path
                    )
                    or not self._cut_sbs_outputs_exist_for_directory(
                        directory_path
                    )
                )
                need_tile_fc_stage = (
                    not self._tile_fc_outputs_exist_for_directory(
                        directory_path
                    )
                )
                need_scored_stage = (
                    not self._scored_nuclei_outputs_exist_for_directory(
                        directory_path
                    )
                )
                need_summary_stage = (
                    not self._foci_summary_exists_for_directory(directory_path)
                )

                if need_region_stage:
                    self._build_auto_region_square_csvs(directory_path)
                else:
                    print(
                        "FC stage skip: region squares and cut SBS already exist for "
                        f"{directory_path}"
                    )

                if need_tile_fc_stage:
                    self._run_auto_tile_foci_count_for_directory(
                        directory_path,
                        colocalization_channels_filter,
                        minimum_colocalization_intensity_ratio,
                    )
                else:
                    print(
                        "FC stage skip: tile FC outputs already exist for "
                        f"{directory_path}"
                    )

                if need_scored_stage:
                    (
                        region_records_by_index,
                        _unassigned_records,
                    ) = build_region_square_records_from_cleaned_segmentations(
                        segmentation_paths_by_tile={
                            tile_index: str(
                                _get_segmentation_output_path_for_tile(
                                    directory_path, tile_path
                                )
                            )
                            for tile_index, tile_path in enumerate(tile_paths)
                        },
                        stitched_image_path=stitched_image_path,
                        edited_regions_csv_path=edited_regions_csv_path,
                    )
                    save_auto_scored_nuclei_files_from_region_records(
                        region_records_by_index=region_records_by_index,
                        directory_path=directory_path,
                        tile_paths=tile_paths,
                        stitched_image_path=stitched_image_path,
                    )
                else:
                    print(
                        "FC stage skip: scored nuclei outputs already exist for "
                        f"{directory_path}"
                    )

                if need_summary_stage:
                    generate_scored_nuclei_foci_summary(
                        str(_get_project_path(directory_path))
                    )
                else:
                    print(
                        "FC stage skip: scored nuclei foci summary already exists for "
                        f"{directory_path}"
                    )
                print(
                    "Run batch FC "
                    f"[{directory_index}/{len(directory_paths)}] "
                    f"finished {directory_path}"
                )
            generate_foci_count_plot_pdf(
                plot_gonad_entries,
                plot_path,
            )
            print(f"Foci-count plot saved: {plot_path}")
        except (OSError, ValueError, RuntimeError) as exc:
            print(f"Run batch FC failed: {exc}")
        finally:
            self._batch_fc_running = False
            print("Run batch FC finished")
            QMetaObject.invokeMethod(
                self,
                "_refresh_qlist_on_gui_thread",
                Qt.ConnectionType.QueuedConnection,
            )

    def _keep_ts_toggled(self) -> None:
        self._keep_channel_le.setEnabled(self._keep_channel_ts.isChecked())

    def _select_plot_path_button_pressed(self) -> None:
        selected_directory = get_directory(
            self,
            "Select plot saving directory",
        )
        if selected_directory is not None:
            self._plot_path_le.setText(selected_directory)

    def _binary_mask_filter_ts_toggled(self) -> None:
        enabled = self._binary_mask_filter_ts.isChecked()
        self._binary_mask_channels_le.setEnabled(enabled)
        self._binary_mask_filter_l.setEnabled(enabled)
        self._minimum_colocalization_intensity_ratio_l.setEnabled(enabled)
        self._minimum_colocalization_intensity_ratio_sb.setEnabled(enabled)

    def _get_colocalization_channels_filter(self) -> list[str]:
        if not self._binary_mask_filter_ts.isChecked():
            return []
        channels_raw = parse_channel_string(
            self._binary_mask_channels_le.text()
        )
        if not channels_raw:
            raise ValueError(
                "Binary mask filtering is enabled but no valid channels were provided."
            )
        positive_channels = [
            channel for channel in channels_raw if channel > 0
        ]
        if len(positive_channels) <= 0:
            raise ValueError(
                "Binary mask filtering requires channel numbers greater than 0."
            )
        return [str(channel) for channel in positive_channels]

    def _use_gpu_ts_toggled(self) -> None:
        if not self._stitching_options_widget.is_gpu_enabled():
            return

        if importlib.util.find_spec("cupy") is None:
            show_warning(
                "CuPy is not installed in the current environment. "
                "GPU stitching has been disabled."
            )
            self._stitching_options_widget.set_gpu_enabled(False)
            return

        try:
            import cupy
        except (ImportError, OSError) as exc:
            show_warning(
                f"GPU stitching is not available in this environment: {exc}"
            )
            self._stitching_options_widget.set_gpu_enabled(False)
            return

        try:
            if cupy.cuda.runtime.getDeviceCount() < 1:
                show_warning(
                    "No CUDA-capable GPU was detected. GPU stitching has been disabled."
                )
                self._stitching_options_widget.set_gpu_enabled(False)
        except cupy.cuda.runtime.CUDARuntimeError as exc:
            show_warning(
                f"GPU stitching is not available in this environment: {exc}"
            )
            self._stitching_options_widget.set_gpu_enabled(False)

    def _call_segmentation(self, directory_path: str | Path) -> None:
        tile_paths = self._get_ready_tile_paths(directory_path)
        if not tile_paths:
            print(
                f"No prepared tiles found for segmentation in {directory_path}"
            )
            return

        segmentation_output_dir = (
            _get_project_files_path(directory_path) / SEGMENTATION_DIR_NAME
        )
        total_tiles = len(tile_paths)
        print(
            f"Starting segmentation for {total_tiles} tiles in {directory_path}"
        )
        for tile_index, tile_path in enumerate(tile_paths, start=1):
            print(
                f"Starting segmentation for tile {tile_index}/{total_tiles}: {tile_path}"
            )
            segmentation_output_path = segmentation_output_dir / (
                f"{tile_path.name[: -len('.ome.zarr')]}_meiotic_3d_crops_masks.npy"
            )
            if segmentation_output_path.exists():
                print(
                    "Segmentation output already exists for "
                    f"{tile_path}; skipping segmentation"
                )
            else:
                run_segmentation_subprocess(
                    image_path=tile_path,
                    model_name="meiotic_3d_crops",
                    output_dir=segmentation_output_dir,
                )
            cleaned_segmentation_output_path = (
                get_cleaned_segmentation_output_path(segmentation_output_path)
            )
            if cleaned_segmentation_output_path.exists():
                print(
                    "Cleaned segmentation output already exists for "
                    f"{tile_path}; skipping cleaning"
                )
            else:
                clean_segmentation_file(segmentation_output_path)
            print(
                f"Finished segmentation for tile {tile_index}/{total_tiles}: {tile_path}"
            )
        print(
            f"Finished segmentation for all {total_tiles} tiles in {directory_path}"
        )

    def _call_automatic_foci_count(
        self,
        image_path: str | Path,
        segmentation_path: str | Path,
        normalization_input_min: float,
        normalization_input_max: float,
        colocalization_channels_filter: list[str],
        minimum_colocalization_intensity_ratio: float,
    ) -> None:
        auto_count_output_dir = (
            Path(segmentation_path).parent.parent / AUTO_COUNT_DIR_NAME
        )
        if auto_count_outputs_exist(image_path, auto_count_output_dir):
            print(
                "Automatic foci count outputs already exist for "
                f"{image_path}; skipping"
            )
            return

        print(f"Starting automatic foci counting for {image_path}")
        print(f"Using Spotiflow model name: {self._spotiflow_model_name}")
        (
            ref_image_zyx,
            segmentation_arr,
            spacing,
            processed_spots_image,
            preprocessing_stats,
            spots_coords,
            processed_image_path,
            preprocessing_stats_path,
            points_layer_path,
        ) = run_auto_count_on_paths(
            image_path=image_path,
            segmentation_path=segmentation_path,
            output_dir=auto_count_output_dir,
            use_gpu=self._stitching_options_widget.is_gpu_enabled(),
            model_name=self._spotiflow_model_name,
            colocalization_channels_filter=colocalization_channels_filter,
            minimum_colocalization_intensity_ratio=(
                minimum_colocalization_intensity_ratio
            ),
            normalize_spots_channel=True,
            normalization_input_min=normalization_input_min,
            normalization_input_max=normalization_input_max,
            normalization_output_max=1000,
        )
        print(
            f"Automatic foci count reference image shape: {ref_image_zyx.shape}"
        )
        print(
            f"Automatic foci count segmentation shape: {segmentation_arr.shape}"
        )
        print(f"Automatic foci count spacing: {spacing}")
        print(
            "Automatic foci count processed spots image shape: "
            f"{processed_spots_image.shape}"
        )
        print(
            f"Automatic foci count preprocessing stats: {preprocessing_stats}"
        )
        print(f"Automatic foci count detected {len(spots_coords)} spots")
        print(
            "Automatic foci count outputs saved to: "
            f"{processed_image_path}, {preprocessing_stats_path}, "
            f"and {points_layer_path}"
        )

    def _run_auto_tile_foci_count_for_directory(
        self,
        directory_path: str | Path,
        colocalization_channels_filter: list[str],
        minimum_colocalization_intensity_ratio: float,
    ) -> None:
        tile_paths = self._get_ready_tile_paths(directory_path)
        if not tile_paths:
            print(f"No prepared tiles found for auto FC in {directory_path}")
            return

        segmentation_paths: list[Path] = []
        pending_tile_paths: list[Path] = []
        for tile_path in tile_paths:
            segmentation_output_path = _get_segmentation_output_path_for_tile(
                directory_path, tile_path
            )
            if not segmentation_output_path.exists():
                print(
                    "Skipping tile FC because segmentation is missing for "
                    f"{tile_path}"
                )
                continue
            auto_count_output_dir = (
                segmentation_output_path.parent.parent / AUTO_COUNT_DIR_NAME
            )
            if auto_count_outputs_exist(tile_path, auto_count_output_dir):
                print(
                    "Automatic foci count outputs already exist for "
                    f"{tile_path}; skipping tile FC"
                )
                continue
            pending_tile_paths.append(tile_path)
            segmentation_paths.append(segmentation_output_path)

        if not pending_tile_paths:
            print(
                f"All tile FC outputs already exist for {directory_path}; skipping"
            )
            return

        normalization_input_min, normalization_input_max = (
            compute_shared_masked_normalization_bounds(
                image_paths=pending_tile_paths,
                segmentation_paths=segmentation_paths,
            )
        )
        print(
            "Automatic foci count shared normalization bounds: "
            f"min={normalization_input_min}, max={normalization_input_max}"
        )
        for tile_path, segmentation_output_path in zip(
            pending_tile_paths, segmentation_paths, strict=True
        ):
            self._call_automatic_foci_count(
                tile_path,
                segmentation_output_path,
                normalization_input_min=normalization_input_min,
                normalization_input_max=normalization_input_max,
                colocalization_channels_filter=colocalization_channels_filter,
                minimum_colocalization_intensity_ratio=(
                    minimum_colocalization_intensity_ratio
                ),
            )
