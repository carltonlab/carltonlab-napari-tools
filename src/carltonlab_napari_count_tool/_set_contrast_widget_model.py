import os
from configparser import ConfigParser

import tifffile
from napari.layers import Image
from napari.viewer import ViewerModel
from qtpy.QtWidgets import QWidget

from carltonlab_napari_count_tool._model import (
    get_file_name_from_path,
    verify_project_directory_from_image_path,
)
from carltonlab_napari_count_tool._shared_variables import (
    DEFAULT_PROJECT_NAME,
    IMAGE_CONTRASTS_FILE_NAME,
)
from carltonlab_napari_count_tool._shared_widgets import (
    confirm_dialog,
    get_file,
)


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
    new_image_path: bool | str = verify_project_directory_from_image_path(
        open_image_path, create_project_if_not_exist=True
    )
    if isinstance(new_image_path, str):
        open_image_path = new_image_path
    image_data = tifffile.imread(open_image_path)
    if len(image_data.shape) < 4:
        raise ValueError(
            f"The image shape is: {image_data.shape}, expected at least 4 dimensions"
            f"The cannel axis must be index 1"
        )
    image_layers: list[Image] | Image = napari_viewer.add_image(
        image_data, channel_axis=1
    )
    file_name_tuple: tuple[str, str, str] = get_file_name_from_path(
        open_image_path
    )
    if isinstance(image_layers, Image):
        raise ValueError(
            f"Expected 2 channels along axis=1, but add_image returned a single layer"
            f"The image shape is: {image_data.shape}"
        )
    for image_index, image_layer in enumerate(image_layers):
        channel_string: str = f"c{image_index + 1}"
        image_layer.name = file_name_tuple[1] + " - " + channel_string
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


def verify_image_contrasts_file(image_path: str | None) -> bool:
    if image_path is None:
        return False
    image_dir: str = os.path.dirname(image_path)
    saving_contrasts_file_path: str = os.path.join(
        image_dir, DEFAULT_PROJECT_NAME, IMAGE_CONTRASTS_FILE_NAME
    )
    return os.path.exists(saving_contrasts_file_path)


def get_image_contrasts_from_file(
    image_path: str, images: tuple[Image, ...]
) -> dict[int, tuple[float, float]] | None:
    image_dir: str = os.path.dirname(image_path)
    project_file_dir: str = os.path.join(image_dir, DEFAULT_PROJECT_NAME)
    returning_dict = get_loaded_image_contrasts(project_file_dir)
    if returning_dict is None:
        return returning_dict
    for layer_index, contrast_tuple in returning_dict.items():
        image_layer: Image = images[layer_index]
        image_layer.contrast_limits = contrast_tuple
    return returning_dict
