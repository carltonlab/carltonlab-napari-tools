from typing import Any

import xarray as xr


def get_clamped_sbs_slices(
    feature: dict[str, Any],
    image_data: xr.DataArray,
) -> tuple[slice, slice, slice] | None:
    center_x = float(feature["stitched_x_coord"])
    center_y = float(feature["stitched_y_coord"])
    center_z = int(float(feature["stitched_z_coord"]))
    width = int(feature["square_width"])
    height = int(feature["square_height"])
    z_sections = int(feature["square_z_sections"])

    z_up = z_sections // 2
    z_down = (z_sections - 1) // 2

    z_start = max(0, center_z - z_down)
    z_stop = min(image_data.sizes["z"], center_z + z_up + 1)
    y_start = max(0, int(center_y - height / 2))
    y_stop = min(image_data.sizes["y"], int(center_y + height / 2))
    x_start = max(0, int(center_x - width / 2))
    x_stop = min(image_data.sizes["x"], int(center_x + width / 2))

    if z_start >= z_stop or y_start >= y_stop or x_start >= x_stop:
        return None

    return (
        slice(z_start, z_stop),
        slice(y_start, y_stop),
        slice(x_start, x_stop),
    )


def crop_sbs_data(
    image_data: xr.DataArray,
    feature: dict[str, Any],
) -> xr.DataArray | None:
    slices = get_clamped_sbs_slices(feature, image_data)
    if slices is None:
        return None

    z_slice, y_slice, x_slice = slices
    return image_data.isel(
        z=z_slice,
        y=y_slice,
        x=x_slice,
    )
