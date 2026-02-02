import os
from configparser import ConfigParser
from configparser import Error as ConfigParserError
from typing import Literal, cast

from napari.layers import Image, Points, Shapes
from napari.utils.notifications import show_info
from napari.viewer import ViewerModel

from carltonlab_napari_count_tool._model import (
    create_points_layer,
    open_csv_as_points_layer,
    open_csv_as_shape_layer,
    open_image_as_layer,
    save_layer_as_csv,
)
from carltonlab_napari_count_tool._shared_variables import (
    DEFAULT_PROJECT_NAME,
    EDITED_REGIONS_EXPANSION_VALUES_FILE_NAME,
    EDITED_REGIONS_FILE_NAME,
    PICK_NUCLEI_DIR_NAME,
    POINTS_SUMMARY_FILE_NAME,
    REGION_ROOT_NAME,
    REGIONS_DIR_NAME,
    POINT_FILE_NAME_EXTENSION,
    SQUARES_FILE_NAME_EXTENSION,
)


def open_project(
    napari_viewer: ViewerModel, image_path: str
) -> Literal["failed"] | tuple[str, Image, list[Points], Shapes, Shapes]:
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
    regions_points_list: list[Points] = []
    number_of_regions = get_number_of_saved_regions(searching_project_path)
    for region_index in range(number_of_regions):
        current_region_string = "region-" + str(region_index + 1)
        current_region_points_file_name = (
            current_region_string + POINT_FILE_NAME_EXTENSION
        )
        current_region_points_layer_path: str = os.path.join(
            pick_nuclei_directory, current_region_points_file_name
        )
        current_region_points_layer: Points | None
        if not os.path.exists(current_region_points_layer_path):
            current_region_points_layer = create_points_layer(
                napari_viewer, current_region_string + "_points"
            )
            regions_points_list.append(current_region_points_layer)
        else:
            current_region_points_layer = open_csv_as_points_layer(
                napari_viewer, current_region_points_layer_path
            )
            if current_region_points_layer is None:
                show_info(
                    f"Couldn't load the points layer with path: {current_region_points_layer_path}."
                )
                continue
            current_region_points_layer.name = (
                current_region_string + "_points"
            )
            regions_points_list.append(current_region_points_layer)
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
        name="current_region"
    )
    return (
        pick_nuclei_directory,
        image_layer,
        regions_points_list,
        edited_regions_layer,
        current_region_layer,
    )


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
    for layer in layers_list:
        layer_path = layer.source.path
        if layer_path == image_path:
            image_layer: Image = cast(Image, layer)
            return image_layer
    return None


def open_squares_layers(
    napari_viewer: ViewerModel,
    pick_nuclei_directory: str,
    saved_points_list: list[tuple[int, bool, bool, bool] | None],
) -> list[Shapes]:
    returning_list: list[Shapes] = []
    for region_index in range(len(saved_points_list)):
        shape_layer: Shapes | None
        layer_name: str = "region-" + str(region_index + 1) + "_squares"
        if saved_points_list[region_index] is None:
            shape_layer = napari_viewer.add_shapes(None, name=layer_name)
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
            shape_layer = napari_viewer.add_shapes(None, name=layer_name)
        returning_list.append(shape_layer)
    return returning_list


def save_points_layer(
    saving_layer: Points,
    number_of_points: int,
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
    summary_file_parser["NucleiCount"][region_string] = str(number_of_points)
    summary_file_parser["SavedPointsState"][region_string] = "True"
    try:
        with open(summary_file_path, "w") as config_file:
            summary_file_parser.write(config_file)
    except ConfigParserError:
        show_info("Error saving the points layer")
        return False
    if number_of_points == 0:
        return True
    region_points_file_name: str = region_string + POINT_FILE_NAME_EXTENSION
    region_points_file_path: str = os.path.join(
        pick_nuclei_directory, region_points_file_name
    )
    save_layer_as_csv(saving_layer, region_points_file_path)
    return True
