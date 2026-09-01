import configparser
from pathlib import Path

from multiview_stitcher import ngff_utils
from napari.utils.notifications import show_error

from carltonlab_napari_tools._shared_variables import (
    EXTRACTED_CHANNELS_FILE_NAME,
    TILES_CONFIG_FILE_NAME,
    TILES_DIR_NAME,
)
from carltonlab_napari_tools._tile_utils import get_extracted_tile_path
from carltonlab_napari_tools.image_resolver._image_resolver import (
    resolve_spatial_data,
)


def extract_channels_to_ome_zarr(
    input_path: Path,
    output_path: Path,
    channels: list[int],
) -> bool:
    if not input_path.exists():
        show_error(f"File {input_path} does not exist.")
        return False
    if output_path.exists():
        show_error(f"Output {output_path} already exists.")
        return False

    output_path.parent.mkdir(parents=True, exist_ok=True)

    data = resolve_spatial_data(input_path)
    if data is None:
        show_error(f"Could not open image {input_path}")
        return False

    expected_dims = ("t", "c", "z", "y", "x")
    if tuple(data.dims) != expected_dims:
        show_error(
            f"Expected image dimensions {expected_dims}, but got {tuple(data.dims)}"
        )
        return False

    if data.sizes["t"] != 1:
        show_error(f"Expected one time point, but got {data.sizes['t']}.")
        return False

    channel_count = data.sizes["c"]

    if channels:
        invalid_channels = [
            channel
            for channel in channels
            if channel < 1 or channel > channel_count
        ]
        if invalid_channels:
            show_error(
                f"Invalid channel(s): {', '.join(map(str, invalid_channels))}. "
                f"Expected 1-{channel_count}."
            )
            return False

        selected_0base_channels = [channel - 1 for channel in channels]
        data = data.isel(c=selected_0base_channels)

        channel_labels = [str(label) for label in data.coords["c"].values]
        label_counts: dict[str, int] = {}
        unique_channel_labels: list[str] = []
        for label in channel_labels:
            occurrence = label_counts.get(label, 0) + 1
            label_counts[label] = occurrence
            unique_channel_labels.append(
                label if occurrence == 1 else f"{label}_{occurrence}"
            )
        data = data.assign_coords(c=unique_channel_labels)

    ngff_utils.write_sim_to_ome_zarr(
        data,
        output_path,
        downscale_factors_per_spatial_dim={
            "z": 2,
            "y": 2,
            "x": 2,
        },
        overwrite=False,
    )

    return True


def extract_project_tiles(
    project_path: Path,
    channels: list[int],
) -> list[Path] | None:
    tiles_path = project_path / TILES_DIR_NAME
    tiles_config_path = tiles_path / TILES_CONFIG_FILE_NAME

    config = configparser.ConfigParser()
    try:
        config.read(tiles_config_path)
        tile_names = [filename for _, filename in config.items("tiles")]
    except (configparser.Error, OSError, ValueError) as exc:
        show_error(f"Could not read {tiles_config_path.name}: {exc}")
        return None

    if not tile_names:
        show_error(f"No tiles listed in {tiles_config_path.name}.")
        return None

    extracted_paths: list[Path] = []
    for tile_number, tile_name in enumerate(tile_names, start=1):
        tile_path = tiles_path / tile_name
        output_path = get_extracted_tile_path(tile_path, channels)

        if output_path.exists():
            extracted_paths.append(output_path)
            continue

        print(
            f"\nExtracting tile: {output_path.name} "
            f"({tile_number}/{len(tile_names)})",
            flush=True,
        )
        if not extract_channels_to_ome_zarr(
            tile_path,
            output_path,
            channels,
        ):
            return None

        print("Done extracting tile\n", flush=True)
        extracted_paths.append(output_path)

    channels_config = configparser.ConfigParser()
    channels_config["channels"] = {
        "kept": (
            "all"
            if not channels
            else ",".join(str(channel) for channel in channels)
        )
    }
    channels_config_path = tiles_path / EXTRACTED_CHANNELS_FILE_NAME
    try:
        with channels_config_path.open("w", encoding="utf-8") as config_file:
            channels_config.write(config_file)
    except OSError as exc:
        show_error(f"Could not write {channels_config_path.name}: {exc}")
        return None

    return extracted_paths
