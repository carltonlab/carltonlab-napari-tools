import configparser
import csv
import shutil
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from carltonlab_napari_tools._shared_variables import (
    SUPPORTED_STITCH_EXTENSIONS,
    TILE_CONTRASTS_FILE_NAME_SUFFIX,
    TILE_POSITIONS_FILE_NAME_SUFFIX,
    TILES_CONFIG_FILE_NAME,
    TILES_DIR_NAME,
)


def write_tiles_config(
    tiles_directory: Path,
    tile_paths: list[Path],
) -> bool:
    config = configparser.ConfigParser()
    config["tiles"] = {
        f"file_{index}": tile_path.name
        for index, tile_path in enumerate(tile_paths)
    }

    try:
        with (tiles_directory / TILES_CONFIG_FILE_NAME).open(
            "w",
            encoding="utf-8",
        ) as config_file:
            config.write(config_file)
    except OSError:
        return False

    return True


def ensure_tiles_config(project_path: Path) -> bool:
    tiles_directory = project_path / TILES_DIR_NAME
    config_path = tiles_directory / TILES_CONFIG_FILE_NAME

    if config_path.exists():
        return True

    tile_paths = sorted(
        path
        for path in tiles_directory.iterdir()
        if path.name.endswith(".ome.zarr")
        or (
            path.is_file()
            and any(
                path.name.endswith(extension)
                for extension in SUPPORTED_STITCH_EXTENSIONS
            )
        )
    )

    if not tile_paths:
        return False

    return write_tiles_config(tiles_directory, tile_paths)


def move_tiles(
    source_directory: Path,
    project_path: Path,
) -> bool:
    tiles_directory = project_path / TILES_DIR_NAME

    image_paths = [
        path
        for path in source_directory.iterdir()
        if path.name.endswith(".ome.zarr")
        or (
            path.is_file()
            and any(
                path.name.endswith(extension)
                for extension in SUPPORTED_STITCH_EXTENSIONS
            )
        )
    ]

    if not image_paths:
        return False

    destination_paths = [
        tiles_directory / image_path.name for image_path in image_paths
    ]
    if any(path.exists() for path in destination_paths):
        return False

    try:
        for image_path in image_paths:
            shutil.move(
                str(image_path),
                str(tiles_directory / image_path.name),
            )
    except OSError:
        return False

    return write_tiles_config(tiles_directory, image_paths)


@dataclass(frozen=True)
class TileBoundingBox:
    tile_path: Path
    bounds: dict[str, tuple[int, int]]

    def contains(
        self,
        coordinates: Mapping[str, float],
    ) -> bool:
        return all(
            minimum <= coordinates[dimension] < maximum
            for dimension, (minimum, maximum) in self.bounds.items()
            if dimension in coordinates
        )


def _strip_ome_zarr_suffix(path: Path) -> str:
    if path.name.endswith(".ome.zarr"):
        return path.name[: -len(".ome.zarr")]
    return path.stem


def get_tile_positions_path(
    stitched_image_path: Path,
    tiles_directory: Path,
) -> Path:
    stitched_stem = _strip_ome_zarr_suffix(stitched_image_path)
    return tiles_directory / (
        f"{stitched_stem}{TILE_POSITIONS_FILE_NAME_SUFFIX}"
    )


def load_tile_bounding_boxes(
    stitched_image_path: Path,
    tiles_directory: Path,
) -> dict[Path, TileBoundingBox]:
    positions_path = get_tile_positions_path(
        stitched_image_path,
        tiles_directory,
    )
    bounding_boxes: dict[Path, TileBoundingBox] = {}

    with positions_path.open(
        "r",
        encoding="utf-8",
        newline="",
    ) as positions_file:
        rows = csv.DictReader(positions_file)

        for row in rows:
            tile_name = (row.get("tile_name") or "").strip()
            if not tile_name:
                continue

            tile_path = tiles_directory / tile_name
            bounds: dict[str, tuple[int, int]] = {}

            for dimension in ("z", "y", "x"):
                minimum = row.get(f"{dimension}_min_px_index")
                maximum = row.get(f"{dimension}_max_px_index_exclusive")
                if minimum is None or maximum is None:
                    continue

                bounds[dimension] = (int(minimum), int(maximum))

            bounding_boxes[tile_path] = TileBoundingBox(
                tile_path=tile_path,
                bounds=bounds,
            )

    return bounding_boxes


def find_tile_for_sbs(
    sbs_feature: Mapping[str, object],
    tile_bounding_boxes: Mapping[Path, TileBoundingBox],
) -> Path | None:
    coordinates: dict[str, float] = {}
    for dimension in ("z", "y", "x"):
        value = sbs_feature.get(f"stitched_{dimension}_coord")
        if value is None:
            return None
        coordinates[dimension] = float(value)

    for bounding_box in tile_bounding_boxes.values():
        if bounding_box.contains(coordinates):
            return bounding_box.tile_path

    return None


def get_tile_contrast_path(tile_path: Path) -> Path:
    tile_stem = _strip_ome_zarr_suffix(tile_path)
    return tile_path.with_name(f"{tile_stem}{TILE_CONTRASTS_FILE_NAME_SUFFIX}")


def load_tile_contrasts(
    tile_path: Path,
) -> dict[int, tuple[float, float]]:
    contrast_path = get_tile_contrast_path(tile_path)
    if not contrast_path.is_file():
        return {}

    config = configparser.ConfigParser()
    config.read(contrast_path)

    if not config.has_section("ImageContrasts"):
        return {}

    number_of_channels = config.getint(
        "ImageContrasts",
        "NumberOfChannels",
    )
    contrasts: dict[int, tuple[float, float]] = {}

    for channel_index in range(number_of_channels):
        values = config.get(
            "ImageContrasts",
            f"channel-{channel_index + 1}",
        )
        minimum, maximum = (
            float(value.strip()) for value in values.split(",", maxsplit=1)
        )
        contrasts[channel_index] = (minimum, maximum)

    return contrasts
