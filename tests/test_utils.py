from pathlib import Path

import pytest
import zarr

from carltonlab_napari_tools._utils import (
    get_complete_ome_zarr_paths,
    get_supported_image_extension,
    is_complete_ome_zarr,
    parse_channel_string,
    remove_incomplete_ome_zarr_paths,
    resolve_clsp_project_path,
    validate_image_directory,
)


@pytest.mark.parametrize(
    ("channel_string", "expected"),
    [
        ("1,3,2,2", [1, 3, 2, 2]),
        ("1-3", [1, 2, 3]),
        ("", []),
        ("1,,3", []),
        ("3-1", []),
    ],
)
def test_parse_channel_string(
    channel_string: str,
    expected: list[int],
) -> None:
    assert parse_channel_string(channel_string) == expected


@pytest.mark.parametrize(
    ("filename", "expected"),
    [
        ("image.dv", ".dv"),
        ("image.DV", ".dv"),
        ("image.ome.zarr", ".ome.zarr"),
        ("image.unknown", None),
    ],
)
def test_get_supported_image_extension(
    filename: str,
    expected: str | None,
) -> None:
    assert get_supported_image_extension(filename) == expected


def test_resolve_clsp_project_path_returns_existing_project(
    tmp_path: Path,
) -> None:
    project_path = tmp_path / "sample_clsp_project"
    project_path.mkdir()

    assert resolve_clsp_project_path(tmp_path) == project_path
    assert resolve_clsp_project_path(project_path) == project_path


def test_resolve_clsp_project_path_returns_none_without_project(
    tmp_path: Path,
) -> None:
    assert resolve_clsp_project_path(tmp_path) is None


def test_validate_image_directory_accepts_matching_files(
    tmp_path: Path,
) -> None:
    (tmp_path / "tile_1.dv").touch()
    (tmp_path / "tile_2.dv").touch()

    assert validate_image_directory(tmp_path) == (True, None)


def test_validate_image_directory_rejects_mixed_formats(
    tmp_path: Path,
) -> None:
    (tmp_path / "tile_1.dv").touch()
    (tmp_path / "tile_2.tif").touch()

    valid, error = validate_image_directory(tmp_path)

    assert not valid
    assert error is not None
    assert "does not match" in error


def test_incomplete_ome_zarr_is_not_complete(
    tmp_path: Path,
) -> None:
    incomplete_path = tmp_path / "broken.ome.zarr"
    incomplete_path.mkdir()

    assert not is_complete_ome_zarr(incomplete_path)
    assert get_complete_ome_zarr_paths(tmp_path) == []


def test_complete_ome_zarr_is_detected_and_incomplete_one_removed(
    tmp_path: Path,
) -> None:
    complete_path = tmp_path / "complete.ome.zarr"
    complete_group = zarr.open_group(str(complete_path), mode="w")
    complete_group.attrs["multiscales"] = [{}]

    incomplete_path = tmp_path / "incomplete.ome.zarr"
    incomplete_path.mkdir()

    assert is_complete_ome_zarr(complete_path)
    assert get_complete_ome_zarr_paths(tmp_path) == [complete_path]

    removed_paths = remove_incomplete_ome_zarr_paths(tmp_path)

    assert removed_paths == [incomplete_path]
    assert complete_path.is_dir()
    assert not incomplete_path.exists()
