import os
from pathlib import Path
from typing import Literal

import numpy as np
from napari.layers import Image, Shapes
from napari.layers.shapes._shapes_models import Shape
from napari.layers.shapes._shapes_models.shape import remove_path_duplicates
from napari.utils.notifications import show_info
from napari.viewer import ViewerModel
from scipy.interpolate import splev, splprep

from carltonlab_napari_count_tool._model import (
    open_csv_as_shape_layer,
    open_image_as_layer,
    save_layer_as_csv,
)
from carltonlab_napari_count_tool._shared_widgets import confirm_dialog

REGIONS_LAYER_DEFAULT_NAME = "clt_regions_layer"
SPLINE_LAYER_DEFAULT_NAME = "clt_spline_layer"
REGIONS_DEFAULT_WIDTH = 3
REGION_COLOR = "#27adf5"

DEFAULT_PROJECT_NAME = "cl_score_points_project"
DEFAULT_PROJECT_EXTENSION = "_clscp"
REGIONS_DIR_NAME = "regions"

SPLINE_FILE_NAME = "clt_spline_layer.csv"
REGIONS_FILE_NAME = "clt_regions_layer.csv"

EDITED_REGIONS_LAYER_NAME = "clt_edited_regions_layer"
EDITED_REGION_COLOR = "#000000"


def open_project(
    napari_viewer: ViewerModel, image_path: str
) -> Literal["load", "failed"] | tuple[str, Image, Shapes]:
    parent_dir: str = os.path.dirname(image_path)
    searching_project_path: str = os.path.join(
        parent_dir, DEFAULT_PROJECT_NAME
    )
    if os.path.exists(searching_project_path):
        show_info(
            f"The image is part of a project with path {searching_project_path} already exists. Loading project"
        )
        return "load"
    returning_tuple: tuple[str, Image, Shapes] | None = create_new_project(
        image_path, napari_viewer
    )
    if returning_tuple is None:
        return "failed"
    return returning_tuple


def create_new_project(
    file_path: str, napari_viewer: "ViewerModel"
) -> tuple[str, Image, Shapes] | None:
    parent_dir = os.path.dirname(file_path)
    image_file_path_object: Path = Path(file_path)
    image_file_name_no_ext: str = image_file_path_object.stem
    image_file_name: str = image_file_path_object.name
    new_project_path: str = os.path.join(
        parent_dir, image_file_name_no_ext + DEFAULT_PROJECT_EXTENSION
    )
    if not os.path.exists(new_project_path):
        os.makedirs(new_project_path)
    new_project_image_path: str = os.path.join(
        new_project_path, image_file_name
    )
    if not os.path.exists(new_project_image_path):
        os.rename(file_path, new_project_image_path)
    project_new_dir_path: str = os.path.join(
        new_project_path, DEFAULT_PROJECT_NAME
    )
    if not os.path.exists(project_new_dir_path):
        os.makedirs(project_new_dir_path)
    regions_path: str = os.path.join(project_new_dir_path, REGIONS_DIR_NAME)
    if not os.path.exists(regions_path):
        os.makedirs(regions_path)
    image_layer: Image | None = open_image_as_layer(
        napari_viewer, new_project_image_path
    )
    if image_layer is None:
        show_info("Image could not be loaded")
        return None
    spline_layer: Shapes = napari_viewer.add_shapes(
        name=SPLINE_LAYER_DEFAULT_NAME
    )
    return (regions_path, image_layer, spline_layer)


def load_project_files(
    napari_viewer: ViewerModel, image_path: str
) -> tuple[str, Image, Shapes, Shapes | None] | None:
    parent_dir = os.path.dirname(image_path)
    regions_path = os.path.join(
        parent_dir,
        DEFAULT_PROJECT_NAME,
        REGIONS_DIR_NAME,
    )
    returning_list = []
    returning_list.append(regions_path)
    image_layer = open_image_as_layer(napari_viewer, image_path)
    returning_list.append(image_layer)
    spline_layer_path: str = os.path.join(
        parent_dir, DEFAULT_PROJECT_NAME, REGIONS_DIR_NAME, SPLINE_FILE_NAME
    )
    if not os.path.exists(spline_layer_path):
        show_info("No spline layer file found")
        spline_layer = napari_viewer.add_shapes(name="ctl_spline_layer")
    else:
        spline_layer = open_csv_as_shape_layer(
            napari_viewer,
            os.path.join(
                parent_dir,
                DEFAULT_PROJECT_NAME,
                REGIONS_DIR_NAME,
                SPLINE_FILE_NAME,
            ),
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
        returning_list.append(regions_layer)
    else:
        regions_layer = None
        returning_list.append(regions_layer)
    return tuple(returning_list)


def save_spline_layer(
    napari_viewer: ViewerModel, spline_layer: Shapes, saving_dir: str
) -> bool:
    spline_file_path: str = os.path.join(saving_dir, SPLINE_FILE_NAME)
    if os.path.exists(spline_file_path):
        dialog_result: bool = confirm_dialog(
            napari_viewer, "Spline file already exists, overwrite?"
        )
        if not dialog_result:
            return False
        else:
            os.remove(spline_file_path)
    save_layer_as_csv(spline_layer, spline_file_path)
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
    napari_viewer: ViewerModel, spline_points: list[np.ndarray]
) -> Shapes:
    regions_layer = napari_viewer.add_shapes(name=REGIONS_LAYER_DEFAULT_NAME)
    regions_layer.add_paths(
        spline_points,
        edge_width=REGIONS_DEFAULT_WIDTH,
        edge_color=REGION_COLOR,
    )
    return regions_layer


def create_edited_regions_layer(
    napari_viewer: "ViewerModel", regions_layer: Shapes
) -> Shapes:
    edited_regions_layer = napari_viewer.add_shapes(
        name=EDITED_REGIONS_LAYER_NAME,
        edge_width=REGIONS_DEFAULT_WIDTH,
        edge_color=EDITED_REGION_COLOR,
    )
    data_list = []
    for shape_obj in regions_layer._data_view.shapes:
        shape_obj_data = shape_obj.data.copy()
        data_list.append(shape_obj_data)
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
