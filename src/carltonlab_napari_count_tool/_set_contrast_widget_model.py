import os
from typing import cast
from napari.utils.misc import re
from pydantic.v1 import config
import tifffile
from napari.layers import Image, image
from napari.viewer import ViewerModel
from qtpy.QtWidgets import QWidget
from carltonlab_napari_count_tool._shared_variables import (
    DEFAULT_PROJECT_NAME,
    IMAGE_CONTRASTS_FILE_NAME,
)
from carltonlab_napari_count_tool._shared_widgets import (
    confirm_dialog,
    get_file,
)
from carltonlab_napari_count_tool._model import get_image_contrasts
from configparser import ConfigParser


def set_layer_contrast_limits(
    image_layer: Image, min_contrast: float, max_contrast: float
):
    if min_contrast == 0 and min_contrast >= max_contrast:
        max_contrast = min_contrast + 0.01
    if max_contrast >= 65535 and min_contrast >= 65535:
        min_contrast = max_contrast - 0.01
    if min_contrast == max_contrast:
        max_contrast = max_contrast + 0.01
    image_layer.contrast_limits = (min_contrast, max_contrast)
    image_layer.refresh()


def get_loaded_image_contrasts(
    project_dir: str,
) -> dict[int, tuple[float, float]] | None:
    if not os.path.exists(project_dir):
        print(f"The project directory {project_dir} doesn't exist")
        return
    contrasts_file_path: str = os.path.join(
        project_dir, IMAGE_CONTRASTS_FILE_NAME
    )
    if not os.path.exists(contrasts_file_path):
        print(
            f"The contrast file with path: {contrasts_file_path} doesn't exist"
        )
        return
    config_parser: ConfigParser = ConfigParser()
    config_parser.read(contrasts_file_path)
    number_of_channels: int = int(
        config_parser["ImageContrasts"]["NumberOfChannels"]
    )
    returning_dict: dict[int, tuple[float, float]] = {}
    for channel_index in range(number_of_channels):
        channel_name: str = "channel-" + str(channel_index + 1)
        values_str: str = config_parser["ImageContrasts"][channel_name]
        values_strings: list[str] = values_str.split(",")
        values: tuple[float, float] = (
            float(values_strings[0]),
            float(values_strings[1]),
        )
        returning_dict[channel_index] = values
    return returning_dict


def open_image_contrasts(
    napari_viewer: ViewerModel, parent_widget: QWidget
) -> tuple[list[Image], str] | None:
    open_image_path: str | None = get_file(
        parent_widget, "Select image to get contrasts"
    )
    if open_image_path is None:
        return None
    image_data = tifffile.imread(open_image_path)
    image_layers: list[Image] | Image = napari_viewer.add_image(
        image_data, channel_axis=1
    )
    if isinstance(image_layers, Image):
        raise ValueError(
            f"Expected 2 channels along axis=1, but add_image returned a single layer"
            f"The image shape is: {image_data.shape}"
        )
    return (image_layers, open_image_path)


def save_contrasts(
    napari_viewer: ViewerModel,
    saving_dict: dict[int, tuple[float, float]],
    image_path: str,
) -> None:
    main_dir: str = os.path.dirname(image_path)
    saving_contrasts_file_path: str = os.path.join(
        main_dir, DEFAULT_PROJECT_NAME, IMAGE_CONTRASTS_FILE_NAME
    )
    if os.path.exists(saving_contrasts_file_path):
        confirm_answer = confirm_dialog(
            napari_viewer, "Contrast already set, replace?"
        )
        if not confirm_answer:
            return
    config_parser: ConfigParser = ConfigParser()
    config_parser.add_section("ImageContrasts")
    config_parser["ImageContrasts"]["NumberOfChannels"] = str(len(saving_dict))
    for contrast_index in range(len(saving_dict.keys())):
        contrast_string: str = "channel-" + str(contrast_index + 1)
        contrast_values: tuple[float, float] = saving_dict[contrast_index]
        config_parser["ImageContrasts"][contrast_string] = (
            str(contrast_values[0]) + "," + str(contrast_values[1])
        )
    with open(saving_contrasts_file_path, "w") as config_file:
        config_parser.write(config_file)
