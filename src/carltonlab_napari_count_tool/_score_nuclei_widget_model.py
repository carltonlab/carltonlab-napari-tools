import os
from configparser import ConfigParser
from typing import Literal

from napari.utils.notifications import show_info
from napari.viewer import ViewerModel
from qtpy.QtWidgets import QWidget

from carltonlab_napari_count_tool._shared_variables import (
    CUT_SBS_DIR_NAME,
    DEFAULT_PROJECT_NAME,
    MULTI_GONAD_FILE_EXTENSION,
    PICK_NUCLEI_DIR_NAME,
    POINTS_SUMMARY_FILE_NAME,
    SBS_FILE_NAME_EXTENSION,
    SCORED_NUCLEI_DIR_NAME,
    SCORED_NUCLEI_POINTS_FILE_NAME_EXTENSION,
)
from carltonlab_napari_count_tool._shared_widgets import (
    confirm_dialog,
    get_file,
)


class CLSPSbsObject:
    def __init__(
        self,
        napari_viewer: "ViewerModel",
        name: str,
        region_name: str,
        scored_nuclei_dir: str,
        sbs_file_path: str,
        gonad_file_name: str,
    ):
        self._napari_viewer = napari_viewer
        self._name: str = name
        self._region_name: str = region_name
        self._scored_nuclei_dir: str = scored_nuclei_dir
        self._points_layer_file_name: str = (
            region_name + "_" + name + SCORED_NUCLEI_POINTS_FILE_NAME_EXTENSION
        )
        self._image_file_path: str = sbs_file_path
        self._gonad_file_name: str = gonad_file_name
        self._number_of_points: int = 0

    def saved_state(self) -> bool:
        points_layer_file_path: str = os.path.join(
            self._scored_nuclei_dir, self._points_layer_file_name
        )
        return os.path.exists(points_layer_file_path)

    def get_image_path(self) -> str:
        return self._image_file_path

    def get_display_name(self) -> str:
        return (
            self._gonad_file_name
            + " - "
            + self._region_name
            + " - "
            + self._name
        )

    def get_number_of_points(self) -> int:
        return self._number_of_points


OpenFileReturns = Literal["failed"] | None | tuple[list[CLSPSbsObject], str]


def open_scoring_file(
    napari_viewer: "ViewerModel", parent_widget: QWidget
) -> OpenFileReturns:
    if len(napari_viewer.layers) > 0:
        confirmed_result: bool = confirm_dialog(
            napari_viewer,
            "Layers are open, it is required to close all layers before scoring. Confirm?",
        )
        if not confirmed_result:
            return None
    file_path = get_file(
        parent_widget,
        f"Select scoring image (.tif) or multi gonad file (*{MULTI_GONAD_FILE_EXTENSION})",
    )
    if file_path is None:
        return None
    validated_parsers_dict: dict[str, ConfigParser] | Literal["invalid"]
    if file_path.endswith(".tif"):
        validated_parsers_dict = validate_image_file_path(file_path)
    elif file_path.endswith(MULTI_GONAD_FILE_EXTENSION):
        validated_parsers_dict = validate_multigonad_file_path(file_path)
    else:
        validated_parsers_dict = "invalid"
    if validated_parsers_dict == "invalid":
        return "failed"
    clsp_sbs_object_list: list[CLSPSbsObject] = []
    for gonad_file_path, gonad_parser in validated_parsers_dict.items():
        gonad_file_name: str = os.path.basename(gonad_file_path)
        sbs_directory: str = os.path.join(
            gonad_file_path,
            DEFAULT_PROJECT_NAME,
            PICK_NUCLEI_DIR_NAME,
            CUT_SBS_DIR_NAME,
        )
        if not os.path.exists(sbs_directory):
            show_info(f"The sbs directory {sbs_directory} doesn't exist")
            print(f"The sbs directory {sbs_directory} doesn't exist")
            return "failed"
        scored_nuclei_dir: str = os.path.join(
            gonad_file_path, DEFAULT_PROJECT_NAME, SCORED_NUCLEI_DIR_NAME
        )
        os.makedirs(scored_nuclei_dir, exist_ok=True)
        for region_index in range(len(gonad_parser["NucleiCount"])):
            region_string = "region-" + str(region_index + 1)
            number_of_sbs: int = int(
                gonad_parser["NucleiCount"][region_string]
            )
            for sbs_index in range(number_of_sbs):
                sbs_string: str = "sbs" + str(sbs_index + 1)
                sbs_file_name: str = (
                    region_string + "_" + sbs_string + SBS_FILE_NAME_EXTENSION
                )
                sbs_file_path: str = os.path.join(sbs_directory, sbs_file_name)
                if not os.path.exists(sbs_file_path):
                    show_info(
                        f"The sbs file with path {sbs_file_path} doesn't exist"
                    )
                    print(
                        f"The sbs file with path {sbs_file_path} doesn't exist"
                    )
                    return "failed"
                current_sbs_object: CLSPSbsObject = CLSPSbsObject(
                    napari_viewer,
                    sbs_string,
                    region_string,
                    scored_nuclei_dir,
                    sbs_file_path,
                    gonad_file_name,
                )
                clsp_sbs_object_list.append(current_sbs_object)
    return (clsp_sbs_object_list, file_path)


def str_to_bool(string: str) -> bool:
    return string.lower() in {"true", "1"}


def get_valid_points_summary_parser_from_image_dir(
    image_dir: str,
) -> ConfigParser | None:
    summary_points_file_path: str = os.path.join(
        image_dir,
        DEFAULT_PROJECT_NAME,
        PICK_NUCLEI_DIR_NAME,
        POINTS_SUMMARY_FILE_NAME,
    )
    if not os.path.exists(summary_points_file_path):
        return None
    config_parser: ConfigParser = ConfigParser()
    config_parser.read(summary_points_file_path)
    if not config_parser.has_section("NucleiCount"):
        return None
    if len(config_parser["NucleiCount"]) <= 0:
        return None
    for region_index in range(len(config_parser["NucleiCount"])):
        region_string: str = "region-" + str(region_index + 1)
        saved_sbs_state: str = config_parser["SavedSbsState"][region_string]
        bool_saved_sbs_sate: bool = str_to_bool(saved_sbs_state)
        if not bool_saved_sbs_sate:
            show_info(
                f"The directory {image_dir} has not created all SBS files.ERROR"
            )
            return None
    return config_parser


def validate_image_file_path(
    file_path: str,
) -> dict[str, ConfigParser] | Literal["invalid"]:
    parent_dir = os.path.dirname(file_path)
    image_summary_points_parser: ConfigParser | None = (
        get_valid_points_summary_parser_from_image_dir(parent_dir)
    )
    if image_summary_points_parser is None:
        return "invalid"
    return {parent_dir: image_summary_points_parser}


def validate_multigonad_file_path(
    file_path: str,
) -> dict[str, ConfigParser] | Literal["invalid"]:
    gonad_parser: ConfigParser = ConfigParser()
    gonad_parser.read(file_path)
    if not gonad_parser.has_section("GonadDirectoryPaths"):
        return "invalid"
    if len(gonad_parser["GonadDirectoryPaths"]) <= 0:
        return "invalid"
    individual_gonad_parsers: dict[str, ConfigParser] = {}
    for gonad_index in range(len(gonad_parser["GonadDirectoryPaths"])):
        gonad_str = "gonad-" + str(gonad_index + 1)
        gonad_path = gonad_parser["GonadDirectoryPaths"][gonad_str]
        validated_parser: ConfigParser | None = (
            get_valid_points_summary_parser_from_image_dir(gonad_path)
        )
        if validated_parser is None:
            show_info(
                f"The gonad path {gonad_path} had an invalid points summary file. ERROR"
            )
            return "invalid"
        individual_gonad_parsers[gonad_path] = validated_parser
    return individual_gonad_parsers


class CLSPRegion:
    def __init__(
        self,
        napari_viewer: "ViewerModel",
        region_index: int,
        scored_nuclei_dir: str,
    ):
        self._napari_viewer = napari_viewer
        self._region_index: int = region_index
        self._score_nuclei_dir = scored_nuclei_dir

        self._sbs_dict: dict[str, CLSPSbsObject] = {}

    @property
    def region_index(self) -> int:
        return self._region_index

    @region_index.setter
    def region_index(self, value: int) -> None:
        self._region_index = value

    def name(self) -> str:
        return "region-" + str(self._region_index)
