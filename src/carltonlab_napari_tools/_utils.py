from __future__ import annotations

import json
import os
from pathlib import Path

from napari.utils.notifications import show_error

from carltonlab_napari_tools._shared_variables import (
    CLSP_PROJECT_SUFFIX,
    PROJECT_TYPES,
    STITCHED_IMAGE_DIR_NAME,
)


def resolve_clsp_project_path(starting_path: Path) -> Path | None:
    if starting_path.name.endswith(CLSP_PROJECT_SUFFIX):
        return starting_path

    try:
        project_paths = sorted(
            path
            for path in starting_path.iterdir()
            if path.is_dir() and path.name.endswith(CLSP_PROJECT_SUFFIX)
        )
    except OSError:
        return None

    return project_paths[0] if project_paths else None


def get_project_stitched_image_path(
    project_path: Path,
) -> Path | None:
    stitched_directory = project_path / STITCHED_IMAGE_DIR_NAME
    stitched_paths = sorted(stitched_directory.glob("*.ome.zarr"))
    return stitched_paths[0] if stitched_paths else None


SUPPORTED_IMAGE_EXTENSIONS: tuple[str, ...] = (
    ".ome.zarr",
    ".ome.tif",
    ".ome.tiff",
    ".tif",
    ".tiff",
    ".czi",
    ".dv",
    ".zs",
    ".deconzs",
    ".r3d",
    ".lif",
    ".nd2",
    ".sldy",
)


def load_project_structure_from_json(project_type: str) -> list[Path]:
    if project_type not in PROJECT_TYPES:
        return []

    resource_path = (
        Path(__file__).resolve().parent
        / "resources"
        / f"{project_type}_structure.json"
    )

    try:
        with resource_path.open("r", encoding="utf-8") as structure_file:
            structure = json.load(structure_file)
    except (OSError, json.JSONDecodeError) as exc:
        show_error(f"Could not load project structure: {exc}")
        return []

    directory_paths: list[Path] = []

    def collect_directories(
        directory_tree: dict[str, object],
        parent: Path = Path(),
    ) -> None:
        for directory_name, children in directory_tree.items():
            directory_path = parent / directory_name
            directory_paths.append(directory_path)

            if isinstance(children, dict):
                collect_directories(children, directory_path)

    directory_tree = structure.get("dir_tree")
    if not isinstance(directory_tree, dict):
        show_error("Project structure does not contain a valid dir_tree")
        return []

    collect_directories(directory_tree)
    return directory_paths


def create_project_structure(project_path: Path, project_type: str) -> bool:
    if project_path.exists() and not project_path.is_dir():
        show_error(f"Project path is not a directory: {project_path}")
        return False

    directory_paths = load_project_structure_from_json(project_type)
    if not directory_paths:
        return False

    try:
        project_path.mkdir(parents=True, exist_ok=True)
        for directory_path in directory_paths:
            (project_path / directory_path).mkdir(
                parents=True,
                exist_ok=True,
            )
    except OSError as exc:
        show_error(f"Could not create project structure: {exc}")
        return False

    return True


def create_stitched_project_structure(project_path: Path) -> bool:
    if project_path.exists():
        show_error(f"Project path {str(project_path)} already exists")
        return False
    project_path.mkdir(parents=True, exist_ok=True)
    return True


def parse_channel_string(channel_string: str) -> list[int]:
    if not channel_string.strip():
        return []

    channels: list[int] = []
    for part in channel_string.split(","):
        part = part.strip()
        if not part:
            return []

        if "-" in part:
            range_parts = part.split("-")
            if len(range_parts) != 2:
                return []

            try:
                start, end = (int(value.strip()) for value in range_parts)
            except ValueError:
                return []

            if start > end:
                return []
            channels.extend(range(start, end + 1))
            continue

        try:
            channels.append(int(part))
        except ValueError:
            return []

    return channels


def get_supported_image_extension(path: str | Path) -> str | None:
    file_path = Path(path)
    lower_name = file_path.name.lower()

    for extension in SUPPORTED_IMAGE_EXTENSIONS:
        if lower_name.endswith(extension):
            return extension

    return None


def is_supported_image_file(path: str | Path) -> bool:
    file_path = Path(path)
    return (
        file_path.is_file()
        and get_supported_image_extension(file_path) is not None
    )


def is_supported_image_entry(path: str | Path) -> bool:
    entry_path = Path(path)
    image_extension = get_supported_image_extension(entry_path)
    if image_extension is None:
        return False

    if image_extension == ".ome.zarr":
        return entry_path.is_dir()

    return entry_path.is_file()


def validate_image_directory(
    directory_path: str | Path,
) -> tuple[bool, str | None]:
    directory = Path(directory_path)

    if not directory.exists():
        return False, f"Directory does not exist: {directory}"

    if not directory.is_dir():
        return False, f"Not a directory: {directory}"

    entries = list(directory.iterdir())
    if not entries:
        return False, f"Directory is empty: {directory.name}"

    directory_extension: str | None = None
    invalid_entries: list[str] = []

    for entry in entries:
        image_extension = get_supported_image_extension(entry)
        if image_extension is None:
            invalid_entries.append(f"{entry.name} (unsupported file type)")
            continue

        if not is_supported_image_entry(entry):
            invalid_entries.append(
                f"{entry.name} (expected {'directory' if image_extension == '.ome.zarr' else 'file'})"
            )
            continue

        if directory_extension is None:
            directory_extension = image_extension
            continue

        if image_extension != directory_extension:
            invalid_entries.append(
                f"{entry.name} (does not match {directory_extension})"
            )

    if invalid_entries:
        invalid_entries_text = "\n".join(
            f"- {entry}" for entry in invalid_entries
        )
        return (
            False,
            f"{directory.name} contains {len(invalid_entries)} invalid entries:\n"
            f"{invalid_entries_text}",
        )

    return True, None


def get_common_prefix(strings: list[str]) -> str:
    if not strings:
        return ""
    prefix = os.path.commonprefix(strings)
    return prefix.rstrip("_-. ")
