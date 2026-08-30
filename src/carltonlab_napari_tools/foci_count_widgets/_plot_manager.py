from datetime import datetime
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.axes import Axes
from matplotlib.figure import Figure
from scipy.interpolate import splev, splprep

from carltonlab_napari_tools._shared_variables import (
    CLSP_PLOTS_DIRECTORY_PREFIX,
    FOCI_COUNT_AVERAGE_PLOT_NAME,
    FOCI_COUNT_CUMULATIVE_PLOT_NAME,
    FOCI_COUNT_PLOT_FILE_NAME_PREFIX,
    FOCI_COUNT_POSITIONS_PLOT_NAME,
    FOCI_COUNT_SUM_PLOT_NAME,
    NUCLEI_POINTS_FEATURES_TABLE_FILE_NAME,
    PICK_NUCLEI_DIR_NAME,
    PROJECT_FILE_DIR_NAME,
    REGIONS_CONFIGURATION_FILE_NAME,
    REGIONS_DIR_NAME,
    RESULTS_DIR,
    SPLINE_LAYER_FILE_NAME,
)
from carltonlab_napari_tools._utils import resolve_clsp_project_path
from carltonlab_napari_tools.spline_manager._spline_manager import (
    load_regions_configuration,
    project_point_to_polyline,
)

REGION_COLORS = (
    "#ff0000",
    "#00ffff",
    "#ffff00",
)


def _load_interpolated_spline(project_path: Path) -> np.ndarray | None:
    resolved_project_path = resolve_clsp_project_path(project_path)
    if resolved_project_path is None:
        return None

    regions_directory = (
        resolved_project_path / PROJECT_FILE_DIR_NAME / REGIONS_DIR_NAME
    )
    spline_path = regions_directory / SPLINE_LAYER_FILE_NAME
    configuration = load_regions_configuration(
        regions_directory / REGIONS_CONFIGURATION_FILE_NAME
    )
    if not spline_path.is_file() or configuration is None:
        return None

    interpolation_order = configuration[0]
    if interpolation_order is None:
        return None

    try:
        spline_data = pd.read_csv(spline_path)
    except (OSError, pd.errors.EmptyDataError, pd.errors.ParserError):
        return None

    if not {"axis-0", "axis-1"}.issubset(spline_data.columns):
        return None

    points = spline_data[["axis-0", "axis-1"]].to_numpy(dtype=np.float64)
    if len(points) <= interpolation_order:
        return None

    try:
        tck, _ = splprep(
            points.T,
            s=0,
            k=interpolation_order,
            per=False,
        )
    except ValueError:
        return None

    sample_count = max(1_000, len(points) * 100)
    samples = np.linspace(0.0, 1.0, sample_count)
    return np.stack(splev(samples, tck), axis=1).astype(np.float32)


def _load_project_plot_data(project_path: Path) -> pd.DataFrame | None:
    resolved_project_path = resolve_clsp_project_path(project_path)
    if resolved_project_path is None:
        return None

    regions_directory = (
        resolved_project_path / PROJECT_FILE_DIR_NAME / REGIONS_DIR_NAME
    )
    configuration = load_regions_configuration(
        regions_directory / REGIONS_CONFIGURATION_FILE_NAME
    )
    if configuration is None or configuration[1] is None:
        return None

    features_path = (
        resolved_project_path
        / PROJECT_FILE_DIR_NAME
        / PICK_NUCLEI_DIR_NAME
        / NUCLEI_POINTS_FEATURES_TABLE_FILE_NAME
    )
    if not features_path.is_file():
        return None

    try:
        features = pd.read_csv(features_path)
    except (OSError, pd.errors.EmptyDataError, pd.errors.ParserError):
        return None

    required_columns = {
        "region",
        "scored_foci_number",
        "stitched_x_coord",
        "stitched_y_coord",
    }
    if not required_columns.issubset(features.columns):
        return None

    plot_data = features.loc[
        :,
        [
            "region",
            "scored_foci_number",
            "stitched_x_coord",
            "stitched_y_coord",
        ],
    ].copy()
    for column in plot_data.columns:
        plot_data[column] = pd.to_numeric(
            plot_data[column],
            errors="coerce",
        )

    plot_data = plot_data.dropna()
    if plot_data.empty:
        return None

    spline = _load_interpolated_spline(project_path)
    if spline is None:
        return None

    projected_positions = [
        project_point_to_polyline(
            np.array([row["stitched_y_coord"], row["stitched_x_coord"]]),
            spline,
        )[1]
        for _, row in plot_data.iterrows()
    ]
    plot_data["normalized_arc_position"] = projected_positions
    plot_data["genotype"] = project_path.parent.name
    return plot_data


def _region_color(region: float) -> str:
    return REGION_COLORS[(int(region) - 1) % len(REGION_COLORS)]


def _save_figure_pair(
    figure: Figure,
    output_directory: Path,
    plot_name: str,
    timestamp: str,
) -> list[Path]:
    output_directory.mkdir(parents=True, exist_ok=True)
    output_stem = output_directory / f"{plot_name}_{timestamp}"
    pdf_path = output_stem.with_suffix(".pdf")
    png_path = output_stem.with_suffix(".png")
    figure.savefig(pdf_path)
    figure.savefig(png_path, dpi=300)
    plt.close(figure)
    return [pdf_path, png_path]


def _configure_axis(axis: Axes, title: str, y_label: str) -> None:
    axis.set_title(title)
    axis.set_xlabel("Region")
    axis.set_ylabel(y_label)
    axis.tick_params(axis="x", rotation=0)


def _make_region_bar_plot(
    plot_data: pd.DataFrame,
    *,
    average: bool,
    title: str,
) -> Figure:
    grouped = (
        plot_data.groupby("region")["scored_foci_number"].mean()
        if average
        else plot_data.groupby("region")["scored_foci_number"].sum()
    )
    figure, axis = plt.subplots(figsize=(8, 4))
    axis.bar(
        grouped.index.astype(str),
        grouped.values,
        color=[_region_color(region) for region in grouped.index],
    )
    _configure_axis(
        axis,
        title,
        "Average foci per nucleus" if average else "Total foci",
    )
    figure.tight_layout()
    return figure


def _make_position_plot(
    plot_data: pd.DataFrame,
    *,
    cumulative: bool,
    title: str,
) -> Figure:
    figure, axis = plt.subplots(figsize=(8, 4))

    if cumulative:
        ordered_data = plot_data.sort_values("normalized_arc_position")
        cumulative_positions = np.arange(1, len(ordered_data) + 1)
        axis.plot(
            ordered_data["normalized_arc_position"],
            cumulative_positions,
            color="black",
            linewidth=1,
        )
        axis.scatter(
            ordered_data["normalized_arc_position"],
            cumulative_positions,
            c=[_region_color(region) for region in ordered_data["region"]],
            s=20,
        )
        axis.set_ylabel("Cumulative nuclei")
    else:
        axis.scatter(
            plot_data["normalized_arc_position"],
            plot_data["scored_foci_number"],
            c=[_region_color(region) for region in plot_data["region"]],
            s=20,
        )
        axis.set_ylabel("Foci count per nucleus")

    axis.set_title(title)
    axis.set_xlabel("Normalized spline arc position")
    axis.set_xlim(0, 1)
    axis.grid(True, alpha=0.3)
    figure.tight_layout()
    return figure


def _save_project_plots(
    project_path: Path,
    plot_data: pd.DataFrame,
    output_directory: Path,
    timestamp: str,
) -> list[Path]:
    created_paths: list[Path] = []

    for average, plot_name in (
        (False, FOCI_COUNT_SUM_PLOT_NAME),
        (True, FOCI_COUNT_AVERAGE_PLOT_NAME),
    ):
        created_paths.extend(
            _save_figure_pair(
                _make_region_bar_plot(
                    plot_data,
                    average=average,
                    title=project_path.name,
                ),
                output_directory,
                plot_name,
                timestamp,
            )
        )

    for cumulative, plot_name in (
        (False, FOCI_COUNT_POSITIONS_PLOT_NAME),
        (True, FOCI_COUNT_CUMULATIVE_PLOT_NAME),
    ):
        created_paths.extend(
            _save_figure_pair(
                _make_position_plot(
                    plot_data,
                    cumulative=cumulative,
                    title=project_path.name,
                ),
                output_directory,
                plot_name,
                timestamp,
            )
        )

    return created_paths


def _save_combined_plots(
    plot_data: pd.DataFrame,
    output_directory: Path,
    timestamp: str,
) -> list[Path]:
    created_paths: list[Path] = []

    for average, plot_name in (
        (False, FOCI_COUNT_SUM_PLOT_NAME),
        (True, FOCI_COUNT_AVERAGE_PLOT_NAME),
    ):
        grouped = (
            plot_data.groupby(["region", "genotype"])[
                "scored_foci_number"
            ].mean()
            if average
            else plot_data.groupby(["region", "genotype"])[
                "scored_foci_number"
            ].sum()
        )
        grouped = grouped.unstack("genotype", fill_value=0)

        figure, axis = plt.subplots(figsize=(8, 4))
        grouped.plot.bar(
            ax=axis,
            color=[_region_color(region) for region in grouped.index],
        )
        _configure_axis(
            axis,
            "Combined foci count by genotype",
            "Average foci per nucleus" if average else "Total foci",
        )
        axis.legend(title="Genotype")
        figure.tight_layout()
        created_paths.extend(
            _save_figure_pair(
                figure,
                output_directory,
                plot_name,
                timestamp,
            )
        )

    for cumulative, plot_name in (
        (False, FOCI_COUNT_POSITIONS_PLOT_NAME),
        (True, FOCI_COUNT_CUMULATIVE_PLOT_NAME),
    ):
        figure, axis = plt.subplots(figsize=(8, 4))
        for genotype, genotype_data in plot_data.groupby("genotype"):
            if cumulative:
                genotype_data = genotype_data.sort_values(
                    "normalized_arc_position"
                )
                axis.plot(
                    genotype_data["normalized_arc_position"],
                    np.arange(1, len(genotype_data) + 1),
                    linewidth=1,
                    label=genotype,
                )
                axis.scatter(
                    genotype_data["normalized_arc_position"],
                    np.arange(1, len(genotype_data) + 1),
                    c=[
                        _region_color(region)
                        for region in genotype_data["region"]
                    ],
                    s=20,
                )
            else:
                axis.scatter(
                    genotype_data["normalized_arc_position"],
                    genotype_data["scored_foci_number"],
                    c=[
                        _region_color(region)
                        for region in genotype_data["region"]
                    ],
                    s=20,
                    label=genotype,
                )

        axis.set_title("Combined nuclei positions by genotype")
        axis.set_xlabel("Normalized spline arc position")
        axis.set_ylabel(
            "Cumulative nuclei" if cumulative else "Foci count per nucleus"
        )
        axis.set_xlim(0, 1)
        axis.grid(True, alpha=0.3)
        axis.legend(title="Genotype")
        figure.tight_layout()
        created_paths.extend(
            _save_figure_pair(
                figure,
                output_directory,
                plot_name,
                timestamp,
            )
        )

    return created_paths


def generate_foci_count_plots(
    project_paths: list[Path],
    combined_output_directory: Path,
) -> list[Path]:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    project_data: list[tuple[Path, pd.DataFrame]] = []

    for project_path in project_paths:
        plot_data = _load_project_plot_data(project_path)
        if plot_data is not None:
            project_data.append((project_path, plot_data))

    if not project_data:
        return []

    combined_plot_data = pd.concat(
        [plot_data for _, plot_data in project_data],
        ignore_index=True,
    )
    created_paths: list[Path] = []
    combined_directory = (
        combined_output_directory / f"{CLSP_PLOTS_DIRECTORY_PREFIX}{timestamp}"
    )
    created_paths.extend(
        _save_combined_plots(
            combined_plot_data,
            combined_directory,
            timestamp,
        )
    )

    for project_path, plot_data in project_data:
        resolved_project_path = resolve_clsp_project_path(project_path)
        if resolved_project_path is None:
            continue

        project_directory = (
            resolved_project_path
            / PROJECT_FILE_DIR_NAME
            / RESULTS_DIR
            / f"{CLSP_PLOTS_DIRECTORY_PREFIX}{timestamp}"
        )
        created_paths.extend(
            _save_project_plots(
                project_path,
                plot_data,
                project_directory,
                timestamp,
            )
        )

    return created_paths


def is_project_plot_complete(project_path: Path) -> bool:
    resolved_project_path = resolve_clsp_project_path(project_path)
    if resolved_project_path is None:
        return False

    output_directory = (
        resolved_project_path / PROJECT_FILE_DIR_NAME / RESULTS_DIR
    )
    pdf_stems = {
        path.stem
        for path in output_directory.rglob(
            f"{FOCI_COUNT_PLOT_FILE_NAME_PREFIX}*.pdf"
        )
    }
    png_stems = {
        path.stem
        for path in output_directory.rglob(
            f"{FOCI_COUNT_PLOT_FILE_NAME_PREFIX}*.png"
        )
    }
    return bool(pdf_stems & png_stems)
