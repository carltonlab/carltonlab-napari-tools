from __future__ import annotations

import configparser
import csv
import importlib
import json
from collections.abc import Callable, Generator
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd
from matplotlib.path import Path as MplPath
from multiview_stitcher import ngff_utils
from napari.layers import Image
from napari.qt.threading import thread_worker
from napari.utils.notifications import show_warning
from numpy.typing import NDArray
from qtpy.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)
from tifffile import imwrite

from carltonlab_napari_tools._model_directories import (
    ModelDirectoriesManager,
)
from carltonlab_napari_tools._model_download import (
    get_bioimageio_weight_path,
    is_bioimageio_weight_available,
)
from carltonlab_napari_tools._shared_variables import (
    AUTO_COUNT_DIR_NAME,
    CELLPOSE_MODEL_NAME,
    CUT_SBS_DIR_NAME,
    EXTRACTED_CHANNELS_FILE_NAME,
    NUCLEI_POINTS_FEATURES_TABLE_FILE_NAME,
    NUCLEI_POINTS_LAYER_FILE_NAME,
    PICK_NUCLEI_DIR_NAME,
    PROJECT_FILE_DIR_NAME,
    SBS_FILE_NAME_EXTENSION,
    SBS_METADATA_FILE_NAME,
    SCORED_NUCLEI_DIR_NAME,
    SCORED_NUCLEI_POINTS_FILE_NAME_EXTENSION,
    SEGMENTATION_DIR_NAME,
    SEGMENTATION_MASKS_FILE_NAME_SUFFIX,
    SEGMENTATION_OUTPUT_NAME,
    STITCHED_IMAGE_DIR_NAME,
    TILES_CONFIG_FILE_NAME,
    TILES_DIR_NAME,
)
from carltonlab_napari_tools._shared_widgets import KeepChannelsWidget
from carltonlab_napari_tools._tile_utils import (
    ensure_tiles_config,
    get_extracted_tile_path,
    get_tile_positions_path,
    load_tile_contrasts,
    move_tiles,
)
from carltonlab_napari_tools._utils import (
    create_project_structure,
    get_clsp_project_path,
    get_project_stitched_image_path,
    is_supported_image_entry,
    parse_channel_string,
    resolve_clsp_project_path,
)
from carltonlab_napari_tools.automatic_foci_count._auto_foci_count import (
    auto_count_binary_mask_outputs_exist,
    auto_count_outputs_exist,
    auto_count_preprocessed_spots_outputs_exist,
    compute_shared_masked_normalization_bounds,
    get_auto_count_output_paths,
    run_auto_count_on_paths,
    run_auto_count_preprocessed_spots_on_paths,
    save_points_csv_for_napari,
)
from carltonlab_napari_tools.automatic_foci_count._auto_settings import (
    AutoFociCountSettings,
    AutoFociCountSettingsManager,
)
from carltonlab_napari_tools.automatic_foci_count._nuclei_features import (
    build_nucleus_candidates,
    deduplicate_nucleus_candidates,
    save_nucleus_features_and_points,
)
from carltonlab_napari_tools.channel_extraction import extract_project_tiles
from carltonlab_napari_tools.foci_count_widgets._sbs_flags_manager import (
    SBSFlag,
    SBSFlagsManager,
)
from carltonlab_napari_tools.general_widgets._project_list_widget import (
    CLTProjectListWidget,
)
from carltonlab_napari_tools.image_processing import (
    crop_sbs_data,
    get_sbs_crop_bounds,
)
from carltonlab_napari_tools.image_resolver import resolve_lazy_image_data
from carltonlab_napari_tools.image_stitching import (
    get_stitched_coordinates_path,
    stitch_ome_zarr_images,
)
from carltonlab_napari_tools.segmentation import (
    clean_segmentation_file,
    get_cleaned_segmentation_output_path,
    load_segmentation_npy,
    run_segmentation_batch_subprocess,
    run_spotiflow_batch_subprocess,
)

if TYPE_CHECKING:
    from napari.components import ViewerModel


@dataclass(frozen=True)
class ContrastPreparationUpdate:
    """One background-preparation update for one project."""

    project_path: Path
    project_index: int
    project_total: int
    stage: str
    error: str | None = None


@dataclass(frozen=True)
class FociCountUpdate:
    """One background foci-counting update for one project."""

    project_path: Path
    project_index: int
    project_total: int
    stage: str
    error: str | None = None


@thread_worker
def _prepare_contrasts_worker(
    project_paths: list[Path],
    channels: list[int],
    stitching_options: dict[str, int | bool | None],
) -> Generator[ContrastPreparationUpdate, None, list[Path]]:
    prepared_projects: list[Path] = []

    for project_index, starting_path in enumerate(project_paths, start=1):
        project_path = get_clsp_project_path(starting_path)

        try:
            yield ContrastPreparationUpdate(
                project_path,
                project_index,
                len(project_paths),
                "Creating project structure",
            )
            create_project_structure(project_path, "clsp")

            tiles_path = project_path / TILES_DIR_NAME
            if tiles_path.is_dir() and not any(tiles_path.iterdir()):
                yield ContrastPreparationUpdate(
                    project_path,
                    project_index,
                    len(project_paths),
                    "Moving tiles",
                )
                if not move_tiles(starting_path, project_path):
                    raise RuntimeError(
                        "Could not move tiles into the project."
                    )

            yield ContrastPreparationUpdate(
                project_path,
                project_index,
                len(project_paths),
                "Checking tile configuration",
            )
            if not ensure_tiles_config(project_path):
                raise RuntimeError("Could not create tiles.config.")

            yield ContrastPreparationUpdate(
                project_path,
                project_index,
                len(project_paths),
                "Extracting channels",
            )
            tile_paths = extract_project_tiles(project_path, channels)

            stitched_path = project_path / STITCHED_IMAGE_DIR_NAME
            if any(stitched_path.glob("*.ome.zarr")):
                prepared_projects.append(project_path)
                yield ContrastPreparationUpdate(
                    project_path,
                    project_index,
                    len(project_paths),
                    "Stitched image already exists",
                )
                continue

            yield ContrastPreparationUpdate(
                project_path,
                project_index,
                len(project_paths),
                "Stitching images",
            )
            stitch_ome_zarr_images(
                image_list=tile_paths,
                output_dir=stitched_path,
                **stitching_options,
            )
        except (OSError, RuntimeError, ValueError) as exc:
            yield ContrastPreparationUpdate(
                project_path,
                project_index,
                len(project_paths),
                "Failed",
                error=str(exc),
            )
            continue

        prepared_projects.append(project_path)
        yield ContrastPreparationUpdate(
            project_path,
            project_index,
            len(project_paths),
            "Ready",
        )

    return prepared_projects


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
    tiles_directory: str | Path,
    tile_path: str | Path,
) -> tuple[float, float, float]:
    tile_positions_path = get_tile_positions_path(
        Path(stitched_image_path),
        Path(tiles_directory),
    )
    if not tile_positions_path.exists():
        raise FileNotFoundError(
            f"Tile positions file not found: {tile_positions_path}"
        )

    with tile_positions_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        row = next(
            (
                dict(candidate)
                for candidate in reader
                if Path(candidate.get("tile_name", "")).name
                == Path(tile_path).name
            ),
            None,
        )

    if row is None:
        raise ValueError(
            f"Tile {Path(tile_path).name!r} is missing from "
            f"{tile_positions_path}"
        )

    z_offset = float((row.get("z_min_px_index") or "0").strip())
    y_offset = float((row.get("y_min_px_index") or "0").strip())
    x_offset = float((row.get("x_min_px_index") or "0").strip())
    return z_offset, y_offset, x_offset


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
    tiles_directory: str | Path,
    tile_path: str | Path,
) -> NDArray[np.float32]:
    points = np.asarray(tile_local_points_zyx, dtype=np.float32)
    if points.ndim != 2 or points.shape[1] != 3:
        raise ValueError(
            f"Expected tile-local points with shape (N, 3), got {points.shape}"
        )
    if len(points) == 0:
        return np.empty((0, 3), dtype=np.float32)

    offsets_zyx = get_tile_stitched_pixel_offsets(
        stitched_image_path,
        tiles_directory,
        tile_path,
    )
    return points + np.asarray(offsets_zyx, dtype=np.float32)


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
    tiles_directory: str | Path,
    tile_path: str | Path,
) -> NDArray[np.float32]:
    squares = np.asarray(tile_local_squares_yx, dtype=np.float32)
    if squares.ndim != 3 or squares.shape[1:] != (4, 2):
        raise ValueError(
            "Expected square polygons with shape (N, 4, 2), "
            f"got {squares.shape}"
        )
    if len(squares) == 0:
        return np.empty((0, 4, 2), dtype=np.float32)

    _z_offset, y_offset, x_offset = get_tile_stitched_pixel_offsets(
        stitched_image_path,
        tiles_directory,
        tile_path,
    )
    offset_yx = np.asarray([y_offset, x_offset], dtype=np.float32)
    return squares + offset_yx


def map_tile_local_square_records_to_stitched_image(
    square_records: list[dict[str, object]],
    stitched_image_path: str | Path,
    tiles_directory: str | Path,
    tile_index: int,
    tile_path: str | Path,
) -> list[dict[str, object]]:
    if len(square_records) == 0:
        return []
    z_offset, y_offset, x_offset = get_tile_stitched_pixel_offsets(
        stitched_image_path,
        tiles_directory,
        tile_path,
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
                "z1": int(record["z1"]) + int(z_offset),
                "z2": int(record["z2"]) + int(z_offset),
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
    tiles_directory: str | Path,
    edited_regions_csv_path: str | Path,
) -> tuple[dict[int, NDArray[np.float32]], NDArray[np.float32]]:
    region_records_by_index, unassigned_records = (
        build_region_square_records_from_cleaned_segmentations(
            segmentation_paths_by_tile=segmentation_paths_by_tile,
            stitched_image_path=stitched_image_path,
            tiles_directory=tiles_directory,
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
    tile_paths_by_tile: dict[int, str | Path],
    stitched_image_path: str | Path,
    tiles_directory: str | Path,
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
                tiles_directory=tiles_directory,
                tile_index=tile_index,
                tile_path=tile_paths_by_tile[tile_index],
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


def save_auto_scored_nuclei_files_from_features(
    project_path: Path,
    tile_paths: list[Path],
    stitched_image_path: Path,
) -> bool:
    project_files_path = project_path / PROJECT_FILE_DIR_NAME
    pick_nuclei_path = project_files_path / PICK_NUCLEI_DIR_NAME
    features_path = pick_nuclei_path / NUCLEI_POINTS_FEATURES_TABLE_FILE_NAME
    if not features_path.exists():
        raise FileNotFoundError(
            f"Nuclei features table not found: {features_path}"
        )

    features = pd.read_csv(features_path)
    stitched_data = resolve_lazy_image_data(stitched_image_path)
    if stitched_data is None:
        raise ValueError(
            f"Could not load stitched image: {stitched_image_path}"
        )

    required_columns = {
        "sbs_number",
        "source_tile_index",
        "source_label_id",
    }
    missing_columns = required_columns.difference(features.columns)
    if missing_columns:
        raise ValueError(
            "Automatic nuclei features table is missing source columns: "
            f"{sorted(missing_columns)}"
        )

    auto_count_output_dir = project_files_path / AUTO_COUNT_DIR_NAME
    filtered_points_by_tile: dict[int, NDArray[np.float32]] = {}
    labels_by_tile: dict[int, NDArray[np.uint32]] = {}
    scored_nuclei_path = project_files_path / SCORED_NUCLEI_DIR_NAME
    scored_nuclei_path.mkdir(parents=True, exist_ok=True)
    project_name = project_path.name.removesuffix("_clsp_project")

    for feature_index, feature in features.iterrows():
        sbs_number = int(feature["sbs_number"])
        tile_index = int(feature["source_tile_index"])
        label_id = int(feature["source_label_id"])
        if not 0 <= tile_index < len(tile_paths):
            raise ValueError(
                f"SBS {sbs_number} has invalid source tile index: {tile_index}"
            )

        tile_path = tile_paths[tile_index]
        if tile_index not in filtered_points_by_tile:
            _, _, filtered_points_path = get_auto_count_output_paths(
                tile_path,
                auto_count_output_dir,
            )
            filtered_points_by_tile[tile_index] = (
                load_napari_points_csv(filtered_points_path)
                if filtered_points_path.exists()
                else np.empty((0, 3), dtype=np.float32)
            )
        if tile_index not in labels_by_tile:
            segmentation_path = _get_segmentation_output_path_for_tile(
                project_path,
                tile_path,
            )
            labels_by_tile[tile_index] = load_cleaned_segmentation_labels(
                segmentation_path
            )

        label_points, rejected_label_points = (
            filter_points_inside_label_with_rejections(
                filtered_points_by_tile[tile_index],
                labels_by_tile[tile_index],
                label_id,
            )
        )
        stitched_label_points = map_tile_local_points_to_stitched_image(
            label_points,
            stitched_image_path=stitched_image_path,
            tiles_directory=project_path / TILES_DIR_NAME,
            tile_path=tile_path,
        )
        feature_data = feature.to_dict()
        crop_bounds = get_sbs_crop_bounds(feature_data, stitched_data)
        if crop_bounds is None:
            raise ValueError(
                f"Could not make crop bounds for SBS {sbs_number}"
            )

        inside_crop = (
            (stitched_label_points[:, 0] >= crop_bounds.z_start)
            & (stitched_label_points[:, 0] < crop_bounds.z_stop)
            & (stitched_label_points[:, 1] >= crop_bounds.y_start)
            & (stitched_label_points[:, 1] < crop_bounds.y_stop)
            & (stitched_label_points[:, 2] >= crop_bounds.x_start)
            & (stitched_label_points[:, 2] < crop_bounds.x_stop)
        )
        kept_stitched_points = stitched_label_points[inside_crop]
        rejected_crop_points = stitched_label_points[~inside_crop]
        local_points = kept_stitched_points.copy()
        local_points[:, 0] -= crop_bounds.z_start
        local_points[:, 1] -= crop_bounds.y_start
        local_points[:, 2] -= crop_bounds.x_start

        sbs_name = f"{project_name}_sbs{sbs_number}{SBS_FILE_NAME_EXTENSION}"
        points_path, zero_points_path = get_scored_nuclei_output_paths(
            scored_nuclei_path,
            sbs_name,
        )
        sbs_stem = sbs_name[: -len(SBS_FILE_NAME_EXTENSION)]
        save_points_csv_for_napari(
            scored_nuclei_path
            / f"{sbs_stem}_rejected_cellpose_label_points.csv",
            rejected_label_points,
        )
        save_points_csv_for_napari(
            scored_nuclei_path / f"{sbs_stem}_rejected_sbs_crop_points.csv",
            rejected_crop_points,
        )

        if len(local_points) == 0:
            points_path.unlink(missing_ok=True)
            zero_points_path.write_text("", encoding="utf-8")
        else:
            zero_points_path.unlink(missing_ok=True)
            save_points_csv_for_napari(points_path, local_points)

        features.loc[feature_index, "scored_foci_number"] = len(local_points)
        features.loc[feature_index, "stitched_foci_coords"] = json.dumps(
            kept_stitched_points.tolist()
        )

    features.to_csv(features_path, index=False)
    return True


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
                tiles_directory=_get_project_tiles_path(directory_path),
                tile_path=tile_paths[tile_index],
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
        f"{tile_path_obj.name[: -len('.ome.zarr')]}"
        f"{SEGMENTATION_MASKS_FILE_NAME_SUFFIX}"
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
        keep_channels_widget: KeepChannelsWidget,
        set_contrasts_callback: Callable[[], None],
        set_regions_callback: Callable[[], None],
        generate_plots_callback: Callable[[], None],
        model_directories_callback: Callable[[], None],
        settings_callback: Callable[[], None],
        status_update_callback: Callable[[], None],
    ):
        super().__init__(parent=parent)
        self._viewer: ViewerModel = viewer
        self._parent: QWidget = parent
        self._project_list_widget = project_list_widget
        self._keep_channels_widget = keep_channels_widget
        self._set_contrasts_callback = set_contrasts_callback
        self._set_regions_callback = set_regions_callback
        self._generate_plots_callback = generate_plots_callback
        self._model_directories_callback = model_directories_callback
        self._settings_callback = settings_callback
        self._status_update_callback = status_update_callback
        ModelDirectoriesManager().ensure_default_configuration()
        self._settings_manager = AutoFociCountSettingsManager()
        self._settings = self._settings_manager.load()

        self._helper_widget: QWidget
        self._helper_widget_layout: QVBoxLayout
        self._helper_content_widget: QWidget | None = None
        self._current_project_files_dir: str | None = None
        self._current_image_path: str | None = None
        self._current_stitched_images: list[Image] = []
        self._current_tile_paths: dict[int, str] = {}
        self._current_tile_image_layers: list[Image] = []
        self._automatic_workflow_active = False
        self._contrast_preparation_worker = None
        self._contrast_failures: list[str] = []
        self._foci_count_worker = None
        self._foci_count_failures: list[str] = []
        self._spotiflow_model_name = "synth_3d"

        self._layout: QVBoxLayout = QVBoxLayout()
        self._layout.setContentsMargins(2, 2, 2, 2)
        self.setLayout(self._layout)
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )

        self._settings_row = QWidget(parent=self)
        self._settings_row_layout = QHBoxLayout()
        self._settings_row_layout.setContentsMargins(0, 0, 0, 0)
        self._settings_row.setLayout(self._settings_row_layout)
        self._settings_status_lb = QLabel(parent=self)
        self._settings_status_lb.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Preferred,
        )
        self._settings_row_layout.addWidget(self._settings_status_lb)
        self._edit_settings_button = QPushButton("Edit settings", parent=self)
        self._edit_settings_button.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Preferred,
        )
        self._edit_settings_button.clicked.connect(self._settings_callback)
        self._settings_row_layout.addWidget(self._edit_settings_button)
        self._layout.addWidget(self._settings_row)
        self._update_settings_status()

        self._edit_model_directories_b = QPushButton(
            "Edit/download model",
            parent=self,
        )
        self._edit_model_directories_b.clicked.connect(
            self._model_directories_callback
        )
        self._model_status_row = QWidget(parent=self)
        self._model_status_row_layout = QHBoxLayout()
        self._model_status_row_layout.setContentsMargins(0, 0, 0, 0)
        self._model_status_row.setLayout(self._model_status_row_layout)
        self._layout.addWidget(self._model_status_row)

        self._cellpose_model_status_lb = QLabel(parent=self)
        self._cellpose_model_status_lb.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Preferred,
        )
        self._model_status_row_layout.addWidget(self._cellpose_model_status_lb)
        self._edit_model_directories_b.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Preferred,
        )
        self._model_status_row_layout.addWidget(self._edit_model_directories_b)
        self._update_cellpose_model_status()

        self._steps_l = QLabel("Steps:", parent=self)
        self._steps_l.setStyleSheet("font-weight: bold")
        self._layout.addSpacing(6)
        self._layout.addWidget(self._steps_l)

        self._set_contrasts_b: QPushButton = QPushButton(
            "1. Set contrasts",
            parent=self,
        )
        self._set_contrasts_b.clicked.connect(
            self._set_contrasts_button_pressed
        )
        self._layout.addWidget(self._set_contrasts_b)

        self._contrast_status_lb = QLabel(parent=self)
        self._contrast_status_lb.setWordWrap(True)
        self._layout.addWidget(self._contrast_status_lb)

        self._count_foci_b: QPushButton = QPushButton(
            "2. Count foci",
            parent=self,
        )
        self._count_foci_b.clicked.connect(self._start_fc_button_pressed)
        self._layout.addWidget(self._count_foci_b)

        self._foci_count_status_lb = QLabel(parent=self)
        self._foci_count_status_lb.setWordWrap(True)
        self._layout.addWidget(self._foci_count_status_lb)

        self._automatic_fc_dependency_status_lb = QLabel(parent=self)
        self._automatic_fc_dependency_status_lb.setStyleSheet(
            "color: #A80000; font-weight: bold;"
        )
        self._automatic_fc_dependency_status_lb.setWordWrap(True)
        self._layout.addWidget(self._automatic_fc_dependency_status_lb)
        self._update_automatic_fc_dependency_status()

        self._set_regions_b: QPushButton = QPushButton(
            "3. Set regions",
            parent=self,
        )
        self._set_regions_b.clicked.connect(self._set_regions_callback)
        self._layout.addWidget(self._set_regions_b)

        self._generate_plots_b: QPushButton = QPushButton(
            "4. Generate plots",
            parent=self,
        )
        self._generate_plots_b.clicked.connect(self._generate_plots_callback)
        self._layout.addWidget(self._generate_plots_b)

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

    def _update_cellpose_model_status(self) -> None:
        directories = ModelDirectoriesManager().ensure_default_configuration()
        model_found = any(
            is_bioimageio_weight_available(
                CELLPOSE_MODEL_NAME,
                directory,
            )
            for directory in directories
        )
        if model_found:
            self._cellpose_model_status_lb.setText("Cellpose model found")
            self._cellpose_model_status_lb.setStyleSheet(
                "color: #29BA00; font-weight: bold;"
            )
        else:
            self._cellpose_model_status_lb.setText("Cellpose model not found")
            self._cellpose_model_status_lb.setStyleSheet(
                "color: #A80000; font-weight: bold;"
            )

    def _get_cellpose_model_path(self) -> Path:
        directories = ModelDirectoriesManager().ensure_default_configuration()
        for directory in directories:
            if is_bioimageio_weight_available(
                CELLPOSE_MODEL_NAME,
                directory,
            ):
                return get_bioimageio_weight_path(
                    CELLPOSE_MODEL_NAME,
                    directory,
                )

        raise FileNotFoundError(
            "The downloaded Cellpose model was not found in any configured "
            "model directory."
        )

    def _set_contrasts_button_pressed(self) -> None:
        if self._automatic_workflow_active:
            return

        project_paths = self._project_list_widget.get_project_paths()
        if not project_paths:
            return
        if not self._validate_gpu_setting():
            return

        channels = self._keep_channels_widget.get_channels()
        self._contrast_failures = []
        self._set_automatic_workflow_active(True)
        self._contrast_status_lb.setText(
            f"Preparing 0/{len(project_paths)} projects"
        )

        self._contrast_preparation_worker = _prepare_contrasts_worker(
            project_paths=project_paths,
            channels=channels,
            stitching_options=self._get_stitching_options(),
        )
        self._contrast_preparation_worker.yielded.connect(
            self._on_contrast_preparation_update
        )
        self._contrast_preparation_worker.returned.connect(
            self._on_contrast_preparation_finished
        )
        self._contrast_preparation_worker.errored.connect(
            self._on_contrast_preparation_error
        )
        self._contrast_preparation_worker.start()

    def _on_contrast_preparation_update(
        self,
        update: ContrastPreparationUpdate,
    ) -> None:
        self._contrast_status_lb.setText(
            f"Project {update.project_index}/{update.project_total}: "
            f"{update.project_path.name}\n{update.stage}"
        )
        if update.error is not None:
            self._contrast_failures.append(
                f"{update.project_path.name}: {update.error}"
            )
        if update.stage in {"Ready", "Stitched image already exists"}:
            self._project_list_widget.refresh_rows()

    def _on_contrast_preparation_finished(
        self,
        prepared_projects: list[Path],
    ) -> None:
        self._contrast_preparation_worker = None
        self._set_automatic_workflow_active(False)
        self._project_list_widget.refresh_rows()

        if self._contrast_failures:
            show_warning(
                "The following projects could not be prepared:\n\n"
                + "\n".join(self._contrast_failures)
            )

        total_projects = len(prepared_projects) + len(self._contrast_failures)
        self._contrast_status_lb.setText(
            f"Prepared {len(prepared_projects)}/{total_projects} projects"
        )
        if prepared_projects:
            self._set_contrasts_callback()

    def _on_contrast_preparation_error(
        self,
        error: BaseException,
    ) -> None:
        self._contrast_preparation_worker = None
        self._set_automatic_workflow_active(False)
        self._contrast_status_lb.setText("Preparation failed")
        show_warning(f"Unexpected contrast-preparation error:\n{error}")

    def _set_automatic_workflow_active(self, active: bool) -> None:
        """Prevent automatic preparation and counting from overlapping."""
        self._automatic_workflow_active = active
        self._set_contrasts_b.setEnabled(not active)
        if active:
            self._count_foci_b.setEnabled(False)
        else:
            self._update_automatic_fc_dependency_status()

    def _clear_helper_widget(self) -> None:
        while self._helper_widget_layout.count():
            q_item = self._helper_widget_layout.takeAt(0)
            q_widget = q_item.widget()
            if q_widget is not None:
                q_widget.setParent(None)
                q_widget.deleteLater()
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

    def _get_directory_tile_paths(self, directory_path: str) -> dict[int, str]:
        tile_paths = self._get_ready_tile_paths(directory_path)
        return {
            tile_index: str(tile_path)
            for tile_index, tile_path in enumerate(tile_paths)
        }

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
        tiles_config_path = tiles_dir / TILES_CONFIG_FILE_NAME
        channels_config_path = tiles_dir / EXTRACTED_CHANNELS_FILE_NAME
        if not tiles_dir.is_dir():
            return []

        tiles_config = configparser.ConfigParser()
        channels_config = configparser.ConfigParser()
        try:
            tiles_config.read(tiles_config_path)
            channels_config.read(channels_config_path)
            tile_names = [
                tile_name for _, tile_name in tiles_config.items("tiles")
            ]
            stored_channels = channels_config.get(
                "channels",
                "kept",
            ).strip()
        except (configparser.Error, OSError, ValueError):
            return []

        if stored_channels == "all":
            channels: list[int] = []
        else:
            channels = parse_channel_string(stored_channels)
            if not channels:
                return []

        ready_tile_paths: list[Path] = []
        for tile_name in tile_names:
            tile_path = get_extracted_tile_path(
                tiles_dir / tile_name,
                channels,
            )
            if tile_path.is_dir() and tile_path.name.endswith(".ome.zarr"):
                ready_tile_paths.append(tile_path)

        return sorted(ready_tile_paths)

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

    def _tile_fc_outputs_exist_for_directory(
        self,
        directory_path: str | Path,
        colocalization_channels_filter: list[str],
    ) -> bool:
        tile_paths = self._get_ready_tile_paths(directory_path)
        if not tile_paths:
            return False
        auto_count_output_dir = (
            self._get_project_files_dir_for_directory(directory_path)
            / AUTO_COUNT_DIR_NAME
        )
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

    def _stitched_image_is_ready(self, directory_path: str | Path) -> bool:
        stitched_directory = Path(directory_path) / STITCHED_IMAGE_DIR_NAME
        stitched_paths = sorted(stitched_directory.glob("*.ome.zarr"))
        if not stitched_paths:
            return False

        tiles_directory = _get_project_tiles_path(directory_path)
        return any(
            Path(
                get_stitched_coordinates_path(
                    tiles_directory,
                    stitched_path,
                )
            ).exists()
            for stitched_path in stitched_paths
        )

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

    def _update_automatic_fc_dependency_status(self) -> None:
        required_modules = ("torch", "cellpose", "spotiflow")
        missing_modules = [
            module_name
            for module_name in required_modules
            if importlib.util.find_spec(module_name) is None
        ]

        dependencies_available = not missing_modules
        self._count_foci_b.setEnabled(
            dependencies_available and not self._automatic_workflow_active
        )
        self._automatic_fc_dependency_status_lb.setVisible(
            not dependencies_available
        )

        if dependencies_available:
            self._automatic_fc_dependency_status_lb.clear()
            self._count_foci_b.setToolTip("")
            return

        missing_text = ", ".join(missing_modules)
        status_text = (
            "Automatic foci counting unavailable. "
            f"Missing dependencies: {missing_text}"
        )
        self._automatic_fc_dependency_status_lb.setText(status_text)
        self._count_foci_b.setToolTip(status_text)

    def _start_fc_button_pressed(self) -> None:
        if self._automatic_workflow_active:
            print("An automatic workflow is already running")
            return
        if not self._validate_gpu_setting():
            return
        try:
            colocalization_channels_filter = (
                self._get_colocalization_channels_filter()
            )
        except ValueError as exc:
            show_warning(str(exc))
            return
        minimum_colocalization_intensity_ratio = (
            self._settings.minimum_colocalization_intensity_ratio
        )
        settings = replace(self._settings)
        spotiflow_model_name = self._spotiflow_model_name
        try:
            cellpose_model_path = self._get_cellpose_model_path()
        except FileNotFoundError as exc:
            show_warning(str(exc))
            return

        invalid_directories: list[str] = []
        directory_paths = self._project_list_widget.get_project_paths()

        for directory_path in directory_paths:
            project_path = _get_project_path(directory_path)
            tile_paths = self._get_ready_tile_paths(project_path)
            missing_requirements: list[str] = []

            if not self._stitched_image_is_ready(project_path):
                missing_requirements.append(
                    "stitched image or tile coordinates"
                )
            if not tile_paths:
                missing_requirements.append("prepared tiles")
            elif not all(
                bool(load_tile_contrasts(tile_path))
                for tile_path in tile_paths
            ):
                missing_requirements.append("tile contrasts")

            if missing_requirements:
                invalid_directories.append(
                    f"{project_path.name}: missing "
                    f"{', '.join(missing_requirements)}"
                )

        if invalid_directories:
            show_warning(
                "Run batch FC stopped.\n\n"
                "The following directories are not ready:\n\n"
                + "\n".join(invalid_directories)
            )
            return

        directory_paths = [str(path) for path in directory_paths]
        self._foci_count_failures = []
        self._set_automatic_workflow_active(True)
        self._foci_count_status_lb.setText(
            f"Processing 0/{len(directory_paths)} projects"
        )
        print(f"Run batch FC started for {len(directory_paths)} directories")
        self._foci_count_worker = self._run_batch_fc_worker(
            directory_paths=directory_paths,
            colocalization_channels_filter=colocalization_channels_filter,
            minimum_colocalization_intensity_ratio=(
                minimum_colocalization_intensity_ratio
            ),
            settings=settings,
            cellpose_model_path=cellpose_model_path,
            spotiflow_model_name=spotiflow_model_name,
        )
        self._foci_count_worker.yielded.connect(self._on_foci_count_update)
        self._foci_count_worker.returned.connect(self._on_foci_count_finished)
        self._foci_count_worker.errored.connect(self._on_foci_count_error)
        self._foci_count_worker.start()

    @thread_worker
    def _run_batch_fc_worker(
        self,
        directory_paths: list[str],
        colocalization_channels_filter: list[str],
        minimum_colocalization_intensity_ratio: float,
        settings: AutoFociCountSettings,
        cellpose_model_path: Path,
        spotiflow_model_name: str,
    ) -> Generator[FociCountUpdate, None, list[Path]]:
        completed_projects: list[Path] = []

        for directory_index, directory_path in enumerate(
            directory_paths, start=1
        ):
            project_path = _get_project_path(directory_path)
            try:
                print("")
                print(
                    "Run batch FC "
                    f"[{directory_index}/{len(directory_paths)}] "
                    f"starting {directory_path}"
                )
                yield FociCountUpdate(
                    project_path,
                    directory_index,
                    len(directory_paths),
                    "Checking project files",
                )
                tile_paths = self._get_ready_tile_paths(project_path)
                if not tile_paths:
                    raise ValueError(
                        f"No prepared tiles found for {project_path}"
                    )

                stitched_image_path = get_project_stitched_image_path(
                    _get_project_path(directory_path)
                )
                if stitched_image_path is None:
                    raise ValueError(
                        f"No stitched image found for {directory_path}"
                    )

                yield FociCountUpdate(
                    project_path,
                    directory_index,
                    len(directory_paths),
                    "Segmenting nuclei",
                )
                self._call_segmentation(project_path, cellpose_model_path)

                yield FociCountUpdate(
                    project_path,
                    directory_index,
                    len(directory_paths),
                    "Creating nuclei features",
                )
                self._create_auto_nuclei_features(
                    project_path=project_path,
                    tile_paths=tile_paths,
                    stitched_image_path=stitched_image_path,
                )
                yield FociCountUpdate(
                    project_path,
                    directory_index,
                    len(directory_paths),
                    "Creating SBS crops",
                )
                self._create_auto_sbs_crops_from_features(
                    project_path=project_path,
                    stitched_image_path=stitched_image_path,
                )
                need_tile_fc_stage = (
                    not self._tile_fc_outputs_exist_for_directory(
                        directory_path,
                        colocalization_channels_filter,
                    )
                )
                need_scored_stage = (
                    not self._scored_nuclei_outputs_exist_for_directory(
                        directory_path
                    )
                )
                if need_tile_fc_stage:
                    yield FociCountUpdate(
                        project_path,
                        directory_index,
                        len(directory_paths),
                        "Counting foci",
                    )
                    self._run_auto_tile_foci_count_for_directory(
                        directory_path,
                        colocalization_channels_filter,
                        minimum_colocalization_intensity_ratio,
                        use_gpu=settings.use_gpu,
                        spotiflow_model_name=spotiflow_model_name,
                    )
                else:
                    print(
                        "FC stage skip: tile FC outputs already exist for "
                        f"{directory_path}"
                    )

                if need_scored_stage:
                    yield FociCountUpdate(
                        project_path,
                        directory_index,
                        len(directory_paths),
                        "Saving scored nuclei",
                    )
                    save_auto_scored_nuclei_files_from_features(
                        project_path=project_path,
                        tile_paths=tile_paths,
                        stitched_image_path=stitched_image_path,
                    )
                else:
                    print(
                        "FC stage skip: scored nuclei outputs already exist for "
                        f"{directory_path}"
                    )

                print(
                    "Run batch FC "
                    f"[{directory_index}/{len(directory_paths)}] "
                    f"finished {directory_path}"
                )
            except (OSError, RuntimeError, ValueError) as exc:
                print(
                    "Run batch FC failed "
                    f"for project {project_path!r}: "
                    f"{type(exc).__name__}: {exc}"
                )
                yield FociCountUpdate(
                    project_path,
                    directory_index,
                    len(directory_paths),
                    "Failed",
                    error=str(exc),
                )
                continue

            completed_projects.append(project_path)
            yield FociCountUpdate(
                project_path,
                directory_index,
                len(directory_paths),
                "Ready",
            )

        print("Run batch FC finished")
        return completed_projects

    def _on_foci_count_update(self, update: FociCountUpdate) -> None:
        self._foci_count_status_lb.setText(
            f"Project {update.project_index}/{update.project_total}: "
            f"{update.project_path.name}\n{update.stage}"
        )
        if update.error is not None:
            self._foci_count_failures.append(
                f"{update.project_path.name}: {update.error}"
            )
        if update.stage == "Ready":
            self._project_list_widget.refresh_rows()
            self._status_update_callback()

    def _on_foci_count_finished(
        self,
        completed_projects: list[Path],
    ) -> None:
        self._foci_count_worker = None
        self._set_automatic_workflow_active(False)
        self._project_list_widget.refresh_rows()
        self._status_update_callback()

        if self._foci_count_failures:
            show_warning(
                "The following projects could not be counted:\n\n"
                + "\n".join(self._foci_count_failures)
            )

        total_projects = len(completed_projects) + len(
            self._foci_count_failures
        )
        self._foci_count_status_lb.setText(
            f"Processed {len(completed_projects)}/{total_projects} projects"
        )

    def _on_foci_count_error(self, error: BaseException) -> None:
        self._foci_count_worker = None
        self._set_automatic_workflow_active(False)
        self._foci_count_status_lb.setText("Counting failed")
        show_warning(f"Unexpected automatic foci-counting error:\n{error}")

    def _get_colocalization_channels_filter(self) -> list[str]:
        if not self._settings.filter_channels_enabled:
            return []
        channels_raw = parse_channel_string(self._settings.filter_channels)
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

    def _get_stitching_options(self) -> dict[str, int | bool | None]:
        return {
            "registration_channel": self._settings.registration_channel - 1,
            "registration_scale": self._settings.registration_scale,
            "num_workers": (
                None
                if self._settings.num_workers == 0
                else self._settings.num_workers
            ),
            "n_batch": (
                None if self._settings.n_batch == 0 else self._settings.n_batch
            ),
            "use_gpu": self._settings.use_gpu,
        }

    def _on_settings_saved(self) -> None:
        self._settings = self._settings_manager.load()
        self._update_settings_status()

    def _update_settings_status(self) -> None:
        status = (
            "default"
            if self._settings == AutoFociCountSettings()
            else "custom"
        )
        self._settings_status_lb.setText(f"Settings: {status}")

    def _validate_gpu_setting(self) -> bool:
        if not self._settings.use_gpu:
            return True

        if importlib.util.find_spec("cupy") is None:
            show_warning(
                "GPU processing is enabled, but CuPy is not installed."
            )
            return False

        try:
            import cupy
        except (ImportError, OSError) as exc:
            show_warning(f"GPU processing is not available: {exc}")
            return False

        try:
            device_count = cupy.cuda.runtime.getDeviceCount()
        except cupy.cuda.runtime.CUDARuntimeError as exc:
            show_warning(f"GPU processing is not available: {exc}")
            return False

        if device_count < 1:
            show_warning(
                "GPU processing is enabled, but no CUDA GPU was found."
            )
            return False

        return True

    def _call_segmentation(
        self,
        directory_path: str | Path,
        model_path: Path,
    ) -> None:
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
        pending_tile_paths: list[Path] = []
        print(
            f"Starting segmentation for {total_tiles} tiles in {directory_path}"
        )
        for tile_path in tile_paths:
            segmentation_output_path = segmentation_output_dir / (
                f"{tile_path.name[: -len('.ome.zarr')]}"
                f"{SEGMENTATION_MASKS_FILE_NAME_SUFFIX}"
            )
            if segmentation_output_path.exists():
                print(
                    "Segmentation output already exists for "
                    f"{tile_path}; skipping segmentation"
                )
            else:
                pending_tile_paths.append(tile_path)

        run_segmentation_batch_subprocess(
            image_paths=pending_tile_paths,
            model_path=model_path,
            output_name=SEGMENTATION_OUTPUT_NAME,
            output_dir=segmentation_output_dir,
        )

        for tile_index, tile_path in enumerate(tile_paths, start=1):
            segmentation_output_path = segmentation_output_dir / (
                f"{tile_path.name[: -len('.ome.zarr')]}"
                f"{SEGMENTATION_MASKS_FILE_NAME_SUFFIX}"
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

    def _create_auto_nuclei_features(
        self,
        project_path: Path,
        tile_paths: list[Path],
        stitched_image_path: Path,
    ) -> None:
        pick_nuclei_directory = (
            project_path / PROJECT_FILE_DIR_NAME / PICK_NUCLEI_DIR_NAME
        )
        points_path = pick_nuclei_directory / NUCLEI_POINTS_LAYER_FILE_NAME
        features_path = (
            pick_nuclei_directory / NUCLEI_POINTS_FEATURES_TABLE_FILE_NAME
        )
        if points_path.exists() and features_path.exists():
            print(
                "Automatic nuclei features already exist for "
                f"{project_path}; skipping"
            )
            return

        labels_by_tile: dict[int, NDArray[np.uint32]] = {}
        tile_offsets_zyx: dict[int, tuple[float, float, float]] = {}
        for tile_index, tile_path in enumerate(tile_paths):
            segmentation_path = _get_segmentation_output_path_for_tile(
                project_path, tile_path
            )
            labels_by_tile[tile_index] = load_cleaned_segmentation_labels(
                segmentation_path
            )
            tile_offsets_zyx[tile_index] = get_tile_stitched_pixel_offsets(
                stitched_image_path,
                project_path / TILES_DIR_NAME,
                tile_path,
            )

        candidates = build_nucleus_candidates(
            labels_by_tile=labels_by_tile,
            tile_offsets_zyx=tile_offsets_zyx,
        )
        candidates = deduplicate_nucleus_candidates(
            candidates=candidates,
            labels_by_tile=labels_by_tile,
            tile_offsets_zyx=tile_offsets_zyx,
        )
        save_nucleus_features_and_points(
            candidates=candidates,
            project_path=project_path,
        )
        print(
            f"Saved {len(candidates)} automatic nuclei features for {project_path}"
        )

    def _create_auto_sbs_crops_from_features(
        self,
        project_path: Path,
        stitched_image_path: Path,
    ) -> None:
        features_path = (
            project_path
            / PROJECT_FILE_DIR_NAME
            / PICK_NUCLEI_DIR_NAME
            / NUCLEI_POINTS_FEATURES_TABLE_FILE_NAME
        )
        if not features_path.exists():
            raise FileNotFoundError(
                f"Nuclei features table not found: {features_path}"
            )

        features = pd.read_csv(features_path)
        stitched_data = resolve_lazy_image_data(stitched_image_path)
        if stitched_data is None:
            raise ValueError(
                f"Could not load stitched image: {stitched_image_path}"
            )

        cut_sbs_directory = (
            project_path
            / PROJECT_FILE_DIR_NAME
            / PICK_NUCLEI_DIR_NAME
            / CUT_SBS_DIR_NAME
        )
        cut_sbs_directory.mkdir(parents=True, exist_ok=True)

        flags_manager = SBSFlagsManager(project_path)
        if not flags_manager.load():
            raise ValueError(f"Could not load SBS flags for {project_path}")

        metadata_rows: list[dict[str, int | str]] = []
        project_name = project_path.name.removesuffix("_clsp_project")

        for feature in features.to_dict(orient="records"):
            sbs_number = int(feature["sbs_number"])
            sbs_key = f"sbs{sbs_number}"
            sbs_name = (
                f"{project_name}_sbs{sbs_number}{SBS_FILE_NAME_EXTENSION}"
            )
            output_path = cut_sbs_directory / sbs_name

            crop_bounds = get_sbs_crop_bounds(feature, stitched_data)
            if crop_bounds is None:
                continue

            needs_recalculation = (
                SBSFlag.COORD_RECALC_NEEDED.value
                in flags_manager.get_flags(sbs_key)
            )
            if output_path.exists() and not needs_recalculation:
                metadata_rows.append(
                    {
                        "sbs_image_name": sbs_name,
                        "z1": crop_bounds.z_start,
                        "z2": crop_bounds.z_stop,
                        "y1": crop_bounds.y_start,
                        "y2": crop_bounds.y_stop,
                        "x1": crop_bounds.x_start,
                        "x2": crop_bounds.x_stop,
                    }
                )
                continue

            cropped_data = crop_sbs_data(
                stitched_data,
                feature,
                crop_bounds,
            )
            if cropped_data is None:
                continue

            imwrite(
                output_path,
                cropped_data.compute().values,
                imagej=True,
                metadata={"axes": "ZCYX"},
            )
            if needs_recalculation:
                flags_manager.remove_flag(
                    sbs_key,
                    SBSFlag.COORD_RECALC_NEEDED,
                )

            metadata_rows.append(
                {
                    "sbs_image_name": sbs_name,
                    "z1": crop_bounds.z_start,
                    "z2": crop_bounds.z_stop,
                    "y1": crop_bounds.y_start,
                    "y2": crop_bounds.y_stop,
                    "x1": crop_bounds.x_start,
                    "x2": crop_bounds.x_stop,
                }
            )

        metadata_path = cut_sbs_directory / SBS_METADATA_FILE_NAME
        pd.DataFrame(metadata_rows).to_csv(metadata_path, index=False)
        if not flags_manager.save():
            raise OSError(f"Could not save SBS flags for {project_path}")

    def _call_automatic_foci_count(
        self,
        image_path: str | Path,
        segmentation_path: str | Path,
        normalization_input_min: float,
        normalization_input_max: float,
        colocalization_channels_filter: list[str],
        minimum_colocalization_intensity_ratio: float,
        *,
        use_gpu: bool,
        spotiflow_model_name: str,
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
        print(f"Using Spotiflow model name: {spotiflow_model_name}")
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
            use_gpu=use_gpu,
            model_name=spotiflow_model_name,
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
        *,
        use_gpu: bool,
        spotiflow_model_name: str,
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

        processed_image_paths: list[Path] = []
        unfiltered_points_paths: list[Path] = []
        for tile_path, segmentation_output_path in zip(
            pending_tile_paths, segmentation_paths, strict=True
        ):
            auto_count_output_dir = (
                segmentation_output_path.parent.parent / AUTO_COUNT_DIR_NAME
            )
            (*_, processed_image_path, _preprocessing_stats_path) = (
                run_auto_count_preprocessed_spots_on_paths(
                    image_path=tile_path,
                    segmentation_path=segmentation_output_path,
                    output_dir=auto_count_output_dir,
                    normalize_spots_channel=True,
                    normalization_input_min=normalization_input_min,
                    normalization_input_max=normalization_input_max,
                    normalization_output_max=1000,
                )
            )
            (_semantic_mask_path, unfiltered_points_path, _filtered_path) = (
                get_auto_count_output_paths(
                    image_path=tile_path,
                    output_dir=auto_count_output_dir,
                )
            )
            if not unfiltered_points_path.exists():
                processed_image_paths.append(processed_image_path)
                unfiltered_points_paths.append(unfiltered_points_path)

        if processed_image_paths:
            run_spotiflow_batch_subprocess(
                image_paths=processed_image_paths,
                output_csv_paths=unfiltered_points_paths,
                model_name=spotiflow_model_name,
                use_gpu=use_gpu,
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
                use_gpu=use_gpu,
                spotiflow_model_name=spotiflow_model_name,
            )
