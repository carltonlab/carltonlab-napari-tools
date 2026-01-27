import numpy as np
from napari.layers import Shapes
from napari.layers.shapes._shapes_models import Shape
from napari.layers.shapes._shapes_models.shape import remove_path_duplicates
from napari.utils.notifications import show_info
from scipy.interpolate import splev, splprep


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
