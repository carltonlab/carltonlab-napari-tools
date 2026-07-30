from __future__ import annotations

import os
from pathlib import Path

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
