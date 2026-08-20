from pathlib import Path

from napari.utils.notifications import show_error

from carltonlab_napari_tools.image_resolver._image_resolver import (
    _carltonlab_normalize_image_data,
    resolve_image,
)


def extract_channels_to_ome_zarr(
    input_path: Path,
    output_path: Path,
    channels: list[int],
) -> bool:
    if not input_path.exists():
        show_error(f"File {input_path} does not exist.")
        return False
    if output_path.exists():
        show_error(f"Output {output_path} already exists.")
        return False

    output_path.parent.mkdir(parents=True, exist_ok=True)

    image = resolve_image(input_path)
    if image is None:
        show_error(f"Could not open image {input_path}")
        return False

    data = _carltonlab_normalize_image_data(image.xarray_data)

    expected_dims = ("c", "z", "y", "x")
    if tuple(data.dims) != expected_dims:
        show_error(
            f"Expected image dimensions {expected_dims}, but got {tuple(data.dims)}"
        )
        return False

    raise NotImplementedError(
        "Channel extraction to ome.zarr is not yet implemented."
    )

    return True
