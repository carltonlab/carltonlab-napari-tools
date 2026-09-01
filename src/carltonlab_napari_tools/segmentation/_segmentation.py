from __future__ import annotations

import ctypes
import json
import os
import signal
import subprocess
import sys
from pathlib import Path

import numpy as np
from multiview_stitcher import ngff_utils
from multiview_stitcher import spatial_image_utils as si_utils
from scipy import ndimage

MODELS_DIR = Path(__file__).resolve().parent / "models"


def _strip_ome_zarr_suffix(path: str | Path) -> str:
    image_path = Path(path)
    if image_path.name.endswith(".ome.zarr"):
        return image_path.name[: -len(".ome.zarr")]
    return image_path.stem


def _resolve_model_path(model_name: str) -> Path:
    model_path = MODELS_DIR / model_name
    if not model_path.exists():
        raise FileNotFoundError(f"Segmentation model not found: {model_path}")
    if not model_path.is_file():
        raise ValueError(f"Segmentation model is not a file: {model_path}")
    return model_path


def _resolve_output_path(
    image_path: str | Path,
    model_name: str,
    output_dir: str | Path,
) -> Path:
    base_name = _strip_ome_zarr_suffix(image_path)
    return Path(output_dir) / f"{base_name}_{model_name}_masks.npy"


def load_segmentation_npy(segmentation_path: str | Path) -> np.ndarray:
    segmentation_path_obj = Path(segmentation_path)
    if not segmentation_path_obj.exists():
        raise FileNotFoundError(
            f"Segmentation file not found: {segmentation_path_obj}"
        )
    if segmentation_path_obj.suffix != ".npy":
        raise ValueError(
            "Segmentation cleaning expects a .npy file. "
            f"Got {segmentation_path_obj.name}."
        )
    return np.asarray(np.load(segmentation_path_obj))


def get_cleaned_segmentation_output_path(
    segmentation_path: str | Path,
) -> Path:
    segmentation_path_obj = Path(segmentation_path)
    if segmentation_path_obj.suffix != ".npy":
        raise ValueError(
            "Segmentation cleaning expects a .npy file. "
            f"Got {segmentation_path_obj.name}."
        )
    return segmentation_path_obj.with_name(
        f"{segmentation_path_obj.stem}_cleaned.npy"
    )


def _prepare_3d_image_for_cellpose(sim) -> tuple[np.ndarray, dict[str, float]]:
    return _prepare_3d_image_channel_zyx(sim, channel_index=0)


def _prepare_3d_image_channel_zyx(
    data, channel_index: int
) -> tuple[np.ndarray, dict[str, float]]:
    source_sim = data
    dims = [str(dim).lower() for dim in data.dims]
    print(f"Segmentation source dims: {tuple(data.dims)}")
    print(f"Segmentation source sizes: {dict(data.sizes)}")

    if "t" in dims:
        t_dim = data.dims[dims.index("t")]
        if data.sizes[t_dim] != 1:
            raise ValueError(
                f"Expected a singleton time axis for segmentation, got {data.sizes[t_dim]}"
            )
        data = data.isel({t_dim: 0})
        dims = [str(dim).lower() for dim in data.dims]
        print(
            "Segmentation dropped singleton time axis; "
            f"new dims: {tuple(data.dims)}"
        )

    if "c" in dims:
        c_dim = data.dims[dims.index("c")]
        if channel_index < 0 or channel_index >= data.sizes[c_dim]:
            raise ValueError(
                f"Channel index {channel_index} is out of bounds for axis {c_dim}"
            )
        print(
            "Segmentation input contains channels; using channel "
            f"{channel_index} from axis {c_dim}."
        )
        data = data.isel({c_dim: channel_index})
        dims = [str(dim).lower() for dim in data.dims]
        print(f"Segmentation selected channel; new dims: {tuple(data.dims)}")

    required_dims = ["z", "y", "x"]
    missing_dims = [dim for dim in required_dims if dim not in dims]
    if missing_dims:
        raise ValueError(
            f"3D segmentation requires z/y/x dims, missing {missing_dims}. "
            f"Got dims {dims}."
        )

    data = data.transpose(
        *[data.dims[dims.index(dim)] for dim in required_dims]
    )
    print(f"Segmentation transposed dims: {tuple(data.dims)}")
    image_zyx = np.asarray(data.data)
    stack_props = si_utils.get_stack_properties_from_sim(
        source_sim,
        transform_key="stage_metadata",
        asarray=False,
    )
    spacing = {
        dim: float(stack_props["spacing"][dim]) for dim in required_dims
    }
    print(f"Segmentation extracted spacing: {spacing}")
    return image_zyx, spacing


def _run_cellpose_3d(
    image_zyx: np.ndarray,
    model_path: Path,
    anisotropy: float | None,
) -> np.ndarray:
    import torch
    from cellpose import models

    use_gpu = torch.cuda.is_available()
    print(f"Loading Cellpose model: {model_path}")
    print(f"Cellpose GPU available: {use_gpu}")
    print(f"Cellpose anisotropy: {anisotropy}")

    model = models.CellposeModel(
        gpu=use_gpu,
        pretrained_model=str(model_path),
    )
    masks, flows, styles = model.eval(
        image_zyx,
        channels=[0, 0],
        channel_axis=None,
        z_axis=0,
        normalize={"normalize": True, "norm3D": True},
        do_3D=True,
        anisotropy=anisotropy,
    )
    del flows
    del styles
    return np.asarray(masks, dtype=np.uint32)


def remove_edge_objects(labels_zyx: np.ndarray) -> np.ndarray:
    labels = np.asarray(labels_zyx)
    if labels.ndim != 3:
        raise ValueError(
            f"Expected a 3D label image, got shape {labels.shape}"
        )

    z_max = labels.shape[0] - 1
    y_max = labels.shape[1] - 1
    x_max = labels.shape[2] - 1
    edge_labels = np.unique(
        np.concatenate(
            [
                labels[0:2, :, :].ravel(),
                labels[z_max - 1 : z_max + 1, :, :].ravel(),
                labels[:, 0:2, :].ravel(),
                labels[:, y_max - 1 : y_max + 1, :].ravel(),
                labels[:, :, 0:2].ravel(),
                labels[:, :, x_max - 1 : x_max + 1].ravel(),
            ]
        )
    )
    edge_labels = edge_labels[edge_labels > 0]
    if len(edge_labels) == 0:
        return labels.astype(np.uint32, copy=True)

    filtered = labels.copy()
    filtered[np.isin(filtered, edge_labels)] = 0
    return np.asarray(filtered, dtype=np.uint32)


def filter_objects_by_volume_cutoff(
    labels_zyx: np.ndarray,
    min_fraction_of_mean: float = 0.15,
) -> np.ndarray:
    if min_fraction_of_mean < 0:
        raise ValueError(
            f"min_fraction_of_mean must be >= 0, got {min_fraction_of_mean}"
        )

    labels = np.asarray(labels_zyx)
    if labels.ndim != 3:
        raise ValueError(
            f"Expected a 3D label image, got shape {labels.shape}"
        )

    object_ids = np.unique(labels)
    object_ids = object_ids[object_ids > 0]
    if len(object_ids) == 0:
        return labels.astype(np.uint32, copy=True)

    volumes = np.bincount(labels.ravel())[object_ids]
    mean_volume = float(volumes.mean())
    cutoff = mean_volume * float(min_fraction_of_mean)
    keep_ids = object_ids[volumes > cutoff]

    filtered = labels.copy()
    filtered[~np.isin(filtered, keep_ids)] = 0
    return np.asarray(filtered, dtype=np.uint32)


def filter_fragmented_objects(
    labels_zyx: np.ndarray,
    min_largest_component_fraction: float = 0.98,
) -> np.ndarray:
    if not 0 <= min_largest_component_fraction <= 1:
        raise ValueError(
            "min_largest_component_fraction must be between 0 and 1, "
            f"got {min_largest_component_fraction}"
        )

    labels = np.asarray(labels_zyx)
    if labels.ndim != 3:
        raise ValueError(
            f"Expected a 3D label image, got shape {labels.shape}"
        )

    object_ids = np.unique(labels)
    object_ids = object_ids[object_ids > 0]
    if len(object_ids) == 0:
        return labels.astype(np.uint32, copy=True)

    keep_ids: list[int] = []
    for object_id in object_ids:
        object_mask = labels == object_id
        total_volume = int(object_mask.sum())
        if total_volume == 0:
            continue

        connected_components, num_components = ndimage.label(object_mask)
        if num_components <= 1:
            keep_ids.append(int(object_id))
            continue

        component_volumes = np.bincount(connected_components.ravel())[1:]
        if len(component_volumes) == 0:
            continue
        largest_component_fraction = float(component_volumes.max()) / float(
            total_volume
        )
        if largest_component_fraction >= min_largest_component_fraction:
            keep_ids.append(int(object_id))

    filtered = labels.copy()
    filtered[~np.isin(filtered, keep_ids)] = 0
    return np.asarray(filtered, dtype=np.uint32)


def clean_segmentation_file(
    segmentation_path: str | Path,
    min_fraction_of_mean: float = 0.15,
) -> Path:
    labels_zyx = load_segmentation_npy(segmentation_path)
    volume_filtered = filter_objects_by_volume_cutoff(
        labels_zyx,
        min_fraction_of_mean=min_fraction_of_mean,
    )
    fragmentation_filtered = filter_fragmented_objects(volume_filtered)
    cleaned_labels = remove_edge_objects(fragmentation_filtered)
    output_path = get_cleaned_segmentation_output_path(segmentation_path)
    np.save(output_path, np.asarray(cleaned_labels, dtype=np.uint32))
    return output_path


def _resolve_spotiflow_model_dir(model_name: str) -> Path:
    model_path = MODELS_DIR / model_name
    if not model_path.exists():
        raise FileNotFoundError(
            f"Spotiflow model directory not found: {model_path}"
        )
    if not model_path.is_dir():
        raise ValueError(
            f"Spotiflow model path is not a directory: {model_path}"
        )
    return model_path


def run_spotiflow_spot_detection(
    image_zyx: np.ndarray,
    model_name: str = "smfish_3d",
    use_gpu: bool = True,
) -> np.ndarray:
    from spotiflow.model import Spotiflow

    device = "auto" if use_gpu else "cpu"
    print(f"Spotiflow device request: {device}")
    model_dir = MODELS_DIR / model_name
    if model_dir.exists():
        print(f"Loading Spotiflow model from folder: {model_dir}")
        model = Spotiflow.from_folder(
            str(model_dir),
            map_location=device,
        )
    else:
        print(f"Loading Spotiflow pretrained model: {model_name}")
        model = Spotiflow.from_pretrained(
            model_name,
            map_location=device,
        )
    spots, _details = model.predict(
        np.asarray(image_zyx),
        normalizer=None,
        verbose=False,
        device=device,
    )
    return np.asarray(spots)


def run_spotiflow_subprocess(
    image_path: str | Path,
    output_csv_path: str | Path,
    model_name: str = "smfish_3d",
    use_gpu: bool = True,
) -> bool:
    payload = {
        "image_path": str(image_path),
        "output_csv_path": str(output_csv_path),
        "model_name": model_name,
        "use_gpu": bool(use_gpu),
    }
    env = os.environ.copy()
    env.setdefault("MPLCONFIGDIR", "/tmp/matplotlib")
    command = [
        sys.executable,
        "-m",
        "carltonlab_napari_tools.segmentation._segmentation",
        json.dumps(payload),
    ]
    print(f"Starting Spotiflow subprocess: {' '.join(command[:3])} ...")
    popen_kwargs = {
        "env": env,
        "text": True,
    }
    if sys.platform.startswith("linux"):
        popen_kwargs["preexec_fn"] = _set_child_parent_death_signal

    process = subprocess.Popen(
        command,
        **popen_kwargs,
    )
    try:
        returncode = process.wait()
    except BaseException:
        process.terminate()
        process.wait()
        raise

    if returncode != 0:
        raise RuntimeError(
            f"Spotiflow subprocess failed with exit code {returncode}"
        )
    return True


def load_ome_zarr_image_zyx(
    image_path: str | Path,
    channel_index: int = 0,
) -> tuple[np.ndarray, dict[str, float]]:
    image_path_obj = Path(image_path)
    if not image_path_obj.exists():
        raise FileNotFoundError(
            f"Segmentation image not found: {image_path_obj}"
        )
    if not image_path_obj.name.endswith(".ome.zarr"):
        raise ValueError(
            "The current image loading implementation expects an .ome.zarr image. "
            f"Got {image_path_obj.name}."
        )

    print(f"Reading image for ZYX conversion: {image_path_obj}")
    source_sim = ngff_utils.read_sim_from_ome_zarr(
        str(image_path_obj),
        transform_key="stage_metadata",
    )
    return _prepare_3d_image_channel_zyx(
        source_sim, channel_index=channel_index
    )


def _set_child_parent_death_signal() -> None:
    if not sys.platform.startswith("linux"):
        return

    libc = ctypes.CDLL("libc.so.6")
    pr_set_pdeathsig = 1
    libc.prctl(pr_set_pdeathsig, signal.SIGTERM)


def run_segmentation_subprocess(
    image_path: str | Path,
    model_name: str,
    output_dir: str | Path,
) -> bool:
    payload = {
        "image_path": str(image_path),
        "model_name": model_name,
        "output_dir": str(output_dir),
    }
    env = os.environ.copy()
    env.setdefault("MPLCONFIGDIR", "/tmp/matplotlib")
    command = [
        sys.executable,
        "-m",
        "carltonlab_napari_count_tool.segmentation._segmentation",
        json.dumps(payload),
    ]
    print(f"Starting segmentation subprocess: {' '.join(command[:3])} ...")
    popen_kwargs = {
        "env": env,
        "text": True,
    }
    if sys.platform.startswith("linux"):
        popen_kwargs["preexec_fn"] = _set_child_parent_death_signal

    process = subprocess.Popen(
        command,
        **popen_kwargs,
    )
    try:
        returncode = process.wait()
    except BaseException:
        process.terminate()
        process.wait()
        raise

    if returncode != 0:
        raise RuntimeError(
            f"Segmentation subprocess failed with exit code {returncode}"
        )
    return True


def run_segmentation(
    image_path: str | Path,
    model_name: str,
    output_dir: str | Path,
) -> bool:
    image_path_obj = Path(image_path)
    if not image_path_obj.exists():
        raise FileNotFoundError(
            f"Segmentation image not found: {image_path_obj}"
        )
    if not image_path_obj.name.endswith(".ome.zarr"):
        raise ValueError(
            "The current segmentation implementation expects an .ome.zarr image. "
            f"Got {image_path_obj.name}."
        )

    model_path = _resolve_model_path(model_name)
    output_dir_path = Path(output_dir)
    output_dir_path.mkdir(parents=True, exist_ok=True)
    output_path = _resolve_output_path(
        image_path=image_path_obj,
        model_name=model_name,
        output_dir=output_dir_path,
    )
    if output_path.exists():
        print(f"Segmentation output already exists: {output_path}")
        return True

    image_zyx, spacing = load_ome_zarr_image_zyx(
        image_path=image_path_obj,
    )
    anisotropy = None
    if spacing["y"] != 0:
        anisotropy = spacing["z"] / spacing["y"]

    print(f"Segmentation image shape (ZYX): {image_zyx.shape}")
    print(f"Segmentation output path: {output_path}")
    print(f"Segmentation spacing: {spacing}")

    masks_zyx = _run_cellpose_3d(
        image_zyx=image_zyx,
        model_path=model_path,
        anisotropy=anisotropy,
    )
    print(f"Segmentation mask shape (ZYX): {masks_zyx.shape}")
    print(f"Segmentation final anisotropy: {anisotropy}")
    np.save(output_path, masks_zyx)
    return True


def _main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("Expected one JSON payload argument")
    payload = json.loads(sys.argv[1])
    if "output_dir" in payload:
        run_segmentation(
            image_path=payload["image_path"],
            model_name=payload["model_name"],
            output_dir=payload["output_dir"],
        )
        return 0

    import csv

    from tifffile import imread

    image_path = Path(payload["image_path"])
    output_csv_path = Path(payload["output_csv_path"])
    model_name = payload["model_name"]
    use_gpu = bool(payload.get("use_gpu", True))

    print(f"Reading Spotiflow input image: {image_path}")
    image_zyx = np.asarray(imread(image_path))
    spots_coords = run_spotiflow_spot_detection(
        image_zyx,
        model_name=model_name,
        use_gpu=use_gpu,
    )
    if spots_coords.ndim == 1 and spots_coords.size == 0:
        spots_coords = np.empty((0, 3), dtype=float)

    output_csv_path.parent.mkdir(parents=True, exist_ok=True)
    with output_csv_path.open("w", encoding="utf-8", newline="") as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(["index", "axis-0", "axis-1", "axis-2"])
        for point_index, point in enumerate(np.asarray(spots_coords)):
            writer.writerow([point_index, *point.tolist()])
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
