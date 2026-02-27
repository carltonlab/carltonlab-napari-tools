import argparse
import configparser
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from dask.diagnostics.progress import ProgressBar
from multiview_stitcher import (
    fusion,
    msi_utils,
    ngff_utils,
    param_utils,
    registration,
)
from multiview_stitcher import spatial_image_utils as si_utils


def _load_stage_translation(zarr_path: str) -> dict[str, float]:
    ini_path = Path(f"{zarr_path}.ini")
    if not ini_path.exists():
        return {"z": 0.0, "y": 0.0, "x": 0.0}

    config = configparser.ConfigParser()
    config.read(ini_path)
    section = (
        config["stage_translation"] if "stage_translation" in config else {}
    )
    return {
        "z": float(section.get("z", 0.0)),
        "y": float(section.get("y", 0.0)),
        "x": float(section.get("x", 0.0)),
    }


def _apply_stage_translation(
    msim, translation: dict[str, float], transform_key: str
):
    spatial_dims = si_utils.get_spatial_dims_from_sim(msim["scale0/image"])
    translation_vec = [translation[dim] for dim in spatial_dims]
    affine = param_utils.affine_from_translation(translation_vec)
    xaffine = param_utils.affine_to_xaffine(affine)
    msi_utils.set_affine_transform(
        msim, xaffine=xaffine, transform_key=transform_key
    )
    return msim


def _load_ome_zarr_paths(directory: Path) -> list[str]:
    paths = sorted(directory.glob("*.ome.zarr"))
    if not paths:
        raise ValueError(f"No .ome.zarr directories found in {directory}")
    return [str(path) for path in paths]


def run_stitch(
    input_dir: Path,
    output_zarr: Path,
    apply_ini_translation: bool,
    num_workers: int | None,
    n_batch: int | None,
) -> None:
    ome_zarr_paths = _load_ome_zarr_paths(input_dir)
    msims = []
    for zarr_path in ome_zarr_paths:
        msim = ngff_utils.read_msim_from_ome_zarr(zarr_path)
        if apply_ini_translation:
            translation = _load_stage_translation(zarr_path)
            msim = _apply_stage_translation(
                msim, translation=translation, transform_key="stage_metadata"
            )
        else:
            ndim = si_utils.get_ndim_from_sim(msim["scale0/image"])
            identity = param_utils.identity_transform(ndim)
            msi_utils.set_affine_transform(
                msim, xaffine=identity, transform_key="stage_metadata"
            )
        msims.append(msim)

    scale_counts = [
        len(msi_utils.get_sorted_scale_keys(msim)) for msim in msims
    ]
    min_scales = min(scale_counts) if scale_counts else 0
    desired_reg_res_level = 1
    registration_binning = {"z": 2, "y": 4, "x": 4}

    reg_kwargs = {}
    if min_scales > 1:
        reg_kwargs["reg_res_level"] = min(
            desired_reg_res_level, min_scales - 1
        )
    else:
        reg_kwargs["registration_binning"] = registration_binning

    with ProgressBar():
        registration.register(
            msims,
            reg_channel_index=0,
            transform_key="stage_metadata",
            new_transform_key="translation_registered",
            pre_registration_pruning_method=None,
            plot_summary=False,
            n_parallel_pairwise_regs=4,
            **reg_kwargs,
        )

    sims = [msi_utils.get_sim_from_msim(msim) for msim in msims]
    fused_sim = fusion.fuse(
        sims=sims,
        transform_key="translation_registered",
    )

    def process_batch_using_threads(
        func, block_ids, num_workers: int = 4
    ) -> None:
        with ThreadPoolExecutor(max_workers=num_workers) as executor:
            list(executor.map(func, block_ids))

    if num_workers is None:
        num_workers = max(1, (os.cpu_count() or 1) // 2)
    if n_batch is None:
        n_batch = max(1, num_workers)
    batch_options = {
        "batch_func": process_batch_using_threads,
        "n_batch": max(1, n_batch),
        "batch_func_kwargs": {"num_workers": num_workers},
    }

    fusion.fuse(
        sims=sims,
        transform_key="translation_registered",
        output_zarr_url=str(output_zarr),
        zarr_options={"ome_zarr": True},
        batch_options=batch_options,
    )
    print(f"Fused output written to {output_zarr}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Stitch OME-Zarr tiles in a directory."
    )
    parser.add_argument(
        "input_dir",
        help="Directory containing .ome.zarr tiles to stitch.",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Output OME-Zarr path. Defaults to <input_dir>/stitched_fused.ome.zarr",
    )
    parser.add_argument(
        "--apply-ini-translation",
        action="store_true",
        help="Apply stage translations from <tile>.ome.zarr.ini files.",
    )
    parser.add_argument(
        "--num-workers",
        type=int,
        default=None,
        help="Thread count for fusion batches (default: half of CPU cores).",
    )
    parser.add_argument(
        "--n-batch",
        type=int,
        default=None,
        help="Number of chunks per batch (default: equals num-workers).",
    )
    args = parser.parse_args()
    input_dir = Path(args.input_dir)
    output_zarr = (
        Path(args.output)
        if args.output is not None
        else input_dir / "stitched_fused.ome.zarr"
    )
    run_stitch(
        input_dir=input_dir,
        output_zarr=output_zarr,
        apply_ini_translation=args.apply_ini_translation,
        num_workers=args.num_workers,
        n_batch=args.n_batch,
    )
