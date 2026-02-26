import os
from pathlib import Path
from typing import Literal

import numpy as np
from mrc import DVFile
from multiview_stitcher import ngff_utils
from multiview_stitcher import spatial_image_utils as si_utils
from napari.utils.notifications import show_error
from tifffile import imread


def parse_string_for_channels(parsing_string: str) -> list[int]:
    if parsing_string == "":
        return []
    channels: list[int] = []
    parts = [part for part in parsing_string.split(",") if part != ""]
    for part in parts:
        if "-" in part:
            start_text, end_text = part.split("-", maxsplit=1)
            if start_text == "" or end_text == "":
                return []
            start_value = int(start_text)
            end_value = int(end_text)
            if start_value > end_value:
                start_value, end_value = end_value, start_value
            channels.extend(range(start_value, end_value + 1))
        else:
            channels.append(int(part))
    sorted_channels = sorted(channels)
    no_repeat_channels = list(set(sorted_channels))
    return no_repeat_channels


def extract_channels(
    file_list: list[str],
    dir_list: list[str],
    extracting_channels_string: str,
    override_shape: list[str] | None = None,
    save_directory: str | None = None,
    stage_units: str = "unknown",
) -> bool:
    channels_raw = parse_string_for_channels(extracting_channels_string)
    if len(channels_raw) <= 0:
        show_error(
            f"The channel string {extracting_channels_string} resulted in no channels"
        )
        print(
            f"The channel string {extracting_channels_string} resulted in no channels"
        )
        return False
    channels = [channel - 1 for channel in channels_raw if channel > 0]
    if len(channels) <= 0:
        show_error(
            f"The channel string {extracting_channels_string} resulted in no channels"
        )
        print(
            f"The channel string {extracting_channels_string} resulted in no channels"
        )
        return False
    print("")
    print(f"Extracting channels: {channels_raw}")

    extracting_dicts: list[dict[str, str]] = []
    for file in file_list:
        extraction_dict: dict[str, str] | None = get_extraction_dict(
            file, channels_raw
        )
        if extraction_dict is not None:
            extracting_dicts.append(extraction_dict)
    for directory in dir_list:
        extracting_dicts.extend(
            _get_extraction_dicts_from_dir(directory, channels_raw)
        )

    for list_index in range(len(extracting_dicts)):
        extraction_dict = extracting_dicts[list_index]
        saving_dir: str = extraction_dict["saving_dir"]
        if save_directory is not None:
            saving_dir = save_directory
        channel_extraction(
            extraction_dict["file_path"],
            extraction_dict["file_type"],
            channels,
            saving_dir,
            extraction_dict["saving_file_name"],
            override_shape=override_shape,
            stage_units=stage_units,
        )

    return True


def channel_extraction(
    file_path: str,
    file_type: str,
    channels: list[int],
    saving_dir: str,
    saving_file_name: str,
    override_shape: list[str] | None = None,
    stage_units: str = "unknown",
) -> bool:
    os.makedirs(saving_dir, exist_ok=True)
    output_path = os.path.join(saving_dir, saving_file_name)

    if file_type == "dv":
        return _extract_from_dv(
            file_path,
            channels,
            output_path,
            override_shape=override_shape,
            stage_units=stage_units,
        )
    if file_type == "tiff":
        return _extract_from_tiff(
            file_path, channels, output_path, override_shape=override_shape
        )
    if file_type == "zarr":
        return _extract_from_ome_zarr(file_path, channels, output_path)
    show_error(f"Unsupported file type for {file_path}")
    return False


def get_extraction_dict(
    file_path: str, channels: list[int]
) -> dict[str, str] | None:
    returning_dict: dict[str, str] = {}
    returning_dict["file_path"] = file_path
    file_type = get_file_type(file_path)
    if file_type == "fail":
        return
    returning_dict["file_type"] = file_type
    path_object: Path = Path(file_path)
    dir_path: str = os.path.dirname(file_path)
    file_name_no_ext: str = path_object.stem
    channels_string: str = "_extracted_channels"
    for channel in channels:
        channels_string += f"_{channel}"
    saving_file_name: str = f"{file_name_no_ext}{channels_string}.ome.zarr"
    saving_file_path: str = os.path.join(dir_path, saving_file_name)
    if os.path.exists(saving_file_path):
        show_error(f"The file with path {saving_file_path} already exists")
        print(f"The file with path {saving_file_path} already exists")
        return
    returning_dict["saving_file_name"] = saving_file_name
    returning_dict["saving_dir"] = dir_path
    returning_dict["saving_file_path"] = saving_file_path
    return returning_dict


def get_file_type(
    file_path: str,
) -> Literal["dir", "zarr", "dv", "tiff", "fail"]:
    if file_path.endswith(".zarr") and os.path.isdir(file_path):
        return "zarr"
    if file_path.endswith(
        (".dv", ".dv_add_decon", ".zs", ".deconzs")
    ) and not os.path.isdir(file_path):
        return "dv"
    if file_path.endswith((".tif", ".tiff")) and not os.path.isdir(file_path):
        return "tiff"
    if os.path.isdir(file_path):
        return "dir"
    return "fail"


def _filter_channels(channels: list[int], n_channels: int) -> list[int]:
    return [channel for channel in channels if 0 <= channel < n_channels]


def _extract_from_dv(
    file_path: str,
    channels: list[int],
    output_path: str,
    override_shape: list[str] | None = None,
    stage_units: str = "unknown",
) -> bool:
    with DVFile(file_path) as dvf:
        header = dvf.hdr
        data = np.array(dvf.data, copy=True)

    data = _prepare_data_for_channels(data, override_shape, file_path)
    if data is None:
        return False

    selected = _filter_channels(channels, data.shape[0])
    if not selected:
        show_error(
            f"No requested channels found in {file_path}; "
            f"available 0-{data.shape[0] - 1}."
        )
        return False

    data = data[selected, ...]
    spacing = {
        "z": float(getattr(header, "dz", 1.0)),
        "y": float(getattr(header, "dy", 1.0)),
        "x": float(getattr(header, "dx", 1.0)),
    }
    translation = {
        "z": -float(getattr(header, "z0", 0.0)),
        "y": -float(getattr(header, "y0", 0.0)),
        "x": -float(getattr(header, "x0", 0.0)),
    }

    sim = si_utils.get_sim_from_array(
        data,
        dims=["c", "z", "y", "x"],
        scale=spacing,
        translation=translation,
        transform_key="stage_metadata",
    )
    ngff_utils.write_sim_to_ome_zarr(sim, output_path, overwrite=False)
    _write_stage_ini(output_path, translation, stage_units=stage_units)
    return True


def _extract_from_tiff(
    file_path: str,
    channels: list[int],
    output_path: str,
    override_shape: list[str] | None = None,
) -> bool:
    data = imread(file_path)
    data = _prepare_data_for_channels(data, override_shape, file_path)
    if data is None:
        return False

    selected = _filter_channels(channels, data.shape[0])
    if not selected:
        show_error(
            f"No requested channels found in {file_path}; "
            f"available 0-{data.shape[0] - 1}."
        )
        return False

    data = data[selected, ...]
    sim = si_utils.get_sim_from_array(
        data,
        dims=["c", "z", "y", "x"],
    )
    ngff_utils.write_sim_to_ome_zarr(sim, output_path, overwrite=False)
    return True


def _extract_from_ome_zarr(
    file_path: str, channels: list[int], output_path: str
) -> bool:
    sim = ngff_utils.read_sim_from_ome_zarr(file_path)
    if "c" not in sim.dims:
        show_error(f"{file_path} does not contain a channel axis.")
        return False

    n_channels = len(sim.coords["c"])
    selected = _filter_channels(channels, n_channels)
    if not selected:
        show_error(
            f"No requested channels found in {file_path}; "
            f"available 0-{n_channels - 1}."
        )
        return False

    sim = sim.isel(c=selected)
    ngff_utils.write_sim_to_ome_zarr(sim, output_path, overwrite=False)
    return True


def _write_stage_ini(
    output_path: str, translation: dict[str, float], stage_units: str
) -> None:
    ini_path = f"{output_path}.ini"
    lines = [
        "[metadata]",
        f"units={stage_units}",
        "",
        "[stage_translation]",
        f"z={translation['z']:.6f}",
        f"y={translation['y']:.6f}",
        f"x={translation['x']:.6f}",
        "",
    ]
    with open(ini_path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines))


def _prepare_data_for_channels(
    data: np.ndarray, override_dims: list[str] | None, file_path: str
) -> np.ndarray | None:
    if override_dims is None:
        if data.ndim == 5:
            dims = ["t", "z", "c", "y", "x"]
        elif data.ndim == 4:
            dims = ["z", "c", "y", "x"]
        elif data.ndim == 3:
            dims = ["c", "y", "x"]
        else:
            show_error(
                f"{file_path} has unsupported ndim {data.ndim}: {data.shape}"
            )
            return None
    else:
        dims = [str(dim) for dim in override_dims]
        if len(dims) != data.ndim:
            show_error(
                f"{file_path} override dims length {len(dims)} does not "
                f"match data ndim {data.ndim}."
            )
            return None

    if "c" not in dims or "y" not in dims or "x" not in dims:
        show_error(f"{file_path} dims must include c, y, x. Got {dims}.")
        return None

    if "t" in dims:
        t_index = dims.index("t")
        if data.shape[t_index] < 1:
            show_error(f"{file_path} has empty time axis.")
            return None
        data = np.take(data, indices=0, axis=t_index)
        dims = [dim for dim in dims if dim != "t"]

    target = ["c", "z", "y", "x"] if "z" in dims else ["c", "y", "x"]
    order = [dims.index(dim) for dim in target]
    data = np.transpose(data, axes=order)
    return data


def _get_extraction_dicts_from_dir(
    directory: str, channels: list[int]
) -> list[dict[str, str]]:
    path = Path(directory)
    if not path.is_dir():
        return []

    patterns = [
        "*.dv",
        "*.DV",
        "*.dv_add_decon",
        "*.zs",
        "*.deconzs",
        "*.tif",
        "*.tiff",
        "*.zarr",
    ]
    found_paths: list[Path] = []
    for pattern in patterns:
        found_paths.extend(path.rglob(pattern))

    extraction_dicts: list[dict[str, str]] = []
    for file_path in sorted(set(found_paths)):
        if file_path.suffix == ".zarr" and not file_path.is_dir():
            continue
        extraction_dict = get_extraction_dict(str(file_path), channels)
        if extraction_dict is not None:
            extraction_dicts.append(extraction_dict)
    return extraction_dicts
