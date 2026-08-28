from configparser import ConfigParser
from pathlib import Path


def _discover_project_types() -> dict[str, str]:
    package_root = Path(__file__).resolve().parent
    project_types: dict[str, str] = {}

    for config_path in package_root.rglob("*_project.config"):
        config = ConfigParser()
        try:
            config.read(config_path)
            project_type = config.get("project", "type")
        except (ConfigParser.Error, OSError, KeyError):
            continue

        project_types[project_type] = str(
            config_path.relative_to(package_root)
        )

    return project_types


DEFAULT_PROJECT_NAME = "cl_score_points_project"
DEFAULT_PROJECT_EXTENSION = "_clsp"

PROJECT_TYPES = _discover_project_types()

IMAGE_CONTRASTS_FILE_NAME = "cl_image_contrasts.config"
TILE_CONTRASTS_FILE_NAME_SUFFIX = "_contrasts.config"

PICK_NUCLEI_DIR_NAME = "pick_nuclei"
SBS_FLAGS_FILE_NAME = "sbs_flags.config"
SBS_LOCKS_DIR_NAME = "sbs_locks"
SBS_LOCK_FILE_SUFFIX = ".lock"
SBS_LOCK_TIMEOUT_SECONDS = 300
SCORING_SAVE_LOCK_NAME = "scoring_save"
NUCLEI_POINTS_LAYER_FILE_NAME = "nuclei_points_layer.csv"
NUCLEI_POINTS_FEATURES_TABLE_FILE_NAME = "nuclei_points_features_table.csv"
POINTS_SUMMARY_FILE_NAME = "points_summary.csv"
REGION_ROOT_NAME = "region-"
SBS_ROOT_NAME = "sbs-"
POINT_FILE_NAME_EXTENSION = "_points_layer.csv"
FILTERED_CSV_FILE_NAME_SUFFIX = "_filtered.csv"
AUTO_COUNT_POINTS_FILE_NAME_EXTENSION = "_points.csv"
AUTO_COUNT_FILTERED_POINTS_FILE_NAME_EXTENSION = "_filtered_points.csv"
SQUARES_FILE_NAME_EXTENSION = "_squares_layer.csv"
AUTO_COUNT_PROCESSED_SPOTS_IMAGE_FILE_NAME_SUFFIX = (
    "_processed_spots_image.tif"
)
AUTO_COUNT_PREPROCESSING_STATS_FILE_NAME_SUFFIX = "_preprocessing_stats.json"
AUTO_COUNT_BINARY_MASK_FILE_NAME_SUFFIX_TEMPLATE = (
    "_channel_{channel_number}_binary_mask.tif"
)
SBS_FILE_NAME_EXTENSION = "_cut_nuclei.tif"
CUT_SBS_DIR_NAME = "cut_sbs"
SBS_METADATA_FILE_NAME = "sbs_metadata.csv"
PICK_NUCLEI_REPORT_FILE_NAME = "pick_nuclei_spline_intensity_report.csv"
PICK_NUCLEI_REPORT_PLOT_FILE_NAME = "pick_nuclei_spline_intensity_report.pdf"
PICK_NUCLEI_REPORT_PLOT_NORM_FILE_NAME = (
    "pick_nuclei_spline_intensity_report_normalized.pdf"
)


REGIONS_DIR_NAME = "regions"
SPLINE_LAYER_FILE_NAME = "clt_spline_layer.csv"
CLSA_SPLINE_LAYER_FILE_NAME_SUFFIX = "_clsa_spline_layer.csv"
CLSA_RAW_SPLINE_LAYER_FILE_NAME_SUFFIX = "_clsa_raw_spline_layer.csv"
CLSA_SPLINE_PREVIEW_FILE_NAME_SUFFIX = "_clsa_spline_preview.tif"
EDITED_REGIONS_EXPANSION_VALUES_FILE_NAME = (
    "clt_expanded_regions_values.config"
)
EDITED_REGIONS_FILE_NAME = "clt_expanded_regions_layer.csv"

MULTI_GONAD_FILE_SUFFIX = "clsp_"
MULTI_GONAD_FILE_EXTENSION = "_multi_gonad_file.config"
MULTIGONAD_FOCI_COUNT_TOOL_FILE_SUFFIX = "_multigonad_clsp.config"
SCORED_NUCLEI_DIR_NAME = "scored_nuclei"
SCORED_NUCLEI_POINTS_FILE_NAME_EXTENSION = "_scored_nuclei_points.csv"
SCORED_NUCLEI_FOCI_SUMMARY_FILE_NAME = "scored_nuclei_foci_summary.csv"
SCORED_NUCLEI_SUMMARY_FILE_NAME = "scored_points_spline_summary.csv"
SCORED_NUCLEI_PLOT_FILE_NAME = "scored_points_spline_cumulative_plot.pdf"
AUTO_COUNT_DIR_NAME = "auto_count"
TILES_DIR_NAME = "tiles"
TILES_CONFIG_FILE_NAME = "tiles.config"
STITCHED_IMAGE_DIR_NAME = "stitched_image"
EXTRACTED_CHANNELS_FILE_NAME = "extracted_channels.config"
STITCHED_IMAGE_SUFFIX = "_stitched.ome.zarr"
SUPPORTED_STITCH_EXTENSIONS = [
    ".tif",
    ".tiff",
    ".ome.zarr",
    ".dv",
    ".dv_add_decon",
    ".zs",
]
PROJECT_FILE_DIR_NAME = "project_file"
SEGMENTATION_DIR_NAME = "segmentation"
SBS_IMAGES_DIR_NAME = "sbs_images"

CLSA_PROJECT_SUFFIX = "_clsa_project"
CLSP_PROJECT_SUFFIX = "_clsp_project"

RESULTS_DIR = "summaries_and_plots"
TILE_POSITIONS_FILE_NAME_SUFFIX = "_tile_positions.csv"
SEGMENTATION_MASKS_FILE_NAME_SUFFIX = "_meiotic_3d_crops_masks.npy"
FILTERED_SEGMENTATION_MASKS_FILE_NAME_SUFFIX = "_filtered.npy"
SBS_TILE_COORDINATES_FILE_NAME_SUFFIX = "_tile_coordinates.csv"
SBS_STITCHED_COORDINATES_FILE_NAME_SUFFIX = "_stitched_coordinates.csv"

DEFAULT_SEPARATOR_THICKNESS = 2
DEFAULT_SEPARATOR_SPACING = 6
