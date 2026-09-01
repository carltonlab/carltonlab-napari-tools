from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray


@dataclass(frozen=True)
class NucleusCandidate:
    tile_index: int
    label_id: int
    stitched_center_zyx: tuple[float, float, float]
    voxel_count: int
    square_width: int
    square_height: int
    square_z_sections: int


def build_nucleus_candidates(
    labels_by_tile: dict[int, NDArray[np.uint32]],
    tile_offsets_yx: dict[int, tuple[float, float]],
) -> list[NucleusCandidate]:
    candidates: list[NucleusCandidate] = []

    for tile_index, labels in sorted(labels_by_tile.items()):
        if labels.ndim != 3:
            raise ValueError(
                f"Expected 3D ZYX labels for tile {tile_index}, "
                f"got shape {labels.shape}"
            )

        y_offset, x_offset = tile_offsets_yx[tile_index]
        label_ids = np.unique(labels)

        for label_id in label_ids:
            if label_id == 0:
                continue

            coordinates = np.argwhere(labels == label_id)
            if len(coordinates) == 0:
                continue

            z_min, y_min, x_min = coordinates.min(axis=0)
            z_max, y_max, x_max = coordinates.max(axis=0)

            object_width = int(x_max - x_min + 1)
            object_height = int(y_max - y_min + 1)
            object_z_sections = int(z_max - z_min + 1)

            center_z, center_y, center_x = coordinates.mean(axis=0)
            candidates.append(
                NucleusCandidate(
                    tile_index=tile_index,
                    label_id=int(label_id),
                    stitched_center_zyx=(
                        float(center_z),
                        float(center_y + y_offset),
                        float(center_x + x_offset),
                    ),
                    voxel_count=int(len(coordinates)),
                    square_width=object_width + 20,
                    square_height=object_height + 20,
                    square_z_sections=object_z_sections + 2,
                )
            )

    return candidates


def _point_is_inside_other_tile_object(
    candidate: NucleusCandidate,
    other_tile_index: int,
    labels_by_tile: dict[int, NDArray[np.uint32]],
    tile_offsets_yx: dict[int, tuple[float, float]],
) -> bool:
    if candidate.tile_index == other_tile_index:
        return False

    labels = labels_by_tile[other_tile_index]
    y_offset, x_offset = tile_offsets_yx[other_tile_index]
    z, y, x = candidate.stitched_center_zyx

    local_index = np.rint([z, y - y_offset, x - x_offset]).astype(int)

    if np.any(local_index < 0):
        return False
    if np.any(local_index >= np.asarray(labels.shape)):
        return False

    return bool(labels[tuple(local_index)] > 0)


def deduplicate_nucleus_candidates(
    candidates: list[NucleusCandidate],
    labels_by_tile: dict[int, NDArray[np.uint32]],
    tile_offsets_yx: dict[int, tuple[float, float]],
) -> list[NucleusCandidate]:
    surviving_candidates: list[NucleusCandidate] = []

    for candidate in candidates:
        conflicting_candidates = [
            other_candidate
            for other_candidate in candidates
            if other_candidate != candidate
            and _point_is_inside_other_tile_object(
                candidate,
                other_candidate.tile_index,
                labels_by_tile,
                tile_offsets_yx,
            )
        ]

        if any(
            other.voxel_count > candidate.voxel_count
            or (
                other.voxel_count == candidate.voxel_count
                and (
                    other.tile_index,
                    other.label_id,
                )
                < (
                    candidate.tile_index,
                    candidate.label_id,
                )
            )
            for other in conflicting_candidates
        ):
            continue

        surviving_candidates.append(candidate)

    return surviving_candidates
