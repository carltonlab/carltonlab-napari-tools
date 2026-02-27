import json
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import numpy.typing as npt
from dask.diagnostics.progress import ProgressBar
from mrc import DVFile
from multiview_stitcher import fusion, msi_utils, registration
from multiview_stitcher import spatial_image_utils as si_utils

image_paths: tuple[str, ...] = (
    "c115_2025_6_10_strain_n2_l4440_stain_dapi_rad51_htp3_syp1_slide1_gonad2_1.deconzs",
    "c115_2025_6_10_strain_n2_l4440_stain_dapi_rad51_htp3_syp1_slide1_gonad2_2.deconzs",
    "c115_2025_6_10_strain_n2_l4440_stain_dapi_rad51_htp3_syp1_slide1_gonad2_3.deconzs",
    "c115_2025_6_10_strain_n2_l4440_stain_dapi_rad51_htp3_syp1_slide1_gonad2_4.deconzs",
    "c115_2025_6_10_strain_n2_l4440_stain_dapi_rad51_htp3_syp1_slide1_gonad2_5.deconzs",
    "c115_2025_6_10_strain_n2_l4440_stain_dapi_rad51_htp3_syp1_slide1_gonad2_6.deconzs",
)


def _fix_ome_zarr_contrast_limits(zarr_url: str) -> None:
    zattrs_path = Path(zarr_url) / ".zattrs"
    if not zattrs_path.exists():
        print(f"No .zattrs found at {zattrs_path}")
        return

    with zattrs_path.open("r", encoding="utf-8") as handle:
        zattrs = json.load(handle)

    omero = zattrs.get("omero")
    channels = omero.get("channels") if isinstance(omero, dict) else None
    if not isinstance(channels, list):
        return

    changed = False
    for channel in channels:
        if not isinstance(channel, dict):
            continue
        window = channel.get("window")
        if not isinstance(window, dict):
            continue
        start = window.get("start")
        end = window.get("end")
        if start is not None and end is not None and start >= end:
            window["start"] = float(start)
            window["end"] = float(start) + 1.0
            changed = True
        min_val = window.get("min")
        max_val = window.get("max")
        if min_val is not None and max_val is not None and min_val >= max_val:
            window["min"] = float(min_val)
            window["max"] = float(min_val) + 1.0
            changed = True

    if changed:
        with zattrs_path.open("w", encoding="utf-8") as handle:
            json.dump(zattrs, handle, indent=2)
            handle.write("\n")


def run_stitch() -> None:
    # 1) Prepare data for stitching
    tile_arrays: list[npt.NDArray[np.uint16]] = []
    tile_translations: list[dict[str, float]] = []

    for image_index, image_path in enumerate(image_paths):
        with DVFile(image_path) as dvf:
            header = dvf.hdr
            # Flip X/Y/Z translation to match image axis orientation.
            translation = {
                "z": -header.z0,
                "y": -header.y0,
                "x": -header.x0,
            }
            # Force a real in-memory copy; dvf.data is a memmap tied to the file.
            data = np.array(dvf.data, dtype=np.uint16, copy=True)
        print(
            f"Tile {image_index} raw shape: {data.shape}, dtype: {data.dtype}, "
            f"translation: {translation}"
        )
        try:
            sample = np.asarray(data[..., :4, :16, :16]).copy()
            print(
                f"Tile {image_index} sample stats: min={sample.min()}, "
                f"max={sample.max()}, mean={float(sample.mean()):.3f}"
            )
        except Exception as exc:
            print(f"Tile {image_index} sample stats failed: {exc}")
        tile_arrays.append(data)
        tile_translations.append(translation)

    spacing = {"z": 0.2, "y": 0.064, "x": 0.064}
    channels = ["DAPI", "RAD51", "HTP3", "SYP1"]

    msims = []
    for tile_index, (tile_array, tile_translation) in enumerate(
        zip(tile_arrays, tile_translations, strict=True)
    ):
        # Accept 4D (c, z, y, x) or 5D (c, t, z, y, x) with a singleton time.
        dims = ["c", "z", "y", "x"]
        if tile_array.ndim == 5:
            if tile_array.shape[1] == 1:
                tile_array = np.squeeze(tile_array, axis=1)
            else:
                raise ValueError(
                    f"Tile {tile_index} has time axis size {tile_array.shape[1]}, "
                    "expected 1 for (c, t, z, y, x)."
                )
        if tile_array.ndim != 4:
            raise ValueError(
                f"Tile {tile_index} should be 4D after squeeze. Got shape {tile_array.shape}."
            )
        if tile_array.shape[0] != len(channels):
            raise ValueError(
                f"Tile {tile_index} channel axis has size {tile_array.shape[0]}, "
                f"expected {len(channels)}."
            )

        sim = si_utils.get_sim_from_array(
            tile_array.astype(np.float32, copy=False),
            dims=dims,
            scale=spacing,
            translation=tile_translation,
            transform_key="stage_metadata",
            c_coords=channels,
        )
        print(
            f"Tile {tile_index} sim dims: {sim.dims}, sizes: {dict(sim.sizes)}"
        )
        msims.append(msi_utils.get_msim_from_sim(sim, scale_factors=[]))

    # 2) Register the tiles
    with ProgressBar():
        registration.register(
            msims,
            reg_channel="DAPI",
            transform_key="stage_metadata",
            new_transform_key="translation_registered",
            pre_registration_pruning_method=None,
            plot_summary=False,
        )

    # 3) Stitch / fuse the tiles
    sims = [msi_utils.get_sim_from_msim(msim) for msim in msims]
    if sims:
        first_sim = sims[0]
        print(
            "First msim->sim dims/sizes before fusion: "
            f"{first_sim.dims}, {dict(first_sim.sizes)}"
        )
        if "c" in first_sim.coords:
            print(f"First sim c coords: {list(first_sim.coords['c'].values)}")
    fused_sim = fusion.fuse(
        sims=sims,
        transform_key="translation_registered",
    )

    # Optional: write fused output to OME-Zarr (use threads for parallel chunk fusion)
    output_zarr = "stitched_fused.ome.zarr"

    def process_batch_using_threads(
        func, block_ids, num_workers: int = 4
    ) -> None:
        with ThreadPoolExecutor(max_workers=num_workers) as executor:
            list(executor.map(func, block_ids))

    num_workers = max(1, (os.cpu_count() or 1) // 2)
    batch_options = {
        "batch_func": process_batch_using_threads,
        "n_batch": max(1, num_workers),
        "batch_func_kwargs": {"num_workers": num_workers},
    }
    print(f"Using threaded fusion with num_workers={num_workers}.")

    fusion.fuse(
        sims=sims,
        transform_key="translation_registered",
        output_zarr_url=output_zarr,
        zarr_options={"ome_zarr": True},
        batch_options=batch_options,
    )
    try:
        import zarr

        zarr_path = os.path.join(output_zarr, "0")
        z = zarr.open(zarr_path, mode="r")
        sample = z[0, 0, 0, :8, :8]
        print(
            f"Zarr sample stats at {zarr_path}: "
            f"min={sample.min()}, max={sample.max()}, mean={float(sample.mean()):.3f}"
        )
        # Probe center region to see if any nonzero data exists.
        t, c, zdim, ydim, xdim = z.shape
        zc, yc, xc = zdim // 2, ydim // 2, xdim // 2
        center = z[0, 0, zc : zc + 1, yc - 4 : yc + 4, xc - 4 : xc + 4]
        print(
            "Zarr center stats: "
            f"min={center.min()}, max={center.max()}, mean={float(center.mean()):.3f}"
        )
    except Exception as exc:
        print(f"Zarr sample read failed: {exc}")
    _fix_ome_zarr_contrast_limits(output_zarr)
    print(f"Fused output written to {output_zarr}")


if __name__ == "__main__":
    run_stitch()
