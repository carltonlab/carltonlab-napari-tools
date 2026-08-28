from pathlib import Path

import numpy as np
from napari.layers import Shapes
from napari.layers.shapes._shapes_models import Shape
from napari.layers.shapes._shapes_models.shape import (
    remove_path_duplicates,
)
from napari.utils.notifications import show_info
from napari.viewer import ViewerModel
from scipy.interpolate import splev, splprep

SPLINE_DEFAULT_EDGE_WIDTH = 8
SPLINE_EDGE_COLOR = "#eb3434"


def configure_spline_layer(spline_layer: Shapes) -> None:
    spline_layer.mode = "add_polyline"
    spline_layer.edge_color = SPLINE_EDGE_COLOR
    spline_layer.current_edge_color = SPLINE_EDGE_COLOR
    spline_layer.edge_width = SPLINE_DEFAULT_EDGE_WIDTH
    spline_layer.current_edge_width = SPLINE_DEFAULT_EDGE_WIDTH
    spline_layer.current_face_color = "transparent"


def load_spline_layer(
    napari_viewer: ViewerModel,
    spline_path: Path,
) -> Shapes | None:
    if not spline_path.is_file():
        return None

    opened_layers = napari_viewer.open(str(spline_path))
    if not isinstance(opened_layers, list):
        opened_layers = [opened_layers]

    for layer in opened_layers:
        if isinstance(layer, Shapes):
            configure_spline_layer(layer)
            napari_viewer.layers.selection.active = layer
            return layer

    return None


def save_spline_layer(
    spline_layer: Shapes,
    saving_path: Path,
) -> bool:
    if len(spline_layer._data_view.shapes) != 1:
        return False

    saving_path.parent.mkdir(parents=True, exist_ok=True)
    spline_layer.save(str(saving_path))
    return True


def verify_spline_interpolation(
    spline_layer: Shapes,
    interpolation_order: int,
) -> bool:
    shape_obj = spline_layer._data_view.shapes[0]
    spline_points = remove_path_duplicates(
        shape_obj.data_displayed,
        closed=True,
    )
    number_of_points = spline_points.shape[0]

    if interpolation_order >= number_of_points:
        show_info(
            "The number of points must be larger than "
            "the interpolation order"
        )
        return False

    return True


def get_spline_object(shape_object: Shape):
    interpolating_data = remove_path_duplicates(
        shape_object.data_displayed,
        closed=True,
    )
    interpolation_order = shape_object.interpolation_order
    data = interpolating_data.copy()
    is_closed = bool(shape_object._closed)

    if is_closed:
        data = np.append(data, data[:1], axis=0)

    tck, *_ = splprep(
        data.T,
        s=0,
        k=interpolation_order,
        per=shape_object._closed,
    )
    u = np.linspace(
        0,
        1,
        shape_object.interpolation_sampling * len(data),
    )
    points = np.stack(splev(u, tck), axis=1)

    if is_closed:
        points = points[:-1]

    return tck, is_closed, points.astype(np.float32)


def get_equal_length_u_breaks(
    tck,
    number_of_segments: int = 7,
    number_of_dense_samples: int = 5000,
    closed: bool = False,
):
    u_dense = np.linspace(
        0.0,
        1.0,
        number_of_dense_samples,
        endpoint=not closed,
        dtype=np.float64,
    )
    points = np.stack(splev(u_dense, tck), axis=1)

    distances = np.linalg.norm(np.diff(points, axis=0), axis=1)
    if closed:
        distances = np.concatenate(
            [distances, [np.linalg.norm(points[0] - points[-1])]]
        )

    cumulative_distance = np.concatenate([[0.0], np.cumsum(distances)])
    total_distance = cumulative_distance[-1]

    if total_distance == 0.0:
        return np.linspace(
            0.0,
            1.0,
            number_of_segments + 1,
            dtype=np.float64,
        )

    target_distances = np.linspace(
        0.0,
        total_distance,
        number_of_segments + 1,
    )
    u_for_interpolation = (
        np.concatenate([u_dense, [1.0]]) if closed else u_dense
    )
    return np.interp(
        target_distances,
        cumulative_distance,
        u_for_interpolation,
    )


def sample_polyline_from_u(
    tck,
    u: np.ndarray,
    dtype=np.float32,
) -> np.ndarray:
    points = np.stack(
        splev(u.astype(np.float64), tck),
        axis=1,
    )
    return points.astype(dtype)


def segment_paths_from_tck(
    tck,
    u_breaks: np.ndarray,
    points_per_segment: int = 50,
    closed: bool = False,
    dtype=np.float32,
) -> list[np.ndarray]:
    u_breaks = np.asarray(u_breaks, dtype=np.float64)
    number_of_segments = len(u_breaks) - 1
    segments: list[np.ndarray] = []

    for index, (start, end) in enumerate(
        zip(u_breaks[:-1], u_breaks[1:], strict=True)
    ):
        u = np.linspace(
            start,
            end,
            points_per_segment,
            dtype=np.float64,
        )
        points = sample_polyline_from_u(tck, u, dtype=dtype)

        if closed and index < number_of_segments - 1:
            points = points[:-1]

        segments.append(points)

    if (
        closed
        and segments
        and segments[-1].shape[0]
        and np.allclose(segments[-1][-1], segments[0][0])
    ):
        segments[-1] = segments[-1][:-1]

    return segments


def get_spline_equal_segments(
    shape_object: Shape,
    number_of_segments: int = 7,
    number_of_dense_samples: int = 5000,
    points_per_segment: int = 50,
) -> list[np.ndarray]:
    tck, is_closed, _ = get_spline_object(shape_object)
    u_breaks = get_equal_length_u_breaks(
        tck,
        number_of_segments,
        number_of_dense_samples,
        is_closed,
    )
    return segment_paths_from_tck(
        tck,
        u_breaks,
        points_per_segment,
        closed=is_closed,
    )


def display_splines(
    spline_layer: Shapes,
    interpolation_order: int,
    shape_index_list: tuple[int, ...] = (0,),
) -> None:
    number_of_shapes = len(spline_layer._data_view.shapes)
    if number_of_shapes <= 0 or not shape_index_list:
        return

    for shape_index in shape_index_list:
        if shape_index >= number_of_shapes:
            show_info(f"Cannot access shape with index: {shape_index}")
            continue

        if not verify_spline_interpolation(
            spline_layer,
            interpolation_order,
        ):
            continue

        shape_object = spline_layer._data_view.shapes[shape_index]
        if shape_object.interpolation_order == interpolation_order:
            continue

        shape_object.interpolation_order = interpolation_order
        shape_object.edge_width = SPLINE_DEFAULT_EDGE_WIDTH
        shape_data = shape_object.data
        spline_layer._data_view.edit(shape_index, shape_data)
        shape_object._update_displayed_data()

    spline_layer.edge_width = SPLINE_DEFAULT_EDGE_WIDTH
    spline_layer.refresh()
