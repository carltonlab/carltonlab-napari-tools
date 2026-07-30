import csv
import os
import shutil
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
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

from carltonlab_napari_tools._shared_variables import STITCHED_IMAGE_SUFFIX
from carltonlab_napari_tools._utils import get_common_prefix


def _load_stage_translation(zarr_path: str) -> dict[str, float]:
    ini_path = Path(f"{zarr_path}.ini")
    if not ini_path.exists():
        return {"z": 0.0, "y": 0.0, "x": 0.0}

    import configparser

    config = configparser.ConfigParser()
    config.read(ini_path)
    section = config.get("stage_translation", {})
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


def get_stitched_coordinates_path(output_zarr: str | Path) -> str:
    output_path = Path(output_zarr)
    base_name = _strip_ome_zarr(output_path.name)
    return str(output_path.parent / f"{base_name}_tile_positions.csv")


def get_stitched_tiles_directory_path(output_zarr: str | Path) -> str:
    output_path = Path(output_zarr)
    base_name = _strip_ome_zarr(output_path.name)
    return str(output_path.parent / f"{base_name}_tiles")


def _get_affine_matrix(xaffine) -> list[list[float]]:
    selection = {
        dim: xaffine.coords[dim][0].item()
        for dim in xaffine.dims
        if dim not in {"x_in", "x_out"}
    }
    affine = xaffine.sel(selection) if selection else xaffine
    return affine.astype(float).values.tolist()


def _get_output_stack_origin_and_spacing(
    bbox_mins_phys: list[np.ndarray],
    sims,
) -> tuple[list[str], np.ndarray, np.ndarray]:
    spatial_dims = si_utils.get_spatial_dims_from_sim(sims[0])
    output_origin = np.min(np.stack(bbox_mins_phys, axis=0), axis=0)
    output_spacing = np.asarray(
        [
            si_utils.get_spacing_from_sim(sims[0], asarray=False)[dim]
            for dim in spatial_dims
        ],
        dtype=float,
    )
    return spatial_dims, output_origin, output_spacing


def _get_tile_bounding_box(
    sim,
    affine_matrix: np.ndarray,
) -> tuple[list[str], np.ndarray, np.ndarray]:
    spatial_dims = si_utils.get_spatial_dims_from_sim(sim)
    stack_props = si_utils.get_stack_properties_from_sim(sim, asarray=False)
    shape = np.asarray(
        [stack_props["shape"][dim] for dim in spatial_dims], dtype=float
    )
    spacing = np.asarray(
        [stack_props["spacing"][dim] for dim in spatial_dims], dtype=float
    )
    origin = np.asarray(
        [stack_props["origin"][dim] for dim in spatial_dims], dtype=float
    )
    corners = np.asarray(
        list(np.ndindex((2,) * len(spatial_dims))), dtype=float
    )
    vertices = corners * shape * spacing + origin
    transformed_vertices = (
        affine_matrix[: len(spatial_dims), : len(spatial_dims)] @ vertices.T
    ).T + affine_matrix[: len(spatial_dims), len(spatial_dims)]
    return (
        spatial_dims,
        transformed_vertices.min(axis=0),
        transformed_vertices.max(axis=0),
    )


def _get_tile_bbox_pixels(
    bbox_min_phys: np.ndarray,
    bbox_max_phys: np.ndarray,
    output_origin: np.ndarray,
    output_spacing: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    bbox_min_px = (bbox_min_phys - output_origin) / output_spacing
    bbox_max_px = (bbox_max_phys - output_origin) / output_spacing
    return bbox_min_px, bbox_max_px


def _normalize_bbox_pixels(
    tile_infos: list[tuple],
) -> tuple[list[tuple], np.ndarray]:
    if not tile_infos:
        return tile_infos, np.array([], dtype=float)

    global_min = np.min(
        np.stack([info[6] for info in tile_infos], axis=0),
        axis=0,
    )
    normalized_infos = []
    for info in tile_infos:
        bbox_min_px = info[6] - global_min
        bbox_max_px = info[7] - global_min
        normalized_infos.append((*info[:6], bbox_min_px, bbox_max_px))
    return normalized_infos, global_min


def _relocate_tiles(ome_zarr_paths: list[str], output_zarr: Path) -> list[str]:
    tiles_dir = Path(get_stitched_tiles_directory_path(output_zarr))
    tiles_dir.mkdir(exist_ok=True)

    relocated_paths: list[str] = []
    for tile_path_str in ome_zarr_paths:
        tile_path = Path(tile_path_str)
        destination_path = tiles_dir / tile_path.name
        if destination_path.exists():
            raise FileExistsError(
                f"Tile destination already exists: {destination_path}"
            )
        shutil.move(str(tile_path), str(destination_path))

        ini_path = Path(f"{tile_path}.ini")
        if ini_path.exists():
            ini_destination_path = tiles_dir / ini_path.name
            if ini_destination_path.exists():
                raise FileExistsError(
                    f"Tile ini destination already exists: {ini_destination_path}"
                )
            shutil.move(str(ini_path), str(ini_destination_path))

        relocated_paths.append(str(destination_path))

    return relocated_paths


def _save_registered_tile_positions(
    msims,
    ome_zarr_paths: list[str],
    output_zarr: Path,
    transform_key: str,
) -> Path:
    rows: list[dict[str, object]] = []
    sims = [msi_utils.get_sim_from_msim(msim) for msim in msims]
    tile_infos = []
    bbox_mins_phys: list[np.ndarray] = []
    for tile_path, sim in zip(ome_zarr_paths, sims, strict=True):
        xaffine = si_utils.get_affine_from_sim(
            sim, transform_key=transform_key
        )
        spatial_dims = [
            str(dim)
            for dim in xaffine.coords["x_in"].values
            if str(dim) != "1"
        ]
        affine_matrix = np.asarray(_get_affine_matrix(xaffine), dtype=float)
        translation = param_utils.translation_from_affine(affine_matrix)
        _, bbox_min_phys, bbox_max_phys = _get_tile_bounding_box(
            sim, affine_matrix
        )
        bbox_mins_phys.append(bbox_min_phys)
        tile_infos.append(
            (
                tile_path,
                spatial_dims,
                affine_matrix,
                translation,
                bbox_min_phys,
                bbox_max_phys,
            )
        )

    _, output_origin, output_spacing = _get_output_stack_origin_and_spacing(
        bbox_mins_phys=bbox_mins_phys,
        sims=sims,
    )

    tile_infos_with_pixels = []
    for (
        tile_path,
        spatial_dims,
        affine_matrix,
        translation,
        bbox_min_phys,
        bbox_max_phys,
    ) in tile_infos:
        bbox_min_px, bbox_max_px = _get_tile_bbox_pixels(
            bbox_min_phys=bbox_min_phys,
            bbox_max_phys=bbox_max_phys,
            output_origin=output_origin,
            output_spacing=output_spacing,
        )
        tile_infos_with_pixels.append(
            (
                tile_path,
                spatial_dims,
                affine_matrix,
                translation,
                bbox_min_phys,
                bbox_max_phys,
                bbox_min_px,
                bbox_max_px,
            )
        )

    tile_infos_with_pixels, _ = _normalize_bbox_pixels(tile_infos_with_pixels)

    for (
        tile_path,
        spatial_dims,
        affine_matrix,
        translation,
        bbox_min_phys,
        bbox_max_phys,
        bbox_min_px,
        bbox_max_px,
    ) in tile_infos_with_pixels:
        row: dict[str, object] = {
            "tile_path": tile_path,
            "tile_name": Path(tile_path).name,
            "transform_key": transform_key,
        }
        row.update(
            {
                f"{dim}_translation": value
                for dim, value in zip(
                    spatial_dims, translation.tolist(), strict=True
                )
            }
        )
        row.update(
            {
                f"{dim}_min_phys": value
                for dim, value in zip(
                    spatial_dims, bbox_min_phys.tolist(), strict=True
                )
            }
        )
        row.update(
            {
                f"{dim}_max_phys": value
                for dim, value in zip(
                    spatial_dims, bbox_max_phys.tolist(), strict=True
                )
            }
        )
        row.update(
            {
                f"{dim}_min_px": value
                for dim, value in zip(
                    spatial_dims, bbox_min_px.tolist(), strict=True
                )
            }
        )
        row.update(
            {
                f"{dim}_max_px": value
                for dim, value in zip(
                    spatial_dims, bbox_max_px.tolist(), strict=True
                )
            }
        )
        row.update(
            {
                f"{dim}_min_px_index": int(np.floor(value))
                for dim, value in zip(
                    spatial_dims, bbox_min_px.tolist(), strict=True
                )
            }
        )
        row.update(
            {
                f"{dim}_max_px_index_exclusive": int(np.ceil(value))
                for dim, value in zip(
                    spatial_dims, bbox_max_px.tolist(), strict=True
                )
            }
        )
        for row_index, affine_row in enumerate(affine_matrix.tolist()):
            for col_index, value in enumerate(affine_row):
                row[f"affine_{row_index}_{col_index}"] = value
        rows.append(row)

    coordinates_path = Path(get_stitched_coordinates_path(output_zarr))
    fieldnames = list(rows[0].keys()) if rows else ["tile_path", "tile_name"]
    with coordinates_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    return coordinates_path


def convert_to_ome_zarr(image_list: list[Path]) -> list[Path] | None:
    return []


def stitch_ome_zarr_images(
    image_list: list[Path],
    output_dir: Path,
    apply_ini_translation: bool = False,
    num_workers: int | None = None,
    n_batch: int | None = None,
    use_gpu: bool = False,
) -> bool:
    if not image_list:
        show_error("No images to stitch, list is empty.")
    if any(not str(p).endswith(".ome.zarr") for p in image_list):
        message: str = " \nThe stitching files are not in .ome.zarr format:"
        for image in image_list:
            message = message + "\n" + str(image)
        show_error(message)
        return False

    output_dir.mkdir(parents=True, exist_ok=True)

    image_names: list[str] = [_strip_ome_zarr(p.name) for p in image_list]
    common_prefix = get_common_prefix(image_names)
    stitched_name = common_prefix + STITCHED_IMAGE_SUFFIX
    print(stitched_name)

    return True


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
        except (OSError, ValueError) as exc:
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
    relocated_tile_paths = _relocate_tiles(ome_zarr_paths, output_zarr)
    _save_registered_tile_positions(
        msims=msims,
        ome_zarr_paths=relocated_tile_paths,
        output_zarr=output_zarr,
        transform_key="translation_registered",
    )
