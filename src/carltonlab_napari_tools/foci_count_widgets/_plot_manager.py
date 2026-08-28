from datetime import datetime
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

from carltonlab_napari_tools._shared_variables import (
    NUCLEI_POINTS_FEATURES_TABLE_FILE_NAME,
    PICK_NUCLEI_DIR_NAME,
    PROJECT_FILE_DIR_NAME,
    RESULTS_DIR,
)
from carltonlab_napari_tools._utils import resolve_clsp_project_path


def _load_project_plot_data(project_path: Path) -> pd.DataFrame | None:
    resolved_project_path = resolve_clsp_project_path(project_path)
    if resolved_project_path is None:
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

    required_columns = {"region", "scored_foci_number"}
    if not required_columns.issubset(features.columns):
        return None

    plot_data = features.loc[:, ["region", "scored_foci_number"]].dropna()
    if plot_data.empty:
        return None

    plot_data["region"] = pd.to_numeric(plot_data["region"], errors="coerce")
    plot_data["scored_foci_number"] = pd.to_numeric(
        plot_data["scored_foci_number"], errors="coerce"
    )
    plot_data = plot_data.dropna()
    if plot_data.empty:
        return None

    return (
        plot_data.groupby("region", sort=True)["scored_foci_number"]
        .sum()
        .rename("foci_count")
        .reset_index()
    )


def _save_bar_plot(
    plot_data: pd.DataFrame,
    output_stem: Path,
    title: str,
) -> tuple[Path, Path]:
    output_stem.parent.mkdir(parents=True, exist_ok=True)

    figure, axis = plt.subplots(figsize=(8, 4))
    plot_data.set_index("region")["foci_count"].plot.bar(ax=axis)
    axis.set_xlabel("Region")
    axis.set_ylabel("Foci count")
    axis.set_title(title)
    axis.tick_params(axis="x", rotation=0)
    figure.tight_layout()

    pdf_path = output_stem.with_suffix(".pdf")
    png_path = output_stem.with_suffix(".png")
    figure.savefig(pdf_path)
    figure.savefig(png_path, dpi=300)
    plt.close(figure)
    return pdf_path, png_path


def generate_foci_count_plots(
    project_paths: list[Path],
    combined_output_directory: Path,
) -> list[Path]:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    project_plot_data: list[tuple[Path, pd.DataFrame]] = []

    for project_path in project_paths:
        plot_data = _load_project_plot_data(project_path)
        if plot_data is not None:
            project_plot_data.append((project_path, plot_data))

    if not project_plot_data:
        return []

    created_paths: list[Path] = []
    combined_rows = []
    for project_path, plot_data in project_plot_data:
        genotype = project_path.parent.name
        combined_rows.append(plot_data.assign(genotype=genotype))

        resolved_project_path = resolve_clsp_project_path(project_path)
        if resolved_project_path is None:
            continue
        project_output_directory = (
            resolved_project_path / PROJECT_FILE_DIR_NAME / RESULTS_DIR
        )
        project_stem = project_output_directory / f"foci_count_{timestamp}"
        created_paths.extend(
            _save_bar_plot(
                plot_data,
                project_stem,
                project_path.name,
            )
        )

    combined_data = (
        pd.concat(combined_rows, ignore_index=True)
        .groupby(["region", "genotype"], sort=True)["foci_count"]
        .sum()
        .unstack("genotype")
        .fillna(0)
    )
    combined_output_stem = (
        combined_output_directory / f"foci_count_{timestamp}"
    )
    combined_output_stem.parent.mkdir(parents=True, exist_ok=True)

    figure, axis = plt.subplots(figsize=(8, 4))
    combined_data.plot.bar(ax=axis)
    axis.set_xlabel("Region")
    axis.set_ylabel("Foci count")
    axis.set_title("Foci count by genotype")
    axis.tick_params(axis="x", rotation=0)
    axis.legend(title="Genotype")
    figure.tight_layout()

    combined_pdf = combined_output_stem.with_suffix(".pdf")
    combined_png = combined_output_stem.with_suffix(".png")
    figure.savefig(combined_pdf)
    figure.savefig(combined_png, dpi=300)
    plt.close(figure)
    created_paths.extend((combined_pdf, combined_png))
    return created_paths
