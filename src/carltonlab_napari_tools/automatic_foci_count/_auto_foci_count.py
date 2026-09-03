from __future__ import annotations

import collections.abc
import configparser
import csv
import heapq
import json
from pathlib import Path

import numpy as np
from scipy import ndimage
from tifffile import imread, imwrite

from carltonlab_napari_tools._shared_variables import (
    AUTO_COUNT_BINARY_MASK_FILE_NAME_SUFFIX_TEMPLATE,
    AUTO_COUNT_FILTERED_POINTS_FILE_NAME_EXTENSION,
    AUTO_COUNT_POINTS_FILE_NAME_EXTENSION,
    AUTO_COUNT_PREPROCESSING_STATS_FILE_NAME_SUFFIX,
    AUTO_COUNT_PROCESSED_SPOTS_IMAGE_FILE_NAME_SUFFIX,
    TILE_CONTRASTS_FILE_NAME_SUFFIX,
)
from carltonlab_napari_tools.segmentation._segmentation import (
    SpotiflowDetector,
    load_ome_zarr_image_zyx,
    run_spotiflow_subprocess,
)

BRIDGE_RATIO_THRESHOLD = 0.40
MIN_COMPONENT_COLOCALIZATION_OVERLAP_VOXELS = 5
DEFAULT_MINIMUM_COLOCALIZATION_INTENSITY_RATIO = 0.25


def _strip_ome_zarr_suffix(path: str | Path) -> str:
    image_path = Path(path)
    if image_path.name.endswith(".ome.zarr"):
        return image_path.name[: -len(".ome.zarr")]
    return image_path.stem


def _get_binary_mask_file_name_suffix(channel_index: int) -> str:
    return AUTO_COUNT_BINARY_MASK_FILE_NAME_SUFFIX_TEMPLATE.format(
        channel_number=channel_index + 1
    )


def get_auto_count_output_paths(
    image_path: str | Path,
    output_dir: str | Path,
) -> tuple[Path, Path, Path]:
    base_name = _strip_ome_zarr_suffix(image_path)
    output_dir_path = Path(output_dir)
    semantic_mask_path = (
        output_dir_path / f"{base_name}_spots_semantic_mask.npy"
    )
    unfiltered_points_layer_path = (
        output_dir_path / f"{base_name}{AUTO_COUNT_POINTS_FILE_NAME_EXTENSION}"
    )
    filtered_points_layer_path = output_dir_path / (
        f"{base_name}{AUTO_COUNT_FILTERED_POINTS_FILE_NAME_EXTENSION}"
    )
    return (
        semantic_mask_path,
        unfiltered_points_layer_path,
        filtered_points_layer_path,
    )


def get_auto_count_rejected_points_path(
    image_path: str | Path,
    output_dir: str | Path,
    filter_name: str,
) -> Path:
    base_name = _strip_ome_zarr_suffix(image_path)
    return Path(output_dir) / f"{base_name}_rejected_{filter_name}_points.csv"


def get_auto_count_preprocessed_spots_output_paths(
    image_path: str | Path,
    output_dir: str | Path,
) -> tuple[Path, Path]:
    base_name = _strip_ome_zarr_suffix(image_path)
    output_dir_path = Path(output_dir)
    processed_image_path = (
        output_dir_path
        / f"{base_name}{AUTO_COUNT_PROCESSED_SPOTS_IMAGE_FILE_NAME_SUFFIX}"
    )
    preprocessing_stats_path = (
        output_dir_path
        / f"{base_name}{AUTO_COUNT_PREPROCESSING_STATS_FILE_NAME_SUFFIX}"
    )
    return processed_image_path, preprocessing_stats_path


def get_auto_count_binary_mask_output_path(
    image_path: str | Path,
    output_dir: str | Path,
    channel_index: int,
) -> Path:
    base_name = _strip_ome_zarr_suffix(image_path)
    output_dir_path = Path(output_dir)
    return (
        output_dir_path
        / f"{base_name}{_get_binary_mask_file_name_suffix(channel_index)}"
    )


def auto_count_preprocessed_spots_outputs_exist(
    image_path: str | Path,
    output_dir: str | Path,
) -> bool:
    processed_image_path, preprocessing_stats_path = (
        get_auto_count_preprocessed_spots_output_paths(
            image_path=image_path,
            output_dir=output_dir,
        )
    )
    return processed_image_path.exists() and preprocessing_stats_path.exists()


def auto_count_binary_mask_outputs_exist(
    image_path: str | Path,
    output_dir: str | Path,
    channel_indices: collections.abc.Sequence[int],
) -> bool:
    return all(
        get_auto_count_binary_mask_output_path(
            image_path=image_path,
            output_dir=output_dir,
            channel_index=channel_index,
        ).exists()
        for channel_index in channel_indices
    )


def get_requested_colocalization_channel_indices(
    colocalization_channels_filter: collections.abc.Sequence[str],
) -> list[int]:
    requested_indices: list[int] = []
    for channel_name in colocalization_channels_filter:
        normalized = channel_name.strip().lower()
        if normalized.startswith("channel-"):
            normalized = normalized[len("channel-") :]
        elif normalized.startswith("channel_"):
            normalized = normalized[len("channel_") :]
        channel_number = int(normalized)
        if channel_number <= 0:
            continue
        requested_indices.append(channel_number - 1)
    return sorted(set(requested_indices))


def get_auto_count_contrast_config_path(
    image_path: str | Path,
) -> Path:
    image_path_obj = Path(image_path)
    base_name = _strip_ome_zarr_suffix(image_path_obj)
    config_path = image_path_obj.parent / (
        f"{base_name}{TILE_CONTRASTS_FILE_NAME_SUFFIX}"
    )
    if not config_path.exists():
        raise FileNotFoundError(
            f"Auto-count contrast config not found: {config_path}"
        )
    return config_path


def load_auto_count_threshold_from_config(
    image_path: str | Path,
    channel_index: int = 1,
) -> float:
    config_path = get_auto_count_contrast_config_path(
        image_path=image_path,
    )
    parser = configparser.ConfigParser()
    read_ok = parser.read(config_path)
    if not read_ok:
        raise ValueError(f"Could not read contrast config {config_path}")
    if "ImageContrasts" not in parser:
        raise ValueError(f"{config_path}: missing [ImageContrasts] section")
    channel_key = f"channel-{channel_index + 1}"
    if channel_key not in parser["ImageContrasts"]:
        raise ValueError(
            f"{config_path}: missing {channel_key} contrast entry"
        )

    raw = parser["ImageContrasts"][channel_key]
    parts = [part.strip() for part in raw.split(",")]
    if len(parts) != 2:
        raise ValueError(
            f"{config_path}: invalid {channel_key} contrast value {raw!r}"
        )
    return float(parts[0])


def save_points_csv_for_napari(
    points_path: str | Path,
    spots_coords: np.ndarray,
) -> Path:
    points_path_obj = Path(points_path)
    points_array = np.asarray(spots_coords)
    if points_array.ndim != 2:
        raise ValueError(
            f"Expected a 2D points array, got shape {points_array.shape}"
        )

    column_names = ["index"] + [
        f"axis-{axis_index}" for axis_index in range(points_array.shape[1])
    ]
    with points_path_obj.open("w", encoding="utf-8", newline="") as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(column_names)
        for point_index, point in enumerate(points_array):
            writer.writerow([point_index, *point.tolist()])

    return points_path_obj


def get_segmentation_npz_output_path(
    segmentation_npy_path: str | Path,
) -> Path:
    npy_path = Path(segmentation_npy_path)
    if npy_path.suffix != ".npy":
        raise ValueError(
            f"Expected a .npy segmentation file, got: {npy_path.name}"
        )
    return npy_path.with_suffix(".npz")


def convert_segmentation_npy_to_npz(
    segmentation_npy_path: str | Path,
    output_npz_path: str | Path | None = None,
) -> Path:
    npy_path = Path(segmentation_npy_path)
    if not npy_path.exists():
        raise FileNotFoundError(f"Segmentation file not found: {npy_path}")

    npz_path = Path(
        output_npz_path or get_segmentation_npz_output_path(npy_path)
    )
    segmentation_arr = np.load(npy_path)
    np.savez_compressed(npz_path, segmentation_arr)
    return npz_path


def load_segmentation_array(
    segmentation_path: str | Path,
) -> np.ndarray:
    segmentation_file = Path(segmentation_path)
    if not segmentation_file.exists():
        raise FileNotFoundError(
            f"Segmentation file not found: {segmentation_file}"
        )

    if segmentation_file.suffix == ".npy":
        return np.asarray(np.load(segmentation_file))

    if segmentation_file.suffix == ".npz":
        with np.load(segmentation_file) as npz_file:
            if not npz_file.files:
                raise ValueError(
                    f"Segmentation npz file is empty: {segmentation_file}"
                )
            return np.asarray(npz_file[npz_file.files[0]])

    raise ValueError(
        f"Unsupported segmentation file type: {segmentation_file}"
    )


def apply_hard_threshold(
    stack: np.ndarray,
    lower_bound: float,
) -> tuple[np.ndarray, int]:
    out = np.asarray(stack).copy()
    removed = int(np.count_nonzero(out < lower_bound))
    out[out < lower_bound] = 0
    return out, removed


def compute_masked_normalization_bounds(
    stack: np.ndarray,
    mask: np.ndarray,
) -> tuple[float, float]:
    masked_values = np.asarray(stack)[np.asarray(mask) > 0]
    if masked_values.size == 0:
        raise ValueError("Segmentation mask contains no foreground voxels.")

    input_min = float(masked_values.min())
    input_max = float(masked_values.max())
    if input_max <= input_min:
        raise ValueError(
            "Invalid masked normalization bounds: "
            f"min={input_min}, max={input_max}"
        )
    return input_min, input_max


def compute_shared_masked_normalization_bounds(
    image_paths: list[str | Path],
    segmentation_paths: list[str | Path],
) -> tuple[float, float]:
    if len(image_paths) != len(segmentation_paths):
        raise ValueError(
            "image_paths and segmentation_paths must have the same length"
        )
    if not image_paths:
        raise ValueError("No tiles were provided for shared normalization.")

    global_min = None
    global_max = None
    for image_path, segmentation_path in zip(
        image_paths, segmentation_paths, strict=True
    ):
        spots_image_zyx, _ = load_ome_zarr_image_zyx(
            image_path, channel_index=1
        )
        segmentation_arr = load_segmentation_array(segmentation_path)
        if spots_image_zyx.shape != segmentation_arr.shape:
            raise ValueError(
                "Image and segmentation shapes do not match: "
                f"{spots_image_zyx.shape} != {segmentation_arr.shape}"
            )
        input_min, input_max = compute_masked_normalization_bounds(
            spots_image_zyx,
            segmentation_arr,
        )
        global_min = (
            input_min if global_min is None else min(global_min, input_min)
        )
        global_max = (
            input_max if global_max is None else max(global_max, input_max)
        )

    if global_min is None or global_max is None or global_max <= global_min:
        raise ValueError(
            "Invalid shared masked normalization bounds: "
            f"min={global_min}, max={global_max}"
        )
    return float(global_min), float(global_max)


def normalize_nonzero_pixels(
    stack: np.ndarray,
    input_min: float,
    input_max: float,
    output_max: int = 1000,
) -> np.ndarray:
    out = np.zeros(np.asarray(stack).shape, dtype=np.uint16)
    keep = np.asarray(stack) > 0
    if not np.any(keep):
        return out

    scaled = (np.asarray(stack)[keep].astype(np.float32) - input_min) / (
        input_max - input_min
    )
    scaled = np.clip(scaled, 0.0, 1.0)
    out[keep] = np.rint(scaled * float(output_max)).astype(np.uint16)
    return out


def preprocess_spots_image_for_counting(
    spots_image_zyx: np.ndarray,
    segmentation_arr: np.ndarray,
    intensity_threshold: float,
    normalization_input_min: float | None = None,
    normalization_input_max: float | None = None,
    normalization_output_max: int = 1000,
) -> tuple[np.ndarray, dict[str, float]]:
    if spots_image_zyx.shape != segmentation_arr.shape:
        raise ValueError(
            "Image and segmentation shapes do not match: "
            f"{spots_image_zyx.shape} != {segmentation_arr.shape}"
        )

    if normalization_input_min is None or normalization_input_max is None:
        input_min, input_max = compute_masked_normalization_bounds(
            spots_image_zyx,
            segmentation_arr,
        )
    else:
        input_min = float(normalization_input_min)
        input_max = float(normalization_input_max)
        if input_max <= input_min:
            raise ValueError(
                "Invalid provided normalization bounds: "
                f"min={input_min}, max={input_max}"
            )
    thresholded, removed_below_threshold = apply_hard_threshold(
        spots_image_zyx,
        intensity_threshold,
    )
    processed = normalize_nonzero_pixels(
        thresholded,
        input_min,
        input_max,
        output_max=normalization_output_max,
    )
    stats = {
        "normalization_input_min": input_min,
        "normalization_input_max": input_max,
        "threshold_lower_bound": float(intensity_threshold),
        "threshold_removed_voxels": float(removed_below_threshold),
    }
    return processed, stats


def preprocess_reference_image_for_counting(
    ref_image_zyx: np.ndarray,
    intensity_threshold: float,
    make_binary_mask: bool = False,
) -> tuple[np.ndarray, dict[str, float]]:
    thresholded, removed_below_threshold = apply_hard_threshold(
        ref_image_zyx,
        intensity_threshold,
    )
    processed = thresholded
    if make_binary_mask:
        processed = (thresholded > 0).astype(np.uint8)
    stats = {
        "ref_threshold_lower_bound": float(intensity_threshold),
        "ref_threshold_removed_voxels": float(removed_below_threshold),
    }
    return processed, stats


def prepare_auto_count_inputs(
    image_path: str | Path,
    segmentation_path: str | Path,
    normalize_spots_channel: bool = False,
    intensity_threshold: float | None = None,
    make_binary_mask: bool = False,
    normalization_input_min: float | None = None,
    reference_intensity_threshold: float | None = None,
    normalization_input_max: float | None = None,
    normalization_output_max: int = 1000,
) -> tuple[
    np.ndarray,
    np.ndarray,
    np.ndarray,
    dict[str, float],
    dict[str, float],
]:
    ref_image_zyx, spacing = load_ome_zarr_image_zyx(
        image_path, channel_index=0
    )
    spots_image_zyx, _ = load_ome_zarr_image_zyx(image_path, channel_index=1)
    segmentation_arr = load_segmentation_array(segmentation_path)

    if spots_image_zyx.shape != segmentation_arr.shape:
        raise ValueError(
            "Image and segmentation shapes do not match: "
            f"{spots_image_zyx.shape} != {segmentation_arr.shape}"
        )

    preprocessing_stats: dict[str, float] = {}
    if reference_intensity_threshold is not None:
        ref_image_zyx, ref_preprocessing_stats = (
            preprocess_reference_image_for_counting(
                ref_image_zyx,
                intensity_threshold=reference_intensity_threshold,
                make_binary_mask=make_binary_mask,
            )
        )
        preprocessing_stats.update(ref_preprocessing_stats)
    if normalize_spots_channel:
        if intensity_threshold is None:
            raise ValueError(
                "normalize_spots_channel=True requires intensity_threshold."
            )
        spots_image_zyx, spots_preprocessing_stats = (
            preprocess_spots_image_for_counting(
                spots_image_zyx,
                segmentation_arr,
                intensity_threshold=intensity_threshold,
                normalization_input_min=normalization_input_min,
                normalization_input_max=normalization_input_max,
                normalization_output_max=normalization_output_max,
            )
        )
        preprocessing_stats.update(spots_preprocessing_stats)

    return (
        ref_image_zyx,
        spots_image_zyx,
        segmentation_arr,
        spacing,
        preprocessing_stats,
    )


def prepare_auto_count_preprocessed_spots_inputs(
    image_path: str | Path,
    segmentation_path: str | Path,
    normalize_spots_channel: bool = False,
    intensity_threshold: float | None = None,
    make_binary_mask: bool = False,
    normalization_input_min: float | None = None,
    reference_intensity_threshold: float | None = None,
    normalization_input_max: float | None = None,
    normalization_output_max: int = 1000,
) -> tuple[
    np.ndarray,
    np.ndarray,
    np.ndarray,
    dict[str, float],
    dict[str, float],
]:
    return prepare_auto_count_inputs(
        image_path=image_path,
        segmentation_path=segmentation_path,
        normalize_spots_channel=normalize_spots_channel,
        intensity_threshold=intensity_threshold,
        make_binary_mask=make_binary_mask,
        reference_intensity_threshold=reference_intensity_threshold,
        normalization_input_min=normalization_input_min,
        normalization_input_max=normalization_input_max,
        normalization_output_max=normalization_output_max,
    )


def save_auto_count_preprocessed_spots_outputs(
    image_path: str | Path,
    output_dir: str | Path,
    processed_spots_image: np.ndarray,
    preprocessing_stats: dict[str, float],
) -> tuple[Path, Path]:
    output_dir_path = Path(output_dir)
    output_dir_path.mkdir(parents=True, exist_ok=True)

    processed_image_path, preprocessing_stats_path = (
        get_auto_count_preprocessed_spots_output_paths(
            image_path=image_path,
            output_dir=output_dir_path,
        )
    )
    imwrite(processed_image_path, np.asarray(processed_spots_image))
    preprocessing_stats_path.write_text(
        json.dumps(preprocessing_stats, indent=2),
        encoding="utf-8",
    )
    return processed_image_path, preprocessing_stats_path


def save_auto_count_binary_mask_output(
    image_path: str | Path,
    output_dir: str | Path,
    binary_mask: np.ndarray,
    channel_index: int,
) -> Path:
    output_dir_path = Path(output_dir)
    output_dir_path.mkdir(parents=True, exist_ok=True)
    binary_mask_path = get_auto_count_binary_mask_output_path(
        image_path=image_path,
        output_dir=output_dir_path,
        channel_index=channel_index,
    )
    imwrite(binary_mask_path, np.asarray(binary_mask, dtype=np.uint8))
    return binary_mask_path


def build_auto_count_binary_mask(
    image_path: str | Path,
    channel_index: int,
    intensity_threshold: float | None = None,
) -> tuple[np.ndarray, dict[str, float]]:
    if intensity_threshold is None:
        intensity_threshold = load_auto_count_threshold_from_config(
            image_path=image_path,
            channel_index=channel_index,
        )
    ref_image_zyx, _spacing = load_ome_zarr_image_zyx(
        image_path,
        channel_index=channel_index,
    )
    return preprocess_reference_image_for_counting(
        ref_image_zyx,
        intensity_threshold=float(intensity_threshold),
        make_binary_mask=True,
    )


def ensure_auto_count_binary_mask_output(
    image_path: str | Path,
    output_dir: str | Path,
    channel_index: int,
) -> Path:
    binary_mask_path = get_auto_count_binary_mask_output_path(
        image_path=image_path,
        output_dir=output_dir,
        channel_index=channel_index,
    )
    if binary_mask_path.exists():
        return binary_mask_path
    binary_mask, _stats = build_auto_count_binary_mask(
        image_path=image_path,
        channel_index=channel_index,
    )
    return save_auto_count_binary_mask_output(
        image_path=image_path,
        output_dir=output_dir,
        binary_mask=binary_mask,
        channel_index=channel_index,
    )


def run_auto_count_preprocessed_spots_on_paths(
    image_path: str | Path,
    segmentation_path: str | Path,
    output_dir: str | Path,
    normalize_spots_channel: bool = False,
    intensity_threshold: float | None = None,
    normalization_input_min: float | None = None,
    normalization_input_max: float | None = None,
    normalization_output_max: int = 1000,
) -> tuple[
    np.ndarray,
    np.ndarray,
    np.ndarray,
    dict[str, float],
    dict[str, float],
    Path,
    Path,
]:
    processed_image_path, preprocessing_stats_path = (
        get_auto_count_preprocessed_spots_output_paths(
            image_path=image_path,
            output_dir=output_dir,
        )
    )
    if auto_count_preprocessed_spots_outputs_exist(image_path, output_dir):
        ref_image_zyx, spacing = load_ome_zarr_image_zyx(
            image_path, channel_index=0
        )
        segmentation_arr = load_segmentation_array(segmentation_path)
        processed_spots_image = np.asarray(imread(processed_image_path))
        preprocessing_stats = json.loads(
            preprocessing_stats_path.read_text(encoding="utf-8")
        )
    else:
        if normalize_spots_channel and intensity_threshold is None:
            intensity_threshold = load_auto_count_threshold_from_config(
                image_path=image_path,
            )

        (
            ref_image_zyx,
            processed_spots_image,
            segmentation_arr,
            spacing,
            preprocessing_stats,
        ) = prepare_auto_count_preprocessed_spots_inputs(
            image_path=image_path,
            segmentation_path=segmentation_path,
            normalize_spots_channel=normalize_spots_channel,
            intensity_threshold=intensity_threshold,
            normalization_input_min=normalization_input_min,
            normalization_input_max=normalization_input_max,
            normalization_output_max=normalization_output_max,
        )
        processed_image_path, preprocessing_stats_path = (
            save_auto_count_preprocessed_spots_outputs(
                image_path=image_path,
                output_dir=output_dir,
                processed_spots_image=processed_spots_image,
                preprocessing_stats=preprocessing_stats,
            )
        )
    return (
        ref_image_zyx,
        processed_spots_image,
        segmentation_arr,
        spacing,
        preprocessing_stats,
        processed_image_path,
        preprocessing_stats_path,
    )


def save_auto_count_outputs(
    image_path: str | Path,
    output_dir: str | Path,
    spots_semantic_segm: np.ndarray,
    spots_coords: np.ndarray,
) -> tuple[Path, Path]:
    output_dir_path = Path(output_dir)
    output_dir_path.mkdir(parents=True, exist_ok=True)

    (
        semantic_mask_path,
        points_layer_path,
        _filtered_points_layer_path,
    ) = get_auto_count_output_paths(
        image_path=image_path,
        output_dir=output_dir_path,
    )
    np.save(semantic_mask_path, np.asarray(spots_semantic_segm))
    save_points_csv_for_napari(points_layer_path, spots_coords)
    return semantic_mask_path, points_layer_path


def filter_spots_by_nonzero_and_component_volume(
    spots_coords: np.ndarray,
    processed_spots_image: np.ndarray,
    min_component_volume: int = 45,
) -> np.ndarray:
    filtered, _rejected = (
        filter_spots_by_nonzero_and_component_volume_with_rejections(
            spots_coords, processed_spots_image, min_component_volume
        )
    )
    return filtered


def filter_spots_by_nonzero_and_component_volume_with_rejections(
    spots_coords: np.ndarray,
    processed_spots_image: np.ndarray,
    min_component_volume: int = 45,
) -> tuple[np.ndarray, dict[str, np.ndarray]]:
    if min_component_volume < 0:
        raise ValueError(
            f"min_component_volume must be >= 0, got {min_component_volume}"
        )
    empty = np.empty((0, 3), dtype=float)
    rejected = {
        "out_of_bounds": empty.copy(),
        "background": empty.copy(),
        "small_component": empty.copy(),
        "duplicate_component": empty.copy(),
    }
    if len(spots_coords) == 0:
        return empty, rejected

    labels, n_labels = ndimage.label(processed_spots_image > 0)
    if n_labels == 0:
        rejected["background"] = np.asarray(spots_coords)
        return empty, rejected

    component_sizes = np.bincount(labels.ravel())
    rounded = np.rint(spots_coords).astype(int)
    max_z, max_y, max_x = processed_spots_image.shape
    component_to_indices: dict[int, list[int]] = {}
    rejected_indices = {name: [] for name in rejected}

    for idx, (z, y, x) in enumerate(rounded):
        if not (0 <= z < max_z and 0 <= y < max_y and 0 <= x < max_x):
            rejected_indices["out_of_bounds"].append(idx)
            continue
        if processed_spots_image[z, y, x] <= 0:
            rejected_indices["background"].append(idx)
            continue
        label_id = labels[z, y, x]
        if label_id == 0:
            rejected_indices["background"].append(idx)
            continue
        if component_sizes[label_id] < min_component_volume:
            rejected_indices["small_component"].append(idx)
            continue
        component_to_indices.setdefault(int(label_id), []).append(idx)

    if not component_to_indices:
        points_array = np.asarray(spots_coords)
        for name, indices in rejected_indices.items():
            rejected[name] = points_array[indices] if indices else empty.copy()
        return empty, rejected

    filtered_indices: list[int] = []
    for label_id, indices in component_to_indices.items():
        component_mask = labels == label_id
        candidate_points = np.asarray(spots_coords)[indices]
        candidate_peaks = [
            _get_local_peak_coordinate_and_intensity(
                processed_spots_image,
                component_mask,
                point,
            )
            for point in candidate_points
        ]
        candidate_order = sorted(
            range(len(indices)),
            key=lambda offset: candidate_peaks[offset][1],
            reverse=True,
        )
        accepted_offsets: list[int] = []
        for offset in candidate_order:
            if all(
                _get_bridge_ratio(
                    processed_spots_image,
                    component_mask,
                    candidate_peaks[offset][0],
                    candidate_peaks[accepted_offset][0],
                )
                < BRIDGE_RATIO_THRESHOLD
                for accepted_offset in accepted_offsets
            ):
                accepted_offsets.append(offset)
                filtered_indices.append(indices[offset])
            else:
                rejected_indices["duplicate_component"].append(indices[offset])

    filtered_indices.sort()
    points_array = np.asarray(spots_coords)
    for name, indices in rejected_indices.items():
        rejected[name] = points_array[indices] if indices else empty.copy()
    return points_array[filtered_indices], rejected


def _get_local_peak_coordinate_and_intensity(
    image: np.ndarray,
    component_mask: np.ndarray,
    point: np.ndarray,
    radius: int = 2,
) -> tuple[tuple[int, int, int], float]:
    z, y, x = np.rint(point).astype(int)
    z0, z1 = max(0, z - radius), min(image.shape[0], z + radius + 1)
    y0, y1 = max(0, y - radius), min(image.shape[1], y + radius + 1)
    x0, x1 = max(0, x - radius), min(image.shape[2], x + radius + 1)
    neighborhood = image[z0:z1, y0:y1, x0:x1]
    neighborhood_mask = component_mask[z0:z1, y0:y1, x0:x1]
    masked_neighborhood = np.where(
        neighborhood_mask,
        neighborhood.astype(np.float32),
        -1.0,
    )
    peak_offset = np.unravel_index(
        np.argmax(masked_neighborhood), masked_neighborhood.shape
    )
    peak_coordinate = (
        z0 + peak_offset[0],
        y0 + peak_offset[1],
        x0 + peak_offset[2],
    )
    return peak_coordinate, float(masked_neighborhood[peak_offset])


def _get_bridge_ratio(
    image: np.ndarray,
    component_mask: np.ndarray,
    start: tuple[int, int, int],
    end: tuple[int, int, int],
) -> float:
    component_coordinates = np.argwhere(component_mask)
    z0, y0, x0 = component_coordinates.min(axis=0)
    z1, y1, x1 = component_coordinates.max(axis=0) + 1
    image_crop = image[z0:z1, y0:y1, x0:x1]
    mask_crop = component_mask[z0:z1, y0:y1, x0:x1]
    start_local = (start[0] - z0, start[1] - y0, start[2] - x0)
    end_local = (end[0] - z0, end[1] - y0, end[2] - x0)
    start_intensity = float(image_crop[start_local])
    end_intensity = float(image_crop[end_local])
    weaker_peak = min(start_intensity, end_intensity)
    if weaker_peak <= 0:
        return 0.0

    widest_path = np.full(image_crop.shape, -1.0, dtype=np.float32)
    widest_path[start_local] = start_intensity
    queue = [(-start_intensity, start_local)]
    visited: set[tuple[int, int, int]] = set()

    while queue:
        negative_width, current = heapq.heappop(queue)
        width = -negative_width
        if current in visited:
            continue
        visited.add(current)
        if current == end_local:
            return width / weaker_peak

        z, y, x = current
        for dz, dy, dx in (
            (1, 0, 0),
            (-1, 0, 0),
            (0, 1, 0),
            (0, -1, 0),
            (0, 0, 1),
            (0, 0, -1),
        ):
            neighbor = (z + dz, y + dy, x + dx)
            if (
                not all(
                    0 <= coordinate < dimension
                    for coordinate, dimension in zip(
                        neighbor, image_crop.shape, strict=True
                    )
                )
                or not mask_crop[neighbor]
            ):
                continue
            neighbor_width = min(width, float(image_crop[neighbor]))
            if neighbor_width > widest_path[neighbor]:
                widest_path[neighbor] = neighbor_width
                heapq.heappush(queue, (-neighbor_width, neighbor))

    return 0.0


def filter_spots_by_binary_mask_colocalization(
    spots_coords: np.ndarray,
    binary_mask: np.ndarray,
    focus_area_image: np.ndarray | None = None,
    raw_colocalization_image: np.ndarray | None = None,
    minimum_intensity_ratio: float = (
        DEFAULT_MINIMUM_COLOCALIZATION_INTENSITY_RATIO
    ),
) -> np.ndarray:
    filtered, _rejected = (
        filter_spots_by_binary_mask_colocalization_with_rejections(
            spots_coords,
            binary_mask,
            focus_area_image,
            raw_colocalization_image,
            minimum_intensity_ratio,
        )
    )
    return filtered


def filter_spots_by_binary_mask_colocalization_with_rejections(
    spots_coords: np.ndarray,
    binary_mask: np.ndarray,
    focus_area_image: np.ndarray | None = None,
    raw_colocalization_image: np.ndarray | None = None,
    minimum_intensity_ratio: float = (
        DEFAULT_MINIMUM_COLOCALIZATION_INTENSITY_RATIO
    ),
) -> tuple[np.ndarray, dict[str, np.ndarray]]:
    if not 0.0 <= minimum_intensity_ratio <= 1.0:
        raise ValueError(
            "minimum_intensity_ratio must be between 0 and 1, got "
            f"{minimum_intensity_ratio}"
        )
    empty = np.empty((0, 3), dtype=float)
    rejected_indices = {
        "insufficient_overlap": [],
        "low_intensity": [],
    }
    if len(spots_coords) == 0:
        return empty, {name: empty.copy() for name in rejected_indices}

    if focus_area_image is not None:
        if focus_area_image.shape != binary_mask.shape:
            raise ValueError(
                "focus_area_image and binary_mask shapes do not match: "
                f"{focus_area_image.shape} != {binary_mask.shape}"
            )
        component_labels, _ = ndimage.label(focus_area_image > 0)
    if raw_colocalization_image is not None and (
        raw_colocalization_image.shape != binary_mask.shape
    ):
        raise ValueError(
            "raw_colocalization_image and binary_mask shapes do not match: "
            f"{raw_colocalization_image.shape} != {binary_mask.shape}"
        )

    rounded = np.rint(spots_coords).astype(int)
    max_z, max_y, max_x = binary_mask.shape
    kept_indices: list[int] = []
    component_overlap_statistics: dict[int, tuple[int, float]] = {}

    for idx, (z, y, x) in enumerate(rounded):
        if not (0 <= z < max_z and 0 <= y < max_y and 0 <= x < max_x):
            rejected_indices["insufficient_overlap"].append(idx)
            continue

        if focus_area_image is None:
            overlaps_mask = binary_mask[z, y, x] > 0
            overlap_median_intensity = None
        else:
            component_id = component_labels[z, y, x]
            if component_id == 0:
                rejected_indices["insufficient_overlap"].append(idx)
                continue
            if component_id not in component_overlap_statistics:
                component_overlap = (component_labels == component_id) & (
                    binary_mask > 0
                )
                overlap_count = int(np.count_nonzero(component_overlap))
                overlap_median_intensity = (
                    float(
                        np.median(raw_colocalization_image[component_overlap])
                    )
                    if raw_colocalization_image is not None
                    and overlap_count > 0
                    else 0.0
                )
                component_overlap_statistics[component_id] = (
                    overlap_count,
                    overlap_median_intensity,
                )
            overlap_count, overlap_median_intensity = (
                component_overlap_statistics[component_id]
            )
            overlaps_mask = (
                overlap_count >= MIN_COMPONENT_COLOCALIZATION_OVERLAP_VOXELS
            )

        if not overlaps_mask:
            rejected_indices["insufficient_overlap"].append(idx)
            continue
        if (
            raw_colocalization_image is not None
            and float(raw_colocalization_image[z, y, x])
            < minimum_intensity_ratio * overlap_median_intensity
        ):
            rejected_indices["low_intensity"].append(idx)
            continue
        kept_indices.append(idx)

    points_array = np.asarray(spots_coords)
    rejected_points = {
        name: points_array[indices] if indices else empty.copy()
        for name, indices in rejected_indices.items()
    }
    return (
        points_array[kept_indices] if kept_indices else empty,
        rejected_points,
    )


def run_auto_count_on_paths(
    image_path: str | Path,
    segmentation_path: str | Path,
    output_dir: str | Path | None = None,
    use_gpu: bool = True,
    model_name: str = "synth_3d",
    spots_zyx_radii_pxl: tuple[float, float, float] = (5.0, 5.0, 5.0),
    normalize_spots_channel: bool = False,
    intensity_threshold: float | None = None,
    make_binary_mask: bool = False,
    normalization_input_min: float | None = None,
    normalization_input_max: float | None = None,
    normalization_output_max: int = 1000,
    colocalization_channels_filter: collections.abc.Sequence[str] = (),
    min_component_volume: int = 45,
    minimum_colocalization_intensity_ratio: float = (
        DEFAULT_MINIMUM_COLOCALIZATION_INTENSITY_RATIO
    ),
    spotiflow_detector: SpotiflowDetector | None = None,
):
    _ = (spots_zyx_radii_pxl,)
    _ = make_binary_mask
    if output_dir is None:
        raise ValueError("output_dir is required for automatic foci count.")

    (
        ref_image_zyx,
        processed_spots_image,
        segmentation_arr,
        spacing,
        preprocessing_stats,
        processed_image_path,
        preprocessing_stats_path,
    ) = run_auto_count_preprocessed_spots_on_paths(
        image_path=image_path,
        segmentation_path=segmentation_path,
        output_dir=output_dir,
        normalize_spots_channel=normalize_spots_channel,
        intensity_threshold=intensity_threshold,
        normalization_input_min=normalization_input_min,
        normalization_input_max=normalization_input_max,
        normalization_output_max=normalization_output_max,
    )
    requested_colocalization_channel_indices = (
        get_requested_colocalization_channel_indices(
            colocalization_channels_filter
        )
    )
    binary_mask_paths_by_channel: dict[int, Path] = {}
    for channel_index in requested_colocalization_channel_indices:
        binary_mask_paths_by_channel[channel_index] = (
            ensure_auto_count_binary_mask_output(
                image_path=image_path,
                output_dir=output_dir,
                channel_index=channel_index,
            )
        )

    output_dir_path = Path(output_dir)
    (
        _semantic_mask_path,
        unfiltered_points_layer_path,
        filtered_points_layer_path,
    ) = get_auto_count_output_paths(
        image_path=image_path,
        output_dir=output_dir_path,
    )
    if not unfiltered_points_layer_path.exists():
        if spotiflow_detector is None:
            run_spotiflow_subprocess(
                image_path=processed_image_path,
                output_csv_path=unfiltered_points_layer_path,
                model_name=model_name,
                use_gpu=use_gpu,
            )
        else:
            save_points_csv_for_napari(
                unfiltered_points_layer_path,
                spotiflow_detector.predict(processed_spots_image),
            )
    spots_coords = np.loadtxt(
        unfiltered_points_layer_path,
        delimiter=",",
        skiprows=1,
        usecols=(1, 2, 3),
    )
    if spots_coords.size == 0:
        spots_coords = np.empty((0, 3), dtype=float)
    elif spots_coords.ndim == 1:
        spots_coords = spots_coords.reshape(1, 3)
    spots_coords, rejected_points = (
        filter_spots_by_nonzero_and_component_volume_with_rejections(
            spots_coords,
            processed_spots_image=processed_spots_image,
            min_component_volume=min_component_volume,
        )
    )
    for filter_name, points in rejected_points.items():
        save_points_csv_for_napari(
            get_auto_count_rejected_points_path(
                image_path, output_dir, filter_name
            ),
            points,
        )
    for channel_index in requested_colocalization_channel_indices:
        binary_mask = np.asarray(
            imread(binary_mask_paths_by_channel[channel_index]),
            dtype=np.uint8,
        )
        raw_colocalization_image, _ = load_ome_zarr_image_zyx(
            image_path,
            channel_index=channel_index,
        )
        spots_coords, rejected_by_reason = (
            filter_spots_by_binary_mask_colocalization_with_rejections(
                spots_coords,
                binary_mask=binary_mask,
                focus_area_image=processed_spots_image,
                raw_colocalization_image=raw_colocalization_image,
                minimum_intensity_ratio=(
                    minimum_colocalization_intensity_ratio
                ),
            )
        )
        save_points_csv_for_napari(
            get_auto_count_rejected_points_path(
                image_path,
                output_dir,
                f"colocalization_channel_{channel_index + 1}",
            ),
            rejected_by_reason["insufficient_overlap"],
        )
        save_points_csv_for_napari(
            get_auto_count_rejected_points_path(
                image_path,
                output_dir,
                f"low_colocalization_intensity_channel_{channel_index + 1}",
            ),
            rejected_by_reason["low_intensity"],
        )
    save_points_csv_for_napari(filtered_points_layer_path, spots_coords)
    return (
        ref_image_zyx,
        segmentation_arr,
        spacing,
        processed_spots_image,
        preprocessing_stats,
        spots_coords,
        processed_image_path,
        preprocessing_stats_path,
        filtered_points_layer_path,
    )


def auto_count_outputs_exist(
    image_path: str | Path,
    output_dir: str | Path,
) -> bool:
    (
        _semantic_mask_path,
        _points_layer_path,
        filtered_points_layer_path,
    ) = get_auto_count_output_paths(
        image_path=image_path,
        output_dir=output_dir,
    )
    return filtered_points_layer_path.exists()
