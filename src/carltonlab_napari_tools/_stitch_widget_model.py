"""Compatibility imports for the relocated stitching workflow."""

from carltonlab_napari_tools.image_stitching._image_stitching import (  # noqa: F401
    get_stitched_coordinates_path,
    get_stitched_output_path,
    get_stitched_tiles_directory_path,
)

__all__ = [
    "get_stitched_coordinates_path",
    "get_stitched_output_path",
    "get_stitched_tiles_directory_path",
]
