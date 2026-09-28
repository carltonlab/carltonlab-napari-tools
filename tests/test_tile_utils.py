from pathlib import Path

import pytest

from carltonlab_napari_tools._tile_utils import (
    TileBoundingBox,
    find_tile_for_sbs,
    get_extracted_tile_path,
    get_tile_contrast_path,
    get_tile_positions_path,
    load_tile_bounding_boxes,
    write_tiles_config,
)


@pytest.mark.parametrize(
    ("tile_name", "channels", "expected_name"),
    [
        (
            "tile.dv",
            [1, 3, 2],
            "tile_kept_channels_1-3-2.ome.zarr",
        ),
        (
            "tile.ome.zarr",
            [],
            "tile.ome.zarr",
        ),
        (
            "tile_kept_channels_1-2.ome.zarr",
            [1, 3, 2],
            "tile_kept_channels_1-3-2.ome.zarr",
        ),
    ],
)
def test_get_extracted_tile_path(
    tile_name: str,
    channels: list[int],
    expected_name: str,
) -> None:
    tile_path = Path("/tmp") / tile_name

    assert get_extracted_tile_path(tile_path, channels).name == expected_name


def test_write_tiles_config(tmp_path: Path) -> None:
    tile_paths = [
        tmp_path / "tile_1.dv",
        tmp_path / "tile_2.dv",
    ]
    for tile_path in tile_paths:
        tile_path.touch()

    assert write_tiles_config(tmp_path, tile_paths)

    config_text = (tmp_path / "tiles.config").read_text()
    assert "file_0 = tile_1.dv" in config_text
    assert "file_1 = tile_2.dv" in config_text


def test_tile_positions_path() -> None:
    stitched_path = Path("stitched_image.ome.zarr")
    tiles_directory = Path("project") / "tiles"

    positions_path = get_tile_positions_path(
        stitched_path,
        tiles_directory,
    )

    assert positions_path == (
        tiles_directory / "stitched_image_tile_positions.csv"
    )


def test_tile_bounding_box_uses_exclusive_upper_bounds() -> None:
    bounding_box = TileBoundingBox(
        tile_path=Path("tile.ome.zarr"),
        bounds={
            "z": (0, 10),
            "y": (100, 200),
            "x": (300, 400),
        },
    )

    assert bounding_box.contains({"z": 0, "y": 100, "x": 300})
    assert not bounding_box.contains({"z": 10, "y": 100, "x": 300})
    assert not bounding_box.contains({"z": 0, "y": 200, "x": 300})
    assert not bounding_box.contains({"z": 0, "y": 100, "x": 400})


def test_load_tile_bounding_boxes_and_find_tile(
    tmp_path: Path,
) -> None:
    tiles_directory = tmp_path / "tiles"
    tiles_directory.mkdir()
    stitched_path = tmp_path / "sample_stitched.ome.zarr"

    positions_path = get_tile_positions_path(
        stitched_path,
        tiles_directory,
    )
    positions_path.write_text(
        "tile_name,z_min_px_index,z_max_px_index_exclusive,"
        "y_min_px_index,y_max_px_index_exclusive,"
        "x_min_px_index,x_max_px_index_exclusive\n"
        "tile_1.ome.zarr,0,10,100,200,300,400\n",
        encoding="utf-8",
    )

    bounding_boxes = load_tile_bounding_boxes(
        stitched_path,
        tiles_directory,
    )

    assert (
        find_tile_for_sbs(
            {
                "stitched_z_coord": 5,
                "stitched_y_coord": 150,
                "stitched_x_coord": 350,
            },
            bounding_boxes,
        )
        == tiles_directory / "tile_1.ome.zarr"
    )

    assert (
        find_tile_for_sbs(
            {
                "stitched_z_coord": 20,
                "stitched_y_coord": 150,
                "stitched_x_coord": 350,
            },
            bounding_boxes,
        )
        is None
    )


def test_get_tile_contrast_path() -> None:
    tile_path = Path("tile_kept_channels_1-3.ome.zarr")

    assert get_tile_contrast_path(tile_path).name == (
        "tile_kept_channels_1-3_contrasts.config"
    )
