from pathlib import Path

from napari.utils.notifications import show_error

from carltonlab_napari_tools.image_resolver._image_resolver import (
    resolve_spatial_data,
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

    data = resolve_spatial_data(input_path)
    if data is None:
        show_error(f"Could not open image {input_path}")
        return False

    expected_dims = ("c", "z", "y", "x")
    if tuple(data.dims) != expected_dims:
        show_error(
            f"Expected image dimensions {expected_dims}, but got {tuple(data.dims)}"
        )
        return False

    channel_count = data.sizes["c"]

    if channels:
        invalid_channels = [
            channel
            for channel in channels
            if channel < 1 or channel > channel_count
        ]
        if invalid_channels:
            show_error(
                f"Invalid channel(s): {', '.join(map(str, invalid_channels))}. "
                f"Expected 1-{channel_count}."
            )
            return False

        selected_0base_channels = [channel - 1 for channel in channels]
        data = data.isel(c=selected_0base_channels)

    raise NotImplementedError(
        "Channel extraction to ome.zarr is not yet implemented."
    )

    return True
