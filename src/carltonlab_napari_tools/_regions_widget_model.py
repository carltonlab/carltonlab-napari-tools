import os
from configparser import ConfigParser
from typing import Literal

import numpy as np
from napari.layers import Shapes
from napari.layers.shapes._shapes_models import Shape
from napari.layers.shapes._shapes_models.shape import remove_path_duplicates
from napari.utils.notifications import show_info
from napari.viewer import ViewerModel
from scipy.interpolate import splev, splprep

from carltonlab_napari_tools._model import (
    open_csv_as_shape_layer,
    save_layer_as_csv,
)
from carltonlab_napari_tools._shared_variables import (
    EDITED_REGIONS_EXPANSION_VALUES_FILE_NAME,
    EDITED_REGIONS_FILE_NAME,
    REGIONS_DIR_NAME,
)
from carltonlab_napari_tools._shared_widgets import confirm_dialog

REGIONS_LAYER_DEFAULT_NAME = "clt_regions_layer"
SPLINE_LAYER_DEFAULT_NAME = "clt_spline_layer"
REGIONS_DEFAULT_WIDTH = 3
REGION_COLOR = "#27adf5"

DEFAULT_PROJECT_NAME = "cl_score_points_project"

SPLINE_FILE_NAME = "clt_spline_layer.csv"
REGIONS_FILE_NAME = "clt_regions_layer.csv"

EDITED_REGIONS_LAYER_NAME = "clt_edited_regions_layer"
EDITED_REGION_COLOR = "#000000"


def open_project(
    napari_viewer: ViewerModel, image_path: str
) -> Literal["load", "failed"] | tuple[str, Shapes]:
    parent_dir: str = os.path.dirname(image_path)
    searching_project_path: str = os.path.join(
        parent_dir, DEFAULT_PROJECT_NAME
    )
    if os.path.exists(searching_project_path):
        show_info(
            f"The image is part of a project with path {searching_project_path} already exists. Loading project"
        )
        return "load"
    returning_tuple: tuple[str, Shapes] | None = create_new_project(
        napari_viewer, image_path
    )
    if returning_tuple is None:
        return "failed"
    return returning_tuple


def create_new_project(
    napari_viewer: "ViewerModel",
    file_path: str,
) -> tuple[str, Shapes] | None:
    parent_dir = os.path.dirname(file_path)
    regions_dir_path: str = os.path.join(
        parent_dir, DEFAULT_PROJECT_NAME, REGIONS_DIR_NAME
    )
    if not os.path.exists(regions_dir_path):
        showing_message: str = (
            f"_regions_widget_model.py: Failed to load project {regions_dir_path}. ERROR"
        )
        show_info(showing_message)
        print(showing_message)
        return None
    spline_layer: Shapes = napari_viewer.add_shapes(
        name=SPLINE_LAYER_DEFAULT_NAME, ndim=2
    )
    return (regions_dir_path, spline_layer)


def load_project_files(
    napari_viewer: ViewerModel, image_path: str
) -> (
    tuple[str, Shapes, Shapes | None, tuple[Shapes, tuple[int, ...]] | None]
    | None
):
    parent_dir = os.path.dirname(image_path)
    regions_path = os.path.join(
        parent_dir,
        DEFAULT_PROJECT_NAME,
        REGIONS_DIR_NAME,
    )
    returning_list = []
    returning_list.append(regions_path)
    spline_layer_path: str = os.path.join(
        parent_dir, DEFAULT_PROJECT_NAME, REGIONS_DIR_NAME, SPLINE_FILE_NAME
    )
    if not os.path.exists(spline_layer_path):
        show_info("No spline layer file found")
        spline_layer = napari_viewer.add_shapes(
            name="ctl_spline_layer", ndim=2
        )
    else:
        spline_layer = open_csv_as_shape_layer(
            napari_viewer,
            spline_layer_path,
        )
    returning_list.append(spline_layer)
    regions_layer_path = os.path.join(
        parent_dir, DEFAULT_PROJECT_NAME, REGIONS_DIR_NAME, REGIONS_FILE_NAME
    )
    if os.path.exists(regions_layer_path):
        regions_layer = open_csv_as_shape_layer(
            napari_viewer,
            regions_layer_path,
        )
    else:
        regions_layer = None
    returning_list.append(regions_layer)
    edited_regions_path = os.path.join(
        parent_dir,
        DEFAULT_PROJECT_NAME,
        REGIONS_DIR_NAME,
        EDITED_REGIONS_FILE_NAME,
    )
    edited_region_values_file_path: str = os.path.join(
        parent_dir,
        DEFAULT_PROJECT_NAME,
        REGIONS_DIR_NAME,
        EDITED_REGIONS_EXPANSION_VALUES_FILE_NAME,
    )
    edited_regions_layer: Shapes | None
    edited_regions_tuple: tuple[Shapes, tuple[int, ...]] | None = None
    if os.path.exists(edited_regions_path) and os.path.exists(
        edited_region_values_file_path
    ):
        edited_regions_layer = open_csv_as_shape_layer(
            napari_viewer,
            edited_regions_path,
        )
        appending_layer: Shapes
        if edited_regions_layer is None:
            edited_regions_tuple = None
        else:
            appending_layer: Shapes = edited_regions_layer
            expansion_values: tuple[int, ...] = (
                open_edited_regions_expansion_values(
                    edited_region_values_file_path
                )
            )
            edited_regions_tuple = (appending_layer, expansion_values)
    returning_list.append(edited_regions_tuple)
    return tuple(returning_list)


def save_shapes_layer(
    napari_viewer: ViewerModel,
    spline_layer: Shapes,
    saving_dir: str,
    saving_file_name: str,
) -> bool:
    # spline_file_path: str = os.path.join(saving_dir, SPLINE_FILE_NAME)
    shapes_layer_file_path: str = os.path.join(saving_dir, saving_file_name)
    if os.path.exists(shapes_layer_file_path):
        dialog_result: bool = confirm_dialog(
            napari_viewer,
            f"{saving_file_name} file already exists, overwrite?",
        )
        if not dialog_result:
            return False
        else:
            os.remove(shapes_layer_file_path)
    save_layer_as_csv(spline_layer, shapes_layer_file_path)
    return True


def verify_spline_interpolation(
    spline_layer: Shapes,
    comparing_interpolation_order: int,
) -> bool:
    shape_obj = spline_layer._data_view.shapes[0]
    spline_points = remove_path_duplicates(
        shape_obj.data_displayed, closed=True
    )
    n_points = spline_points.shape[0]
    if comparing_interpolation_order >= n_points:
        show_info(
            "The number of points must be larger than the interpolation order"
        )
        return False
    return True


def get_spline_object(shape_object: Shape):
    interpolating_data = remove_path_duplicates(
        shape_object.data_displayed, closed=True
    )
    interpolation_order = shape_object.interpolation_order
    data = interpolating_data.copy()
    is_closed = bool(shape_object._closed)
    if is_closed:
        data = np.append(data, data[:1], axis=0)
    tck, *_ = splprep(
        data.T, s=0, k=interpolation_order, per=shape_object._closed
    )
    u = np.linspace(0, 1, shape_object.interpolation_sampling * len(data))  # type: ignore
    points = np.stack(splev(u, tck), axis=1)
    if is_closed:
        points = points[:-1]
    points = points.astype(np.float32)
    return tck, is_closed, points


def get_equal_length_u_breaks(tck, n_segments=7, n_dense=5000, closed=False):
    # For closed curves, use [0, 1) to avoid duplicated endpoint
    u_dense = np.linspace(
        0.0, 1.0, n_dense, endpoint=not closed, dtype=np.float64
    )
    pts = np.stack(splev(u_dense, tck), axis=1)

    d = np.linalg.norm(np.diff(pts, axis=0), axis=1)
    if closed:
        # close the polyline to measure full loop length
        d = np.concatenate([d, [np.linalg.norm(pts[0] - pts[-1])]])
    s = np.concatenate([[0.0], np.cumsum(d)])
    total = s[-1]
    if total == 0.0:
        return np.linspace(0.0, 1.0, n_segments + 1, dtype=np.float64)
    targets = np.linspace(0.0, total, n_segments + 1)
    u_for_interp = np.concatenate([u_dense, [1.0]]) if closed else u_dense
    u_breaks = np.interp(targets, s, u_for_interp)
    if closed:
        # last breakpoint is 1.0 which is same as 0.0; you can drop it if you want wrap-around handling
        pass
    return u_breaks


def sample_polyline_from_u(tck, u: np.ndarray, dtype=np.float32) -> np.ndarray:
    pts = np.stack(splev(u.astype(np.float64), tck), axis=1)
    return pts.astype(dtype)


def segment_paths_from_tck(
    tck,
    u_breaks: np.ndarray,
    points_per_segment: int = 50,
    closed: bool = False,
    dtype=np.float32,
) -> list[np.ndarray]:
    """
    Returns 7 polylines (or n_segments) as list of arrays shaped (N, dim),
    suitable for napari Shapes 'path' or 'polygon' data.
    """
    u_breaks = np.asarray(u_breaks, dtype=np.float64)
    n_segments = len(u_breaks) - 1

    segs: list[np.ndarray] = []

    if not closed:
        for a, b in zip(u_breaks[:-1], u_breaks[1:], strict=True):
            u = np.linspace(a, b, points_per_segment, dtype=np.float64)
            segs.append(sample_polyline_from_u(tck, u, dtype=dtype))
        return segs

    # closed curve:
    # assume u_breaks includes 0 and 1 (or very close). We'll make segments on [0,1]
    # and drop duplicate end point per segment to avoid repeated vertices.
    for i, (a, b) in enumerate(zip(u_breaks[:-1], u_breaks[1:], strict=True)):
        u = np.linspace(a, b, points_per_segment, dtype=np.float64)
        pts = sample_polyline_from_u(tck, u, dtype=dtype)

        # avoid duplicate join point between consecutive segments
        if i < n_segments - 1:
            pts = pts[:-1]
        segs.append(pts)

    # Optionally also remove the very last point if it duplicates the first
    # (depends on whether u_breaks[-1] == 1.0 exactly and per=True)
    if (
        len(segs)
        and segs[-1].shape[0]
        and np.allclose(segs[-1][-1], segs[0][0])
    ):
        segs[-1] = segs[-1][:-1]

    return segs


def get_spline_equal_segments(
    shape_object: Shape,
    number_of_segments: int = 7,
    n_dense=5000,
    points_per_segment: int = 50,
):
    tck, is_closed, spline_points = get_spline_object(shape_object)
    u_breaks = get_equal_length_u_breaks(
        tck,
        number_of_segments,
        n_dense,
        is_closed,
    )
    paths = segment_paths_from_tck(
        tck, u_breaks, points_per_segment, closed=is_closed
    )
    return paths


def create_regions_layer(
    napari_viewer: ViewerModel,
    spline_points: list[np.ndarray],
    image_layer_dims: int,
) -> Shapes:
    print(f"Creating layer with dim: {image_layer_dims}")
    regions_layer = napari_viewer.add_shapes(
        name=REGIONS_LAYER_DEFAULT_NAME, ndim=2
    )
    spline_points = rectify_path_dimensions(spline_points, image_layer_dims)
    regions_layer.add_paths(
        spline_points,
        edge_width=REGIONS_DEFAULT_WIDTH,
        edge_color=REGION_COLOR,
    )
    return regions_layer


def rectify_path_dimensions(
    spline_points: list[np.ndarray], image_layer_dims: int
) -> list[np.ndarray]:
    target_dims = image_layer_dims
    if target_dims < 2:
        raise ValueError(f"image_layer_dims must be >= 2, got {target_dims}")

    out: list[np.ndarray] = []

    for i, p in enumerate(spline_points):
        p = np.asarray(p, dtype=np.float32)

        if p.ndim != 2:
            raise ValueError(f"segment {i}: expected (N,D), got {p.shape}")

        n, d = p.shape
        if d < 2:
            raise ValueError(
                f"segment {i}: expected at least 2 cols, got {p.shape}"
            )

        # take the spline coords from the first two columns (your existing format)
        xy = p[:, :2]

        if target_dims == 2:
            out.append(xy)
            continue

        full = np.zeros((n, target_dims), dtype=np.float32)
        full[:, -2:] = xy  # last two axes are the spline points
        out.append(full)

    return out


def create_edited_regions_layer(
    napari_viewer: "ViewerModel", regions_layer: Shapes, image_layer_dims: int
) -> Shapes:
    edited_regions_layer = napari_viewer.add_shapes(
        name=EDITED_REGIONS_LAYER_NAME,
        edge_width=REGIONS_DEFAULT_WIDTH,
        edge_color=EDITED_REGION_COLOR,
        ndim=image_layer_dims,
    )
    data_list = []
    for shape_obj in regions_layer._data_view.shapes:
        shape_obj_data = np.array(shape_obj.data, copy=True)
        data_list.append(shape_obj_data)
    data_list = rectify_path_dimensions(data_list, image_layer_dims)
    edited_regions_layer.add_paths(data_list)
    return edited_regions_layer


def display_splines(
    spline_layer: Shapes,
    setting_interpolation_order: int,
    shape_index_list: tuple[int] = (0,),
) -> None:
    number_of_shapes_in_layer: int = len(spline_layer._data_view.shapes)
    number_of_changing_shapes: int = len(shape_index_list)
    if number_of_shapes_in_layer <= 0 or number_of_changing_shapes <= 0:
        return
    for shape_index in shape_index_list:
        if shape_index >= number_of_shapes_in_layer:
            show_info(f"Cannot access shape with index: {shape_index}")
            continue
        shape_object = spline_layer._data_view.shapes[shape_index]
        if not verify_spline_interpolation(
            spline_layer, setting_interpolation_order
        ):
            continue
        if shape_object.interpolation_order == setting_interpolation_order:
            continue
        shape_object.interpolation_order = setting_interpolation_order
        shape_object.edge_width = REGIONS_DEFAULT_WIDTH
        shape_data = shape_object.data
        spline_layer._data_view.edit(shape_index, shape_data)
        shape_object._update_displayed_data()
    spline_layer.edge_width = REGIONS_DEFAULT_WIDTH
    spline_layer.refresh()
    return


def save_regions_layer(regions_layer: Shapes, regions_dir_path: str) -> None:
    regions_layer_path = os.path.join(regions_dir_path, REGIONS_FILE_NAME)
    save_layer_as_csv(regions_layer, regions_layer_path)


def expand_shape(
    spline_layer: Shapes,
    expanded_shapes_layer: Shapes,
    shape_index: int,
    expanding_factor: int,
) -> None:
    setting_type = "polygon"
    if expanding_factor < 0:
        return

    original_shape_data = spline_layer._data_view.shapes[
        shape_index
    ].data.copy()

    # If data is (N, >2), treat last two columns as the 2D geometry (YX),
    # and preserve the leading columns as metadata dims (e.g. Z,C).
    if original_shape_data.ndim != 2 or original_shape_data.shape[1] < 2:
        raise ValueError(
            f"Expected (N,D) with D>=2, got {original_shape_data.shape}"
        )

    leading = None
    xy = original_shape_data

    if original_shape_data.shape[1] > 2:
        leading = original_shape_data[:, :-2].copy()
        xy = original_shape_data[:, -2:].copy()

    def _direction_from_points(
        points: np.ndarray, at_start: bool
    ) -> np.ndarray | None:
        if points.shape[0] < 2:
            return None
        xy = points[:, -2:] if points.shape[1] > 2 else points
        vec = xy[1] - xy[0] if at_start else xy[-1] - xy[-2]
        norm = np.linalg.norm(vec)
        if norm == 0:
            return None
        return vec / norm

    if expanding_factor == 0:
        # keep as path
        new_polyline_data_xy = xy
        setting_type = "path"
    else:
        prev_dir = None
        next_dir = None
        if shape_index > 0:
            prev_data = spline_layer._data_view.shapes[shape_index - 1].data
            prev_data = np.asarray(prev_data, dtype=np.float32)
            prev_dir = _direction_from_points(prev_data, at_start=False)
        if shape_index + 1 < len(spline_layer._data_view.shapes):
            next_data = spline_layer._data_view.shapes[shape_index + 1].data
            next_data = np.asarray(next_data, dtype=np.float32)
            next_dir = _direction_from_points(next_data, at_start=True)

        new_polyline_data_xy = stroke_polyline_to_polygon(
            xy,
            expanding_factor,
            start_join_dir=prev_dir,
            end_join_dir=next_dir,
        )

    # Reattach leading dims (set them to the same values as the original)
    if leading is not None:
        # For polygons, the number of vertices changes, so broadcast the leading dims.
        lead_row = leading[0:1, :]  # (1, D-2)
        lead_full = np.repeat(lead_row, new_polyline_data_xy.shape[0], axis=0)
        new_polyline_data = np.concatenate(
            [lead_full, new_polyline_data_xy], axis=1
        )
    else:
        new_polyline_data = new_polyline_data_xy

    data_list = list(expanded_shapes_layer.data)
    data_list[shape_index] = new_polyline_data
    expanded_shapes_layer.data = data_list

    shape_types = list(expanded_shapes_layer.shape_type)
    if len(shape_types) == len(data_list):
        shape_types[shape_index] = setting_type
        expanded_shapes_layer.shape_type = shape_types

    expanded_shapes_layer.refresh()


# def expand_shape(
#    spline_layer: Shapes,
#    expanded_shapes_layer: Shapes,
#    shape_object: Shape,
#    shape_index: int,
#    expanding_factor: int,
# ) -> None:
#    setting_type = "polygon"
#    if expanding_factor < 0:
#        return
#    original_shape_data = spline_layer._data_view.shapes[
#        shape_index
#    ].data.copy()
#    if expanding_factor == 0:
#        new_polyline_data = original_shape_data.copy()
#        setting_type = "path"
#    else:
#        new_polyline_data = stroke_polyline_to_polygon(
#            original_shape_data, expanding_factor
#        )
#    expanded_shapes_layer._data_view.edit(
#        shape_index, new_polyline_data, new_type=setting_type
#    )
#    shape_object._update_displayed_data()
#    expanded_shapes_layer.refresh()


def _normalize(v: np.ndarray, eps: float = 1e-12) -> np.ndarray:
    n = np.linalg.norm(v, axis=-1, keepdims=True)
    return v / np.maximum(n, eps)


def _line_intersection(p1, d1, p2, d2, eps=1e-12):
    """
    Intersection of lines: p1 + t d1 and p2 + u d2 in 2D.
    Returns point or None if (near) parallel.
    """

    # Solve p1 + t d1 = p2 + u d2
    # using 2D cross products
    def cross(a, b):  # scalar
        return a[0] * b[1] - a[1] * b[0]

    denom = cross(d1, d2)
    if abs(denom) < eps:
        return None

    t = cross((p2 - p1), d2) / denom
    return p1 + t * d1


def _clean_consecutive_duplicates(
    pts: np.ndarray, eps: float = 1e-6
) -> np.ndarray:
    if len(pts) == 0:
        return pts
    out = [pts[0]]
    for p in pts[1:]:
        if np.linalg.norm(p - out[-1]) > eps:
            out.append(p)
    return np.asarray(out)


def stroke_polyline_to_polygon(
    pts: np.ndarray,
    width: float,
    *,
    closed: bool = False,
    miter_limit: float = 4.0,  # in units of half-width
    drop_eps: float = 1e-6,
    start_join_dir: np.ndarray | None = None,
    end_join_dir: np.ndarray | None = None,
) -> np.ndarray:
    """
    2D polyline -> polygon outline using segment offsets and miter-with-clamp joins.
    Output polygon is NOT explicitly closed (napari closes polygons implicitly).
    """
    pts = np.asarray(pts, float)
    if pts.ndim != 2 or pts.shape[1] != 2:
        raise ValueError(f"Expected (N,2), got {pts.shape}")
    if len(pts) < 2:
        raise ValueError("Need at least 2 points")

    # Remove non-finite and consecutive duplicates / zero-length segments
    pts = pts[np.isfinite(pts).all(axis=1)]
    if len(pts) < 2:
        raise ValueError("Not enough finite points")

    d = np.diff(pts, axis=0)
    keep = np.concatenate([[True], np.linalg.norm(d, axis=1) > drop_eps])
    pts = pts[keep]

    if (
        closed
        and len(pts) >= 3
        and np.linalg.norm(pts[0] - pts[-1]) <= drop_eps
    ):
        pts = pts[:-1]

    n = len(pts)
    if n < 2:
        raise ValueError("Degenerate after cleaning")

    half = 0.5 * float(width)

    # Segment directions and normals
    ## edited this. Problem might rise
    # if closed:
    #    seg = np.roll(pts, -1, axis=0) - pts  # (N,2)
    # else:
    #    seg = np.diff(pts, axis=0)  # (N-1,2)
    seg = np.roll(pts, -1, axis=0) - pts if closed else np.diff(pts, axis=0)

    t = _normalize(seg)
    nseg = np.stack([-t[:, 1], t[:, 0]], axis=1)  # left normal per segment

    def _miter_cap(
        p: np.ndarray,
        d1: np.ndarray,
        d2: np.ndarray,
        sign: float,
    ) -> np.ndarray | None:
        n1 = np.array([-d1[1], d1[0]])
        n2 = np.array([-d2[1], d2[0]])
        o1 = p + sign * half * n1
        o2 = p + sign * half * n2
        x = _line_intersection(o1, d1, o2, d2)
        if x is None:
            return None
        if np.linalg.norm(x - p) > miter_limit * half:
            return None
        return x

    def build_side(sign: float) -> np.ndarray:
        # sign=+1 for left, sign=-1 for right
        out = []

        if not closed:
            # start cap (butt)
            start_cap = None
            if start_join_dir is not None:
                d1 = _normalize(start_join_dir.reshape(1, 2))[0]
                d2 = t[0]
                start_cap = _miter_cap(pts[0], d1, d2, sign)
            out.append(
                start_cap
                if start_cap is not None
                else pts[0] + sign * half * nseg[0]
            )

            for i in range(1, n - 1):
                p = pts[i]

                # previous segment (i-1) and next segment (i)
                d1 = t[i - 1]
                d2 = t[i]
                o1 = p + sign * half * nseg[i - 1]
                o2 = p + sign * half * nseg[i]

                x = _line_intersection(o1, d1, o2, d2)

                if x is None:
                    # parallel: just bevel
                    out.append(o1)
                    out.append(o2)
                else:
                    # miter length check
                    if np.linalg.norm(x - p) > miter_limit * half:
                        out.append(o1)
                        out.append(o2)
                    else:
                        out.append(x)

            # end cap (butt)
            end_cap = None
            if end_join_dir is not None:
                d1 = t[-1]
                d2 = _normalize(end_join_dir.reshape(1, 2))[0]
                end_cap = _miter_cap(pts[-1], d1, d2, sign)
            out.append(
                end_cap
                if end_cap is not None
                else pts[-1] + sign * half * nseg[-1]
            )
            return _clean_consecutive_duplicates(np.asarray(out))

        # closed: every vertex has prev and next segments
        for i in range(n):
            p = pts[i]
            d1 = t[i - 1]
            d2 = t[i]
            o1 = p + sign * half * nseg[i - 1]
            o2 = p + sign * half * nseg[i]

            x = _line_intersection(o1, d1, o2, d2)
            if x is None:
                out.append(o1)
                out.append(o2)
            else:
                if np.linalg.norm(x - p) > miter_limit * half:
                    out.append(o1)
                    out.append(o2)
                else:
                    out.append(x)

        return _clean_consecutive_duplicates(np.asarray(out))

    left = build_side(+1.0)
    right = build_side(-1.0)

    poly = np.vstack([left, right[::-1]])

    # final sanity
    if not np.isfinite(poly).all():
        raise ValueError("Polygon has NaN/inf")
    if len(poly) < 3:
        raise ValueError("Polygon too small")
    return poly


def save_expansion_spinbox_values(
    expanded_shapes_values: list[int], saving_directory: str
) -> None:
    config_parser = ConfigParser()
    config_parser.add_section("ExpandedRegions")
    for expanded_index, expanded_value in enumerate(expanded_shapes_values):
        region_string = "region-" + str(expanded_index + 1)
        config_parser["ExpandedRegions"][region_string] = str(expanded_value)
    config_file_path = os.path.join(
        saving_directory, EDITED_REGIONS_EXPANSION_VALUES_FILE_NAME
    )
    with open(config_file_path, "w") as config_file:
        config_parser.write(config_file)


def open_edited_regions_expansion_values(file_path) -> tuple[int, ...]:
    config_parser = ConfigParser()
    config_parser.read(file_path)
    number_of_expanded_regions: int = len(config_parser["ExpandedRegions"])
    returning_list: list[int] = []
    for expanded_index in range(number_of_expanded_regions):
        region_string = "region-" + str(expanded_index + 1)
        expanded_value = config_parser["ExpandedRegions"][region_string]
        returning_list.append(int(expanded_value))
    return tuple(returning_list)
