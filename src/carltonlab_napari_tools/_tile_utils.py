import configparser
import csv
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from carltonlab_napari_tools._shared_variables import (
    TILE_CONTRASTS_FILE_NAME_SUFFIX,
    TILE_POSITIONS_FILE_NAME_SUFFIX,
)


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
