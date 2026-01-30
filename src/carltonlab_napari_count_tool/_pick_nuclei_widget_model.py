import os
from configparser import ConfigParser
from typing import Literal, cast

from napari.layers import Image, Points
from napari.utils.notifications import show_info
from napari.viewer import ViewerModel

from carltonlab_napari_count_tool._model import (
    create_points_layer,
    open_csv_as_points_layer,
    open_image_as_layer,
)
from carltonlab_napari_count_tool._shared_variables import (
    DEFAULT_PROJECT_NAME,
    EDITED_REGIONS_EXPANSION_VALUES_FILE_NAME,
    PICK_NUCLEI_DIR_NAME,
    REGIONS_DIR_NAME,
)


def open_project(
    napari_viewer: ViewerModel, image_path: str
) -> Literal["failed"] | tuple[str, Image, list[Points]]:
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
    config_parser = ConfigParser()
    config_parser.read(editable_regions_config_path)
    number_of_regions = len(config_parser["ExpandedRegions"])
    for region_index in range(number_of_regions):
        current_region_points_name = (
            "region-" + str(region_index + 1) + "_points"
        )
        current_region_points_file_name = current_region_points_name + ".csv"
        current_region_points_layer_path: str = os.path.join(
            pick_nuclei_directory, current_region_points_file_name
        )
        current_region_points_layer: Points | None
        if not os.path.exists(current_region_points_layer_path):
            current_region_points_layer = create_points_layer(
                napari_viewer, current_region_points_name
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
            current_region_points_layer.name = current_region_points_name
            regions_points_list.append(current_region_points_layer)
    return (pick_nuclei_directory, image_layer, regions_points_list)


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
