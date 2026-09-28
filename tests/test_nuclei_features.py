from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from carltonlab_napari_tools.automatic_foci_count._nuclei_features import (
    NucleusCandidate,
    build_nucleus_candidates,
    build_nucleus_features_table,
    deduplicate_nucleus_candidates,
    save_nucleus_features_and_points,
)


def test_build_nucleus_candidates_calculates_centers_and_square_sizes() -> (
    None
):
    labels = np.zeros((5, 8, 10), dtype=np.uint32)
    labels[1:4, 2:5, 3:7] = 7

    candidates = build_nucleus_candidates(
        labels_by_tile={2: labels},
        tile_offsets_zyx={2: (10, 100, 200)},
    )

    assert candidates == [
        NucleusCandidate(
            tile_index=2,
            label_id=7,
            stitched_center_zyx=(12.0, 103.0, 204.5),
            voxel_count=36,
            square_width=24,
            square_height=23,
            square_z_sections=5,
        )
    ]


def test_build_nucleus_candidates_requires_3d_labels() -> None:
    labels = np.zeros((5, 6), dtype=np.uint32)

    with pytest.raises(ValueError, match="Expected 3D ZYX labels"):
        build_nucleus_candidates(
            labels_by_tile={1: labels},
            tile_offsets_zyx={1: (0, 0, 0)},
        )


def test_deduplicate_nucleus_candidates_keeps_larger_overlap() -> None:
    tile_a = np.zeros((3, 3, 3), dtype=np.uint32)
    tile_b = np.zeros((3, 3, 3), dtype=np.uint32)
    tile_a[1, 1, 1] = 1
    tile_b[1, 1, 1] = 2
    tile_b[1, 1, 2] = 2

    candidates = [
        NucleusCandidate(0, 1, (1.0, 1.0, 1.0), 1, 21, 21, 3),
        NucleusCandidate(1, 2, (1.0, 1.0, 1.5), 2, 22, 22, 3),
    ]

    surviving = deduplicate_nucleus_candidates(
        candidates=candidates,
        labels_by_tile={0: tile_a, 1: tile_b},
        tile_offsets_zyx={0: (0, 0, 0), 1: (0, 0, 0)},
    )

    assert surviving == [candidates[1]]


def test_build_nucleus_features_table_has_required_defaults() -> None:
    candidate = NucleusCandidate(
        tile_index=3,
        label_id=8,
        stitched_center_zyx=(4.0, 5.0, 6.0),
        voxel_count=12,
        square_width=30,
        square_height=31,
        square_z_sections=7,
    )

    features = build_nucleus_features_table([candidate])

    assert list(features.columns) == [
        "stitched_x_coord",
        "stitched_y_coord",
        "stitched_z_coord",
        "sbs_number",
        "source_tile_index",
        "source_label_id",
        "square_width",
        "square_height",
        "square_z_sections",
        "region",
        "scored_foci_number",
        "stitched_foci_coords",
    ]
    assert features.loc[0, "stitched_x_coord"] == 6.0
    assert features.loc[0, "sbs_number"] == 1
    assert pd.isna(features.loc[0, "region"])
    assert pd.isna(features.loc[0, "scored_foci_number"])
    assert features.loc[0, "stitched_foci_coords"] == "[]"


def test_save_nucleus_features_and_points_uses_project_structure(
    tmp_path: Path,
) -> None:
    candidate = NucleusCandidate(
        tile_index=1,
        label_id=4,
        stitched_center_zyx=(2.0, 3.0, 4.0),
        voxel_count=5,
        square_width=25,
        square_height=26,
        square_z_sections=4,
    )

    points_path, features_path = save_nucleus_features_and_points(
        candidates=[candidate],
        project_path=tmp_path,
    )

    assert points_path.is_file()
    assert features_path.is_file()
    assert points_path.parent.name == "pick_nuclei"
    assert "axis-0,axis-1,axis-2" in points_path.read_text()
    assert pd.read_csv(features_path).loc[0, "sbs_number"] == 1
