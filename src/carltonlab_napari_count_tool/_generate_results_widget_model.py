from napari.utils.notifications import show_info

from carltonlab_napari_count_tool._score_nuclei_widget_model import (
    generate_scored_points_spline_plot,
    generate_scored_points_spline_summary,
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
