from dataclasses import dataclass
from typing import Any

import xarray as xr


@dataclass(frozen=True)
class SBSCropBounds:
    z_start: int
    z_stop: int
    y_start: int
    y_stop: int
    x_start: int
    x_stop: int

    @property
    def slices(self) -> tuple[slice, slice, slice]:
        return (
            slice(self.z_start, self.z_stop),
            slice(self.y_start, self.y_stop),
            slice(self.x_start, self.x_stop),
        )

    def stitched_to_local(
        self,
        coordinates: tuple[float, float, float],
    ) -> tuple[float, float, float]:
        z, y, x = coordinates
        return (
            z - self.z_start,
            y - self.y_start,
            x - self.x_start,
        )

    def local_to_stitched(
        self,
        coordinates: tuple[float, float, float],
    ) -> tuple[float, float, float]:
        z, y, x = coordinates
        return (
            z + self.z_start,
            y + self.y_start,
            x + self.x_start,
        )


def get_sbs_crop_bounds(
    feature: dict[str, Any],
    image_data: xr.DataArray,
) -> SBSCropBounds | None:
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

    return SBSCropBounds(
        z_start=z_start,
        z_stop=z_stop,
        y_start=y_start,
        y_stop=y_stop,
        x_start=x_start,
        x_stop=x_stop,
    )


def get_clamped_sbs_slices(
    feature: dict[str, Any],
    image_data: xr.DataArray,
) -> tuple[slice, slice, slice] | None:
    bounds = get_sbs_crop_bounds(feature, image_data)
    return None if bounds is None else bounds.slices


def crop_sbs_data(
    image_data: xr.DataArray,
    feature: dict[str, Any],
    bounds: SBSCropBounds | None = None,
) -> xr.DataArray | None:
    crop_bounds = bounds or get_sbs_crop_bounds(feature, image_data)
    if crop_bounds is None:
        return None

    z_slice, y_slice, x_slice = crop_bounds.slices
    return image_data.isel(
        z=z_slice,
        y=y_slice,
        x=x_slice,
    )
