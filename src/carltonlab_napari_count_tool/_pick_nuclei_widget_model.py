import csv
import glob
import os
from configparser import ConfigParser
from configparser import Error as ConfigParserError
from typing import Literal, cast

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from napari.layers import Image, Points, Shapes
from napari.utils.notifications import show_info
from napari.viewer import ViewerModel
from numpy.typing import NDArray
from skimage.io import imread

from carltonlab_napari_count_tool._model import (
    open_csv_as_points_layer,
    open_csv_as_shape_layer,
    open_image_as_layer,
    save_layer_as_csv,
)
from carltonlab_napari_count_tool._regions_widget_model import SPLINE_FILE_NAME
from carltonlab_napari_count_tool._shared_variables import (
    CUT_SBS_DIR_NAME,
    DEFAULT_PROJECT_NAME,
    EDITED_REGIONS_EXPANSION_VALUES_FILE_NAME,
    EDITED_REGIONS_FILE_NAME,
    PICK_NUCLEI_DIR_NAME,
    PICK_NUCLEI_REPORT_FILE_NAME,
    PICK_NUCLEI_REPORT_PLOT_FILE_NAME,
    PICK_NUCLEI_REPORT_PLOT_NORM_FILE_NAME,
    POINT_FILE_NAME_EXTENSION,
    POINTS_SUMMARY_FILE_NAME,
    REGION_ROOT_NAME,
    REGIONS_DIR_NAME,
    SBS_FILE_NAME_EXTENSION,
    SBS_METADATA_FILE_NAME,
    SQUARES_FILE_NAME_EXTENSION,
)


def open_project(napari_viewer: ViewerModel, image_path: str) -> (
    Literal["failed"]
    | tuple[
        str,
        Image,
        list[Points],
        list[Shapes],
        Shapes,
        Shapes,
        Shapes,
        Points,
        Points,
        Shapes,
        list[tuple[int, bool, bool, bool] | None],
    ]
):
    """
    The returns are
    tuple with a string with the pick_nuclei_directory_path, the image layer and the points layer
    """
    parent_dir: str = os.path.dirname(image_path)
    searching_project_path: str = os.path.join(
        parent_dir, DEFAULT_PROJECT_NAME
    )
    if not os.path.exists(searching_project_path):
        show_info(
            f"The project with path {searching_project_path} doesn't exist, make sure to create it with the regions tool"
        )
        return "failed"
    pick_nuclei_directory: str = os.path.join(
        searching_project_path, PICK_NUCLEI_DIR_NAME
    )
    if not os.path.exists(pick_nuclei_directory):
        os.makedirs(pick_nuclei_directory)
    editable_regions_config_path = os.path.join(
        searching_project_path,
        REGIONS_DIR_NAME,
        EDITED_REGIONS_EXPANSION_VALUES_FILE_NAME,
    )
    if not os.path.exists(editable_regions_config_path):
        show_info(
            "The edited (expanded) regions file doesn't exist. Create it in the regions widget"
        )
        return "failed"
    image_layer: Image | None = validate_image_open(napari_viewer, image_path)
    if validate_image_open(napari_viewer, image_path) is None:
        image_layer = open_image_as_layer(napari_viewer, image_path)
    if image_layer is None:
        show_info("Couldn't load the image layer")
        return "failed"
    image_layer_dims = image_layer.ndim
    number_of_regions = get_number_of_saved_regions(searching_project_path)
    points_squares_tuple: (
        tuple[list[Points], list[Shapes]] | Literal["failed"]
    ) = open_points_and_squares_layers(
        napari_viewer,
        pick_nuclei_directory,
        number_of_regions,
        image_layer_dims,
    )
    if points_squares_tuple == "failed":
        return "failed"
    edited_regions_path: str = os.path.join(
        searching_project_path, REGIONS_DIR_NAME, EDITED_REGIONS_FILE_NAME
    )
    if not os.path.exists(edited_regions_path):
        show_info(
            f"The edited regions file with path {edited_regions_path} does not exist"
        )
        return "failed"
    edited_regions_layer: Shapes | None = open_csv_as_shape_layer(
        napari_viewer, edited_regions_path
    )
    if edited_regions_layer is None:
        show_info("Couldn't load the edited regions layer")
        return "failed"
    current_region_layer: Shapes = napari_viewer.add_shapes(
        name="current_region", ndim=2
    )
    extra_regions_layer: Shapes = napari_viewer.add_shapes(
        name="extra_regions", ndim=2
    )
    all_points_layer: Points = napari_viewer.add_points(
        name="all_points_layer", ndim=image_layer_dims
    )
    all_points_2d_layer: Points = napari_viewer.add_points(
        name="all_points_2d", ndim=2
    )
    all_squares_layer: Shapes = napari_viewer.add_shapes(
        name="all_squares_layer", ndim=2
    )
    saved_points_list: list[tuple[int, bool, bool, bool] | None] = (
        get_points_saved_list(pick_nuclei_directory, number_of_regions)
    )
    return (
        pick_nuclei_directory,
        image_layer,
        points_squares_tuple[0],
        points_squares_tuple[1],
        edited_regions_layer,
        current_region_layer,
        extra_regions_layer,
        all_points_layer,
        all_points_2d_layer,
        all_squares_layer,
        saved_points_list,
    )


def open_points_and_squares_layers(
    napari_viewer: ViewerModel,
    pick_nuclei_directory: str,
    number_of_regions: int,
    image_dims: int,
) -> tuple[list[Points], list[Shapes]] | Literal["failed"]:
    returning_points: list[Points] = []
    returning_squares: list[Shapes] = []
    for region_index in range(number_of_regions):
        current_region_string = "region-" + str(region_index + 1)
        current_points_file_name: str = os.path.join(
            current_region_string + POINT_FILE_NAME_EXTENSION
        )
        current_points_file_path: str = os.path.join(
            pick_nuclei_directory, current_points_file_name
        )
        current_point_layer: Points | None
        if not os.path.exists(current_points_file_path):
            current_point_layer = napari_viewer.add_points(
                name=current_region_string + "_points", ndim=image_dims
            )
        else:
            current_point_layer = open_csv_as_points_layer(
                napari_viewer, current_points_file_path
            )
        if current_point_layer is None:
            show_info(
                f"Couldn't load the points layer {current_points_file_path}"
            )
            return "failed"
        returning_points.append(current_point_layer)
        current_square_file_name: str = os.path.join(
            current_region_string + SQUARES_FILE_NAME_EXTENSION
        )
        current_square_file_path: str = os.path.join(
            pick_nuclei_directory, current_square_file_name
        )
        current_square_layer: Shapes | None
        if not os.path.exists(current_square_file_path):
            current_square_layer = napari_viewer.add_shapes(
                name=current_region_string + "_squares", ndim=2
            )
        else:
            current_square_layer = open_csv_as_shape_layer(
                napari_viewer, current_square_file_path
            )
        if current_square_layer is None:
            show_info(
                f"Couldn't load the squares layer {current_square_file_path}"
            )
            return "failed"
        returning_squares.append(current_square_layer)
    return (returning_points, returning_squares)


def str_to_bool(value: str) -> bool:
    return value.lower() in {"true", "1"}


def get_points_saved_list(
    pick_nuclei_directory, number_of_regions: int
) -> list[tuple[int, bool, bool, bool] | None]:
    points_saved_list: list[None | tuple[int, bool, bool, bool]] = []
    project_directory: str = os.path.dirname(pick_nuclei_directory)
    number_of_saved_regions: int = get_number_of_saved_regions(
        project_directory
    )
    for _ in range(number_of_saved_regions):
        points_saved_list.append(None)
    points_summary_file_path: str = os.path.join(
        pick_nuclei_directory, POINTS_SUMMARY_FILE_NAME
    )
    summary_parser = load_points_summary_file(points_summary_file_path)
    if summary_parser is None:
        summary_parser = create_summary_file(
            pick_nuclei_directory, number_of_regions
        )
    if len(summary_parser["NucleiCount"]) <= 0:
        print("Returning without loading?")
        return points_saved_list
    for region_index in range(len(summary_parser["NucleiCount"])):
        region_str: str = "region-" + str(region_index + 1)
        number_of_points: int = int(summary_parser["NucleiCount"][region_str])
        saved_points_state: bool = str_to_bool(
            summary_parser["SavedPointsState"][region_str]
        )
        saved_squares_state: bool = str_to_bool(
            summary_parser["SavedSquaresState"][region_str]
        )
        saved_sbs_state: bool = str_to_bool(
            summary_parser["SavedSbsState"][region_str]
        )
        setting_tuple: tuple[int, bool, bool, bool] = (
            number_of_points,
            saved_points_state,
            saved_squares_state,
            saved_sbs_state,
        )
        points_saved_list[region_index] = setting_tuple
    return points_saved_list


def get_number_of_saved_regions(project_directory: str) -> int:
    editable_regions_config_path: str = os.path.join(
        project_directory,
        REGIONS_DIR_NAME,
        EDITED_REGIONS_EXPANSION_VALUES_FILE_NAME,
    )
    if not os.path.exists(editable_regions_config_path):
        return 0
    edited_regions_parser: ConfigParser = ConfigParser()
    try:
        edited_regions_parser.read(editable_regions_config_path)
    except ConfigParserError:
        show_info("Couldn't load the edited regions config file")
        return 0
    number_of_regions: int = len(edited_regions_parser["ExpandedRegions"])
    return number_of_regions


def create_summary_file(
    pick_nuclei_directory: str, number_of_regions
) -> ConfigParser:
    config_file_path: str = os.path.join(
        pick_nuclei_directory, POINTS_SUMMARY_FILE_NAME
    )
    summary_file_parser: ConfigParser = ConfigParser()
    summary_file_parser.add_section("NucleiCount")
    summary_file_parser.add_section("SavedPointsState")
    summary_file_parser.add_section("SavedSquaresState")
    summary_file_parser.add_section("SavedSbsState")
    for region_index in range(number_of_regions):
        retion_string: str = "region-" + str(region_index + 1)
        summary_file_parser["NucleiCount"][retion_string] = "0"
        summary_file_parser["SavedPointsState"][retion_string] = "False"
        summary_file_parser["SavedSquaresState"][retion_string] = "False"
        summary_file_parser["SavedSbsState"][retion_string] = "False"
    with open(config_file_path, "w") as config_file:
        summary_file_parser.write(config_file)
    return summary_file_parser


def save_points_summary_file(
    points_saved_list: list[tuple[int, bool, bool, bool]],
    pick_nuclei_directory: str,
) -> None:
    config_parser = ConfigParser()
    config_parser.add_section("NucleiCount")
    config_parser.add_section("SavedPointsState")
    config_parser.add_section("SavedSquaresState")
    config_parser.add_section("SavedSbsState")
    for region_index in range(len(points_saved_list)):
        region_string: str = "region-" + str(region_index + 1)
        config_parser["NucleiCount"][region_string] = str(
            points_saved_list[region_index][0]
        )
        config_parser["SavedPointsState"][region_string] = str(
            points_saved_list[region_index][1]
        )
        config_parser["SavedSquaresState"][region_string] = str(
            points_saved_list[region_index][2]
        )
        config_parser["SavedSbsState"][region_string] = str(
            points_saved_list[region_index][3]
        )
    config_file_path: str = os.path.join(
        pick_nuclei_directory, POINTS_SUMMARY_FILE_NAME
    )
    try:
        with open(config_file_path, "w") as config_file:
            config_parser.write(config_file)
    except ConfigParserError:
        show_info("Error saving the points summary file...")
    return


def load_points_summary_file(summary_file_path) -> ConfigParser | None:
    loaded_parser: ConfigParser | None = ConfigParser()
    try:
        read_file = loaded_parser.read(summary_file_path)
        if not read_file:
            loaded_parser = None
    except ConfigParserError:
        show_info("Couldn't load the points summary file")
        loaded_parser = None
        return loaded_parser
    return loaded_parser


def validate_image_open(
    napari_viewer: ViewerModel, image_path: str
) -> Image | None:
    layers_list = napari_viewer.layers
    image_file_name: str = os.path.basename(image_path)
    for layer in layers_list:
        layer_path = layer.source.path
        if layer_path is None:
            return None
        layer_file_name: str = os.path.basename(layer_path)
        if layer_file_name == image_file_name:
            image_layer: Image = cast(Image, layer)
            return image_layer
    return None


def open_squares_layers(
    napari_viewer: ViewerModel,
    pick_nuclei_directory: str,
    saved_points_list: list[tuple[int, bool, bool, bool] | None],
    image_layer_dims: int,
) -> list[Shapes]:
    returning_list: list[Shapes] = []
    for region_index in range(len(saved_points_list)):
        shape_layer: Shapes | None
        layer_name: str = "region-" + str(region_index + 1) + "_squares"
        if saved_points_list[region_index] is None:
            shape_layer = napari_viewer.add_shapes(
                None, name=layer_name, ndim=image_layer_dims
            )
            returning_list.append(shape_layer)
            continue
        tuple_element: tuple[int, bool, bool, bool] = cast(
            tuple[int, bool, bool, bool], saved_points_list[region_index]
        )
        if tuple_element[2]:
            squares_layer_path = os.path.join(
                pick_nuclei_directory,
                REGION_ROOT_NAME,
                str(region_index + 1) + SQUARES_FILE_NAME_EXTENSION,
            )
            shape_layer = open_csv_as_shape_layer(
                napari_viewer, squares_layer_path
            )
            if shape_layer is None:
                show_info(
                    f"Couldn't open the squares layer for region {str(region_index + 1)}"
                )
                return []
            shape_layer.name = layer_name
        else:
            shape_layer = napari_viewer.add_shapes(
                None, name=layer_name, ndim=image_layer_dims
            )
        returning_list.append(shape_layer)
    return returning_list


def save_points_or_square_layer(
    saving_layer: Points | Shapes,
    number_of_points: int | None,
    pick_nuclei_directory: str,
    region_index: int,
) -> bool:
    summary_file_path: str = os.path.join(
        pick_nuclei_directory, POINTS_SUMMARY_FILE_NAME
    )
    summary_file_parser: ConfigParser | None = load_points_summary_file(
        summary_file_path
    )
    if summary_file_parser is None:
        return False
    region_string: str = "region-" + str(region_index + 1)
    if isinstance(saving_layer, Points):
        summary_file_parser["NucleiCount"][region_string] = str(
            number_of_points
        )
        summary_file_parser["SavedPointsState"][region_string] = "True"
    if isinstance(saving_layer, Shapes):
        summary_file_parser["SavedSquaresState"][region_string] = "True"
    try:
        with open(summary_file_path, "w") as config_file:
            summary_file_parser.write(config_file)
    except ConfigParserError:
        show_info("Error saving the points layer")
        return False
    if number_of_points == 0:
        return True
    saving_file_path = ""
    if isinstance(saving_layer, Points):
        region_points_file_name: str = (
            region_string + POINT_FILE_NAME_EXTENSION
        )
        region_points_file_path: str = os.path.join(
            pick_nuclei_directory, region_points_file_name
        )
        saving_file_path = region_points_file_path
    if isinstance(saving_layer, Shapes):
        region_squares_file_name: str = (
            region_string + SQUARES_FILE_NAME_EXTENSION
        )
        region_squares_file_path: str = os.path.join(
            pick_nuclei_directory, region_squares_file_name
        )
        saving_file_path = region_squares_file_path
    save_layer_as_csv(saving_layer, saving_file_path)
    return True


def create_squares_layers_from_points_layer(
    points_layer: Points, squares_layer: Shapes, square_width: int
) -> None:
    if not len(points_layer.data):
        show_info("There's no points in the layer to crete squares")
        return
    points_data = points_layer.data
    points_np_data = np.asarray(points_data)
    half_size = square_width / 2
    xy_points = points_np_data[:, (-2, -1)]
    offsets = np.array(
        [
            [-half_size, -half_size],
            [half_size, -half_size],
            [half_size, half_size],
            [-half_size, half_size],
        ],
        dtype=xy_points.dtype,
    )
    squares_np_data = xy_points[:, None, :] + offsets[None, :, :]
    squares_layer.data = squares_np_data
    squares_layer.refresh()


def cut_sbs_files_from_squares_and_image_layers(
    image_layer: Image,
    squares_layer: Shapes,
    pick_nuclei_directory: str,
    region_index: int,
) -> bool:
    region_str: str = "region-" + str(region_index + 1)
    squares_array = squares_layer.data
    image_data: NDArray[np.generic] = np.asarray(image_layer.data)
    cut_sbs_dir: str = os.path.join(pick_nuclei_directory, CUT_SBS_DIR_NAME)
    os.makedirs(cut_sbs_dir, exist_ok=True)
    img_y, img_x = image_data.shape[-2:]
    metadata_rows = []
    for square_index, square_array in enumerate(squares_array):
        current_square = np.asarray(square_array)
        y1, x1 = np.floor(current_square.min(axis=0)).astype(int)
        y2, x2 = np.floor(current_square.max(axis=0)).astype(int) + 1
        y1 = max(0, y1)
        x1 = max(0, x1)
        y2 = min(img_y, y2)
        x2 = min(img_x, x2)
        if y2 <= y1 or x2 <= x1:
            continue
        cropped_image = image_data[..., y1:y2, x1:x2]
        sbs_name = (
            region_str
            + "_sbs"
            + str(square_index + 1)
            + SBS_FILE_NAME_EXTENSION
        )
        cropped_layer: Image = Image(cropped_image, name=sbs_name)
        saving_file_path = os.path.join(cut_sbs_dir, sbs_name)
        cropped_layer.save(saving_file_path)
        metadata_rows.append(
            {
                "sbs_image_name": sbs_name,
                "y1": int(y1),
                "x1": int(x1),
                "y2": int(y2),
                "x2": int(x2),
            }
        )

    if metadata_rows:
        metadata_path = os.path.join(cut_sbs_dir, SBS_METADATA_FILE_NAME)
        existing_rows = {}
        if os.path.exists(metadata_path):
            with open(metadata_path, newline="") as csv_file:
                reader = csv.DictReader(csv_file)
                for row in reader:
                    if "sbs_image_name" in row:
                        existing_rows[row["sbs_image_name"]] = row
        for row in metadata_rows:
            existing_rows[row["sbs_image_name"]] = row
        fieldnames = ["sbs_image_name", "y1", "x1", "y2", "x2"]
        with open(metadata_path, "w", newline="") as csv_file:
            writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
            writer.writeheader()
            for row in existing_rows.values():
                writer.writerow(row)

    return True


def _axis_columns_from_dataframe(df: pd.DataFrame) -> list[str]:
    axis_cols = [col for col in df.columns if col.startswith("axis-")]
    if not axis_cols:
        return []
    axis_cols.sort(key=lambda col: int(col.split("-")[-1]))
    return axis_cols


def _load_spline_polyline(spline_csv_path: str) -> np.ndarray | None:
    if not os.path.exists(spline_csv_path):
        return None
    df = pd.read_csv(spline_csv_path)
    axis_cols = _axis_columns_from_dataframe(df)
    if len(axis_cols) < 2:
        return None
    axis_cols = axis_cols[-2:]
    shape_df = df
    if "shape_type" in df.columns:
        shape_df = df[df["shape_type"] == "path"]
        if shape_df.empty:
            shape_df = df
    if "index" in shape_df.columns:
        min_index = shape_df["index"].min()
        shape_df = shape_df[shape_df["index"] == min_index]
    if "vertex_index" in shape_df.columns:
        shape_df = shape_df.sort_values("vertex_index")
    spline_points = shape_df[axis_cols].to_numpy()
    if spline_points.ndim != 2 or spline_points.shape[0] < 2:
        return None
    return spline_points


def _project_point_to_polyline(
    point_yx: np.ndarray, polyline_yx: np.ndarray
) -> float:
    segments = polyline_yx[1:] - polyline_yx[:-1]
    seg_len2 = (segments**2).sum(axis=1)
    seg_len = np.sqrt(seg_len2)
    cumlen = np.concatenate(([0.0], np.cumsum(seg_len)))
    total_len = cumlen[-1]

    best_dist2 = None
    best_arc = 0.0
    for i, (p0, seg, seg_l2) in enumerate(
        zip(polyline_yx[:-1], segments, seg_len2, strict=True)
    ):
        if seg_l2 == 0:
            continue
        t = float(np.dot(point_yx - p0, seg) / seg_l2)
        t = min(1.0, max(0.0, t))
        proj = p0 + t * seg
        dist2 = float(np.dot(point_yx - proj, point_yx - proj))
        if best_dist2 is None or dist2 < best_dist2:
            best_dist2 = dist2
            best_arc = float(cumlen[i] + t * seg_len[i])

    if total_len == 0:
        return 0.0
    return best_arc / total_len


def generate_pick_nuclei_spline_intensity_report(
    pick_nuclei_directory: str,
) -> str | None:
    project_dir = os.path.dirname(pick_nuclei_directory)
    spline_csv_path = os.path.join(
        project_dir, REGIONS_DIR_NAME, SPLINE_FILE_NAME
    )
    spline_points = _load_spline_polyline(spline_csv_path)
    if spline_points is None:
        return None

    points_files = glob.glob(
        os.path.join(
            pick_nuclei_directory,
            f"{REGION_ROOT_NAME}*{POINT_FILE_NAME_EXTENSION}",
        )
    )
    if not points_files:
        return None

    cut_sbs_dir = os.path.join(pick_nuclei_directory, CUT_SBS_DIR_NAME)
    rows = []
    for points_file_path in points_files:
        points_df = pd.read_csv(points_file_path)
        axis_cols = _axis_columns_from_dataframe(points_df)
        if len(axis_cols) < 2:
            continue
        axis_cols = axis_cols[-2:]
        region_name = os.path.basename(points_file_path).replace(
            POINT_FILE_NAME_EXTENSION, ""
        )
        for idx, row in points_df.iterrows():
            point_y = float(row[axis_cols[0]])
            point_x = float(row[axis_cols[1]])
            sbs_name = f"{region_name}_sbs{idx + 1}{SBS_FILE_NAME_EXTENSION}"
            sbs_path = os.path.join(cut_sbs_dir, sbs_name)
            if os.path.exists(sbs_path):
                sbs_data = np.asarray(imread(sbs_path))
                sum_intensity = float(sbs_data.sum())
            else:
                sum_intensity = float("nan")
            norm_arc = _project_point_to_polyline(
                np.array([point_y, point_x], dtype=np.float64),
                spline_points,
            )
            rows.append(
                {
                    "sbs_image_file_name": sbs_name,
                    "x_coordinate": point_x,
                    "y_coordinate": point_y,
                    "relative_position_in_spline": norm_arc,
                    "sum_intensity": sum_intensity,
                }
            )

    if not rows:
        return None
    report_df = pd.DataFrame(rows)
    norm_bins = [
        (0.0, 0.2, "normalized_intensity_0_20"),
        (0.2, 0.4, "normalized_intensity_20_40"),
        (0.4, 0.6, "normalized_intensity_40_60"),
        (0.6, 0.8, "normalized_intensity_60_80"),
        (0.8, 1.0, "normalized_intensity_80_100"),
    ]
    for start, end, col_name in norm_bins:
        region_mask = (report_df["relative_position_in_spline"] >= start) & (
            report_df["relative_position_in_spline"] <= end
        )
        mean_intensity = report_df.loc[region_mask, "sum_intensity"].mean()
        if pd.isna(mean_intensity) or mean_intensity == 0:
            report_df[col_name] = np.nan
        else:
            report_df[col_name] = report_df["sum_intensity"] / mean_intensity
    output_csv_path = os.path.join(
        pick_nuclei_directory, PICK_NUCLEI_REPORT_FILE_NAME
    )
    report_columns = [
        "sbs_image_file_name",
        "x_coordinate",
        "y_coordinate",
        "relative_position_in_spline",
        "sum_intensity",
    ] + [col_name for _, _, col_name in norm_bins]
    report_df = report_df[report_columns]
    report_df.to_csv(output_csv_path, index=False)
    return output_csv_path


def generate_pick_nuclei_spline_intensity_plot(
    pick_nuclei_directory: str,
) -> str | None:
    report_path = os.path.join(
        pick_nuclei_directory, PICK_NUCLEI_REPORT_FILE_NAME
    )
    if not os.path.exists(report_path):
        report_path = generate_pick_nuclei_spline_intensity_report(
            pick_nuclei_directory
        )
        if report_path is None:
            return None
    report_df = pd.read_csv(report_path)
    if not {
        "relative_position_in_spline",
        "sum_intensity",
    }.issubset(report_df.columns):
        return None
    x = report_df["relative_position_in_spline"].to_numpy()
    y = report_df["sum_intensity"].to_numpy()

    fig, ax = plt.subplots(figsize=(6, 4))
    ax.scatter(x, y, s=12)
    ax.set_xlabel("Relative position in spline")
    ax.set_ylabel("Sum intensity")
    ax.set_xlim(0, 1)
    ax.grid(True, alpha=0.3)

    output_path = os.path.join(
        pick_nuclei_directory, PICK_NUCLEI_REPORT_PLOT_FILE_NAME
    )
    fig.tight_layout()
    fig.savefig(output_path, format="pdf")
    plt.close(fig)
    norm_bins = [
        ("normalized_intensity_0_20", "0-20"),
        ("normalized_intensity_20_40", "20-40"),
        ("normalized_intensity_40_60", "40-60"),
        ("normalized_intensity_60_80", "60-80"),
        ("normalized_intensity_80_100", "80-100"),
    ]
    for col_name, label in norm_bins:
        if col_name not in report_df.columns:
            continue
        y_norm = report_df[col_name].to_numpy()
        fig_norm, ax_norm = plt.subplots(figsize=(6, 4))
        ax_norm.scatter(x, y_norm, s=12)
        ax_norm.set_xlabel("Relative position in spline")
        ax_norm.set_ylabel(f"Normalized intensity ({label})")
        ax_norm.set_xlim(0, 1)
        ax_norm.grid(True, alpha=0.3)

        output_norm_path = os.path.join(
            pick_nuclei_directory,
            PICK_NUCLEI_REPORT_PLOT_NORM_FILE_NAME.replace(
                ".pdf", f"_{label}.pdf"
            ),
        )
        fig_norm.tight_layout()
        fig_norm.savefig(output_norm_path, format="pdf")
        plt.close(fig_norm)
    return output_path
