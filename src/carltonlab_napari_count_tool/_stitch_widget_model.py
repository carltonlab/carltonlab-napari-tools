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
from napari.utils.notifications import show_error


def _load_stage_translation(zarr_path: str) -> dict[str, float]:
    ini_path = Path(f"{zarr_path}.ini")
    if not ini_path.exists():
        return {"z": 0.0, "y": 0.0, "x": 0.0}

    import configparser

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


def _strip_ome_zarr(name: str) -> str:
    if name.endswith(".ome.zarr"):
        return name[: -len(".ome.zarr")]
    return Path(name).stem


def _common_prefix(strings: list[str]) -> str:
    if not strings:
        return ""
    prefix = os.path.commonprefix(strings)
    return prefix.rstrip("_-. ")


def get_stitched_output_path(input_dir: str) -> str:
    ome_zarr_paths = _load_ome_zarr_paths(Path(input_dir))
    names = [_strip_ome_zarr(Path(path).name) for path in ome_zarr_paths]
    common = _common_prefix(names)
    if not common:
        common = Path(input_dir).name or "stitched"
    output_name = f"{common}_stitched.ome.zarr"
    return str(Path(input_dir) / output_name)


def stitch_directories(
    input_dirs: list[str],
    apply_ini_translation: bool = False,
    num_workers: int | None = None,
    n_batch: int | None = None,
) -> bool:
    if not input_dirs:
        return False
    all_ok = True
    for input_dir in input_dirs:
        try:
            run_stitch(
                input_dir=Path(input_dir),
                output_zarr=Path(get_stitched_output_path(input_dir)),
                apply_ini_translation=apply_ini_translation,
                num_workers=num_workers,
                n_batch=n_batch,
            )
        except Exception as exc:
            show_error(f"Failed stitching {input_dir}: {exc}")
            all_ok = False
    return all_ok


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
    fusion.fuse(
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
