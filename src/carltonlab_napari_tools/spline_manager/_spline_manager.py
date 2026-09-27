import configparser
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

from carltonlab_napari_tools._shared_variables import (
    REGIONS_CONFIGURATION_FILE_NAME,
)

SPLINE_DEFAULT_EDGE_WIDTH = 8
SPLINE_EDGE_COLOR = "#eb3434"
SPLINE_END_EXCLUSION_START = 0.95


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
    configuration_path = saving_path.parent / REGIONS_CONFIGURATION_FILE_NAME
    save_regions_configuration(
        configuration_path,
        interpolation_order=spline_layer._data_view.shapes[
            0
        ].interpolation_order,
    )
    return True


def _normalize(
    vector: np.ndarray,
    eps: float = 1e-12,
) -> np.ndarray:
    norm = np.linalg.norm(vector, axis=-1, keepdims=True)
    return vector / np.maximum(norm, eps)


def _line_intersection(
    point_one: np.ndarray,
    direction_one: np.ndarray,
    point_two: np.ndarray,
    direction_two: np.ndarray,
    eps: float = 1e-12,
) -> np.ndarray | None:
    def cross(first: np.ndarray, second: np.ndarray) -> float:
        return first[0] * second[1] - first[1] * second[0]

    denominator = cross(direction_one, direction_two)
    if abs(denominator) < eps:
        return None

    parameter = cross(point_two - point_one, direction_two) / denominator
    return point_one + parameter * direction_one


def _clean_consecutive_duplicates(
    points: np.ndarray,
    eps: float = 1e-6,
) -> np.ndarray:
    if len(points) == 0:
        return points

    cleaned = [points[0]]
    for point in points[1:]:
        if np.linalg.norm(point - cleaned[-1]) > eps:
            cleaned.append(point)
    return np.asarray(cleaned)


def stroke_polyline_to_polygon(
    points: np.ndarray,
    width: float,
    *,
    closed: bool = False,
    miter_limit: float = 4.0,
    drop_eps: float = 1e-6,
    start_join_dir: np.ndarray | None = None,
    end_join_dir: np.ndarray | None = None,
) -> np.ndarray:
    points = np.asarray(points, dtype=float)
    if points.ndim != 2 or points.shape[1] != 2:
        raise ValueError(f"Expected (N,2), got {points.shape}")
    if len(points) < 2:
        raise ValueError("Need at least 2 points")

    points = points[np.isfinite(points).all(axis=1)]
    if len(points) < 2:
        raise ValueError("Not enough finite points")

    differences = np.diff(points, axis=0)
    keep = np.concatenate(
        [[True], np.linalg.norm(differences, axis=1) > drop_eps]
    )
    points = points[keep]

    if (
        closed
        and len(points) >= 3
        and np.linalg.norm(points[0] - points[-1]) <= drop_eps
    ):
        points = points[:-1]

    number_of_points = len(points)
    if number_of_points < 2:
        raise ValueError("Degenerate after cleaning")

    half_width = 0.5 * float(width)
    segments = (
        np.roll(points, -1, axis=0) - points
        if closed
        else np.diff(points, axis=0)
    )
    directions = _normalize(segments)
    normals = np.stack(
        [-directions[:, 1], directions[:, 0]],
        axis=1,
    )

    def miter_cap(
        point: np.ndarray,
        direction_one: np.ndarray,
        direction_two: np.ndarray,
        side: float,
    ) -> np.ndarray | None:
        normal_one = np.array([-direction_one[1], direction_one[0]])
        normal_two = np.array([-direction_two[1], direction_two[0]])
        offset_one = point + side * half_width * normal_one
        offset_two = point + side * half_width * normal_two
        intersection = _line_intersection(
            offset_one,
            direction_one,
            offset_two,
            direction_two,
        )
        if intersection is None:
            return None
        if np.linalg.norm(intersection - point) > miter_limit * half_width:
            return None
        return intersection

    def build_side(side: float) -> np.ndarray:
        output: list[np.ndarray] = []

        if not closed:
            start_cap = None
            if start_join_dir is not None:
                first_direction = _normalize(start_join_dir.reshape(1, 2))[0]
                start_cap = miter_cap(
                    points[0],
                    first_direction,
                    directions[0],
                    side,
                )
            output.append(
                start_cap
                if start_cap is not None
                else points[0] + side * half_width * normals[0]
            )

            for index in range(1, number_of_points - 1):
                point = points[index]
                direction_one = directions[index - 1]
                direction_two = directions[index]
                offset_one = point + side * half_width * normals[index - 1]
                offset_two = point + side * half_width * normals[index]
                intersection = _line_intersection(
                    offset_one,
                    direction_one,
                    offset_two,
                    direction_two,
                )

                if intersection is None or (
                    np.linalg.norm(intersection - point)
                    > miter_limit * half_width
                ):
                    output.extend([offset_one, offset_two])
                else:
                    output.append(intersection)

            end_cap = None
            if end_join_dir is not None:
                final_direction = _normalize(end_join_dir.reshape(1, 2))[0]
                end_cap = miter_cap(
                    points[-1],
                    directions[-1],
                    final_direction,
                    side,
                )
            output.append(
                end_cap
                if end_cap is not None
                else points[-1] + side * half_width * normals[-1]
            )
            return _clean_consecutive_duplicates(np.asarray(output))

        for index in range(number_of_points):
            point = points[index]
            direction_one = directions[index - 1]
            direction_two = directions[index]
            offset_one = point + side * half_width * normals[index - 1]
            offset_two = point + side * half_width * normals[index]
            intersection = _line_intersection(
                offset_one,
                direction_one,
                offset_two,
                direction_two,
            )
            if intersection is None or (
                np.linalg.norm(intersection - point) > miter_limit * half_width
            ):
                output.extend([offset_one, offset_two])
            else:
                output.append(intersection)

        return _clean_consecutive_duplicates(np.asarray(output))

    left = build_side(+1.0)
    right = build_side(-1.0)
    polygon = np.vstack([left, right[::-1]])

    if not np.isfinite(polygon).all():
        raise ValueError("Polygon has NaN/inf")
    if len(polygon) < 3:
        raise ValueError("Polygon too small")
    return polygon


def expand_shape(
    source_layer: Shapes,
    expanded_layer: Shapes,
    shape_index: int,
    expanding_factor: int,
) -> None:
    if expanding_factor < 0:
        return

    original_data = source_layer._data_view.shapes[shape_index].data.copy()
    if original_data.ndim != 2 or original_data.shape[1] < 2:
        raise ValueError(
            f"Expected (N,D) with D>=2, got {original_data.shape}"
        )

    leading_data = None
    xy_data = original_data
    if original_data.shape[1] > 2:
        leading_data = original_data[:, :-2].copy()
        xy_data = original_data[:, -2:].copy()

    def direction_from_points(
        points: np.ndarray,
        at_start: bool,
    ) -> np.ndarray | None:
        if points.shape[0] < 2:
            return None
        xy = points[:, -2:] if points.shape[1] > 2 else points
        vector = xy[1] - xy[0] if at_start else xy[-1] - xy[-2]
        norm = np.linalg.norm(vector)
        if norm == 0:
            return None
        return vector / norm

    if expanding_factor == 0:
        new_xy_data = xy_data
        shape_type = "path"
    else:
        previous_direction = None
        next_direction = None
        if shape_index > 0:
            previous_data = np.asarray(
                source_layer._data_view.shapes[shape_index - 1].data,
                dtype=np.float32,
            )
            previous_direction = direction_from_points(
                previous_data,
                at_start=False,
            )
        if shape_index + 1 < len(source_layer._data_view.shapes):
            next_data = np.asarray(
                source_layer._data_view.shapes[shape_index + 1].data,
                dtype=np.float32,
            )
            next_direction = direction_from_points(
                next_data,
                at_start=True,
            )

        new_xy_data = stroke_polyline_to_polygon(
            xy_data,
            expanding_factor,
            start_join_dir=previous_direction,
            end_join_dir=next_direction,
        )
        shape_type = "polygon"

    if leading_data is not None:
        leading_row = leading_data[0:1, :]
        full_leading_data = np.repeat(
            leading_row,
            new_xy_data.shape[0],
            axis=0,
        )
        new_data = np.concatenate(
            [full_leading_data, new_xy_data],
            axis=1,
        )
    else:
        new_data = new_xy_data

    data_list = list(expanded_layer.data)
    data_list[shape_index] = new_data
    expanded_layer.data = data_list

    shape_types = list(expanded_layer.shape_type)
    if len(shape_types) == len(data_list):
        shape_types[shape_index] = shape_type
        expanded_layer.shape_type = shape_types

    expanded_layer.refresh()


def create_expanded_regions_layer(
    napari_viewer: ViewerModel,
    regions_layer: Shapes,
) -> Shapes:
    expanded_layer = napari_viewer.add_shapes(
        name="clt_expanded_regions_layer",
        ndim=2,
        edge_width=SPLINE_DEFAULT_EDGE_WIDTH,
        edge_color="#000000",
    )
    region_data = [
        np.array(shape.data, copy=True)
        for shape in regions_layer._data_view.shapes
    ]
    expanded_layer.add_paths(region_data)
    return expanded_layer


def save_regions_configuration(
    saving_path: Path,
    *,
    interpolation_order: int | None = None,
    number_of_regions: int | None = None,
    expansion_values: list[int] | None = None,
) -> None:
    config = configparser.ConfigParser()
    if saving_path.is_file():
        config.read(saving_path)
    if not config.has_section("Regions"):
        config["Regions"] = {}

    if interpolation_order is not None:
        config["Regions"]["interpolation_order"] = str(interpolation_order)

    if "number_of_regions" not in config["Regions"]:
        config["Regions"]["number_of_regions"] = "None"

    if number_of_regions is not None:
        config["Regions"]["number_of_regions"] = str(number_of_regions)
        for index in range(number_of_regions):
            config["Regions"].setdefault(
                f"region-{index + 1}",
                "None",
            )

    if expansion_values is not None:
        for index, value in enumerate(expansion_values):
            config["Regions"][f"region-{index + 1}"] = str(value)

    saving_path.parent.mkdir(parents=True, exist_ok=True)
    with saving_path.open("w", encoding="utf-8") as config_file:
        config.write(config_file)


def reset_regions_configuration(
    saving_path: Path,
    *,
    reset_number_of_regions: bool = False,
    reset_expansion_values: bool = False,
) -> None:
    config = configparser.ConfigParser()
    if saving_path.is_file():
        config.read(saving_path)
    if not config.has_section("Regions"):
        config["Regions"] = {}

    if reset_number_of_regions:
        config["Regions"]["number_of_regions"] = "None"
        for option in list(config["Regions"]):
            if option.startswith("region-"):
                del config["Regions"][option]
    elif reset_expansion_values:
        for option in list(config["Regions"]):
            if option.startswith("region-"):
                config["Regions"][option] = "None"

    saving_path.parent.mkdir(parents=True, exist_ok=True)
    with saving_path.open("w", encoding="utf-8") as config_file:
        config.write(config_file)


def load_regions_configuration(
    values_path: Path,
) -> tuple[int | None, int | None, tuple[int | None, ...] | None] | None:
    if not values_path.is_file():
        return None

    config = configparser.ConfigParser()
    config.read(values_path)
    if not config.has_section("Regions"):
        return None

    def get_optional_int(option: str) -> int | None:
        value = config.get("Regions", option, fallback="None")
        return None if value.strip().lower() == "none" else int(value)

    interpolation_order = get_optional_int("interpolation_order")
    number_of_regions = get_optional_int("number_of_regions")
    if number_of_regions is None:
        return interpolation_order, None, None

    expansion_values = tuple(
        get_optional_int(f"region-{index + 1}")
        for index in range(number_of_regions)
    )
    return interpolation_order, number_of_regions, expansion_values


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


def project_point_to_polyline(
    point_yx: np.ndarray,
    polyline_yx: np.ndarray,
) -> tuple[np.ndarray, float]:
    """Return the closest point and normalized arc position."""
    segment_starts = polyline_yx[:-1]
    segment_vectors = np.diff(polyline_yx, axis=0)
    segment_lengths_squared = np.sum(segment_vectors**2, axis=1)
    point_vectors = point_yx - segment_starts
    segment_positions = np.divide(
        np.sum(point_vectors * segment_vectors, axis=1),
        segment_lengths_squared,
        out=np.zeros_like(segment_lengths_squared),
        where=segment_lengths_squared > 0,
    )
    segment_positions = np.clip(segment_positions, 0.0, 1.0)
    projected_points = (
        segment_starts + segment_positions[:, None] * segment_vectors
    )
    distances_squared = np.sum((projected_points - point_yx) ** 2, axis=1)
    closest_segment = int(np.argmin(distances_squared))

    segment_lengths = np.sqrt(segment_lengths_squared)
    cumulative_lengths = np.concatenate([[0.0], np.cumsum(segment_lengths)])
    total_length = cumulative_lengths[-1]
    if total_length == 0.0:
        normalized_position = 0.0
    else:
        distance_on_polyline = (
            cumulative_lengths[closest_segment]
            + segment_positions[closest_segment]
            * segment_lengths[closest_segment]
        )
        normalized_position = float(distance_on_polyline / total_length)

    return projected_points[closest_segment], normalized_position


def assign_points_to_spline_regions(
    points_yx: np.ndarray,
    spline_shape: Shape,
    number_of_regions: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Project points onto the interpolated spline and assign regions."""
    if points_yx.ndim != 2 or points_yx.shape[1] != 2:
        raise ValueError("points_yx must have shape (N, 2)")
    if number_of_regions < 1:
        raise ValueError("number_of_regions must be positive")

    _, _, interpolated_spline = get_spline_object(spline_shape)
    final_tangent = interpolated_spline[-1] - interpolated_spline[-2]
    final_tangent /= np.linalg.norm(final_tangent)

    projected_points: list[np.ndarray] = []
    region_numbers: list[float] = []
    out_of_spline: list[bool] = []
    for point in points_yx:
        projected_point, normalized_position = project_point_to_polyline(
            point,
            interpolated_spline,
        )
        projected_points.append(projected_point)

        point_from_projection = point - projected_point
        is_past_spline_end = (
            normalized_position >= SPLINE_END_EXCLUSION_START
            and np.dot(point_from_projection, final_tangent) > 0.0
        )
        if is_past_spline_end:
            region_numbers.append(np.nan)
            out_of_spline.append(True)
            continue

        region_numbers.append(
            float(
                min(
                    number_of_regions,
                    int(normalized_position * number_of_regions) + 1,
                )
            )
        )
        out_of_spline.append(False)

    return (
        np.asarray(projected_points, dtype=np.float32),
        np.asarray(region_numbers, dtype=np.float32),
        np.asarray(out_of_spline, dtype=bool),
    )


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
