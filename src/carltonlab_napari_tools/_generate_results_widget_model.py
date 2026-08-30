import os
from pathlib import Path

import pandas as pd
from napari.utils.notifications import show_info

from carltonlab_napari_tools._score_nuclei_widget_model import (
    generate_scored_points_spline_plot,
    generate_scored_points_spline_summary,
    get_valid_points_summary_parser_from_image_dir,
)
from carltonlab_napari_tools._shared_variables import (
    CUT_SBS_DIR_NAME,
    DEFAULT_PROJECT_NAME,
    PICK_NUCLEI_DIR_NAME,
    SBS_FILE_NAME_EXTENSION,
    SCORED_NUCLEI_DIR_NAME,
    SCORED_NUCLEI_FOCI_SUMMARY_FILE_NAME,
    SCORED_NUCLEI_POINTS_FILE_NAME_EXTENSION,
)


def generate_summaries(gonad_dirs: list[str]) -> list[str]:
    created_paths: list[str] = []
    for gonad_dir in gonad_dirs:
        created_path = generate_scored_points_spline_summary(gonad_dir)
        if created_path is not None:
            created_paths.append(created_path)
    if not created_paths:
        show_info("Failed to create scored points spline summary")
    return created_paths


def generate_plots(gonad_dirs: list[str]) -> list[str]:
    created_paths: list[str] = []
    for gonad_dir in gonad_dirs:
        created_path = generate_scored_points_spline_plot(gonad_dir)
        if created_path is not None:
            created_paths.append(created_path)
    if not created_paths:
        show_info("Failed to create scored points spline plot")
    return created_paths


def _read_sbs_flags(image_path: str) -> list[str]:
    image_path_obj = Path(image_path)
    flags_path = image_path_obj.with_name(image_path_obj.stem + "_flags.txt")
    if not flags_path.exists():
        return []
    with flags_path.open() as handle:
        return [line.strip() for line in handle if line.strip()]


def _load_scored_nuclei_foci_count(
    scored_nuclei_dir: str, region_name: str, sbs_index: int
) -> int | None:
    sbs_name = f"sbs{sbs_index}"
    points_file_name = (
        region_name + "_" + sbs_name + SCORED_NUCLEI_POINTS_FILE_NAME_EXTENSION
    )
    points_file_path = os.path.join(scored_nuclei_dir, points_file_name)
    if os.path.exists(points_file_path):
        points_df = pd.read_csv(points_file_path)
        return int(len(points_df))

    zero_points_file_name = region_name + "_" + sbs_name + "_zero_points.txt"
    zero_points_file_path = os.path.join(
        scored_nuclei_dir, zero_points_file_name
    )
    if os.path.exists(zero_points_file_path):
        return 0
    return None


def generate_scored_nuclei_foci_summary(
    gonad_dir: str, output_csv_path: str | None = None
) -> str | None:
    project_dir = os.path.join(gonad_dir, DEFAULT_PROJECT_NAME)
    scored_nuclei_dir = os.path.join(project_dir, SCORED_NUCLEI_DIR_NAME)
    if not os.path.exists(scored_nuclei_dir):
        return None

    summary_parser = get_valid_points_summary_parser_from_image_dir(gonad_dir)
    if summary_parser is None:
        return None
    nuclei_count = summary_parser["NucleiCount"]
    if len(nuclei_count) <= 0:
        return None

    cut_sbs_dir = os.path.join(
        project_dir, PICK_NUCLEI_DIR_NAME, CUT_SBS_DIR_NAME
    )
    rows: list[dict[str, str | int | None]] = []
    for region_index in range(len(nuclei_count)):
        region_name = f"region-{region_index + 1}"
        if region_name not in nuclei_count:
            continue
        sbs_count = int(nuclei_count[region_name])
        for sbs_index in range(1, sbs_count + 1):
            sbs_image_name = (
                f"{region_name}_sbs{sbs_index}{SBS_FILE_NAME_EXTENSION}"
            )
            sbs_image_path = os.path.join(cut_sbs_dir, sbs_image_name)
            flags = sorted(set(_read_sbs_flags(sbs_image_path)))
            ignored = "ignore" in flags
            foci_count = None
            if not ignored:
                foci_count = _load_scored_nuclei_foci_count(
                    scored_nuclei_dir, region_name, sbs_index
                )
            rows.append(
                {
                    "region_name": region_name,
                    "sbs": sbs_index,
                    "sbs_image_name": sbs_image_name,
                    "flags": ",".join(flags),
                    "foci_count": foci_count,
                }
            )

    if not rows:
        return None

    output_df = pd.DataFrame(
        rows,
        columns=[
            "region_name",
            "sbs",
            "sbs_image_name",
            "flags",
            "foci_count",
        ],
    )
    if output_csv_path is None:
        output_csv_path = os.path.join(
            scored_nuclei_dir, SCORED_NUCLEI_FOCI_SUMMARY_FILE_NAME
        )
    output_df.to_csv(output_csv_path, index=False)
    return output_csv_path


def generate_foci_summaries(gonad_dirs: list[str]) -> list[str]:
    created_paths: list[str] = []
    for gonad_dir in gonad_dirs:
        created_path = generate_scored_nuclei_foci_summary(gonad_dir)
        if created_path is not None:
            created_paths.append(created_path)
    if not created_paths:
        show_info("Failed to create scored nuclei foci summary")
    return created_paths
