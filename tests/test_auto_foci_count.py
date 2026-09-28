import numpy as np
import pytest

from carltonlab_napari_tools.automatic_foci_count._auto_foci_count import (
    filter_spots_by_binary_mask_colocalization_with_rejections,
    filter_spots_by_nonzero_and_component_volume_with_rejections,
    get_requested_colocalization_channel_indices,
)


@pytest.mark.parametrize(
    ("channels", "expected"),
    [
        (["1", "2", "3", "2"], [0, 1, 2]),
        ([" 1 ", "3"], [0, 2]),
        ([], []),
    ],
)
def test_get_requested_colocalization_channel_indices(
    channels: list[str],
    expected: list[int],
) -> None:
    assert get_requested_colocalization_channel_indices(channels) == expected


def test_filter_spots_by_component_volume_reports_rejections() -> None:
    processed = np.zeros((3, 4, 4), dtype=float)
    processed[1, 1, 1:3] = 1
    spots = np.asarray(
        [
            [1, 1, 1],
            [1, 0, 0],
            [4, 1, 1],
        ],
        dtype=float,
    )

    filtered, rejected = (
        filter_spots_by_nonzero_and_component_volume_with_rejections(
            spots,
            processed,
            min_component_volume=2,
        )
    )

    np.testing.assert_array_equal(filtered, spots[:1])
    np.testing.assert_array_equal(rejected["background"], spots[1:2])
    np.testing.assert_array_equal(rejected["out_of_bounds"], spots[2:3])


def test_filter_spots_by_component_volume_handles_empty_input() -> None:
    filtered, rejected = (
        filter_spots_by_nonzero_and_component_volume_with_rejections(
            np.empty((0, 3)),
            np.zeros((2, 2, 2)),
        )
    )

    assert filtered.shape == (0, 3)
    assert all(points.shape == (0, 3) for points in rejected.values())


def test_filter_spots_by_binary_mask_keeps_only_overlapping_points() -> None:
    binary_mask = np.zeros((3, 4, 4), dtype=bool)
    binary_mask[1, 1, 1] = True
    spots = np.asarray(
        [
            [1, 1, 1],
            [1, 2, 2],
        ],
        dtype=float,
    )

    filtered, rejected = (
        filter_spots_by_binary_mask_colocalization_with_rejections(
            spots,
            binary_mask,
        )
    )

    np.testing.assert_array_equal(filtered, spots[:1])
    np.testing.assert_array_equal(
        rejected["insufficient_overlap"],
        spots[1:2],
    )


def test_filter_spots_by_binary_mask_validates_ratio_and_shapes() -> None:
    spots = np.asarray([[1, 1, 1]], dtype=float)
    binary_mask = np.zeros((3, 3, 3), dtype=bool)

    with pytest.raises(ValueError, match="between 0 and 1"):
        filter_spots_by_binary_mask_colocalization_with_rejections(
            spots,
            binary_mask,
            minimum_intensity_ratio=1.1,
        )

    with pytest.raises(ValueError, match="shapes do not match"):
        filter_spots_by_binary_mask_colocalization_with_rejections(
            spots,
            binary_mask,
            focus_area_image=np.zeros((2, 2, 2)),
        )
