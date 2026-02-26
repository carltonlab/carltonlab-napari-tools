#!/usr/bin/env python3
import argparse
import configparser
from collections.abc import Iterable, Sequence
from pathlib import Path

import numpy as np
from mrc import DVFile
from multiview_stitcher import ngff_utils
from multiview_stitcher import spatial_image_utils as si_utils


def _parse_spacing(value: str | None) -> dict[str, float] | None:
    if value is None:
        return None
    parts = [p.strip() for p in value.split(",")]
    if len(parts) != 3:
        raise ValueError("Expected --spacing as 'z,y,x'")
    z, y, x = (float(p) for p in parts)
    return {"z": z, "y": y, "x": x}


def _spacing_from_header(
    header, fallback: dict[str, float] | None
) -> dict[str, float]:
    # DeltaVision headers commonly include dx/dy/dz spacing.
    dx = getattr(header, "dx", None)
    dy = getattr(header, "dy", None)
    dz = getattr(header, "dz", None)
    if dx is not None and dy is not None and dz is not None:
        dx = float(dx)
        dy = float(dy)
        dz = float(dz)
        if dx > 0 and dy > 0 and dz > 0:
            return {"z": dz, "y": dy, "x": dx}

    # Fallback: use axis lengths and sizes if available.
    try:
        nx = float(header.nx)
        ny = float(header.ny)
        nz = float(header.nz)
        xlen = float(header.xlen)
        ylen = float(header.ylen)
        zlen = float(header.zlen)
    except Exception:
        nx = ny = nz = xlen = ylen = zlen = None

    if nx is not None and ny is not None and nz is not None:
        if nx <= 0 or ny <= 0 or nz <= 0:
            nx = ny = nz = None

    if xlen is not None and ylen is not None and zlen is not None:
        if xlen <= 0 or ylen <= 0 or zlen <= 0:
            xlen = ylen = zlen = None

    if (
        nx is not None
        and ny is not None
        and nz is not None
        and xlen is not None
        and ylen is not None
        and zlen is not None
    ):
        return {"z": zlen / nz, "y": ylen / ny, "x": xlen / nx}

    if fallback is None:
        raise ValueError("Spacing not found in header; provide --spacing.")
    return fallback


def _translation_from_header(header, negate: bool) -> dict[str, float]:
    trans = {
        "z": float(getattr(header, "z0", 0.0)),
        "y": float(getattr(header, "y0", 0.0)),
        "x": float(getattr(header, "x0", 0.0)),
    }
    if negate:
        return {k: -v for k, v in trans.items()}
    return trans


def _channel_names(n_channels: int, names: Sequence[str] | None) -> list[str]:
    if names:
        if len(names) != n_channels:
            raise ValueError(
                f"Expected {n_channels} channel names, got {len(names)}."
            )
        return list(names)
    return [f"ch{idx}" for idx in range(n_channels)]


def _iter_paths(paths: Iterable[str]) -> list[Path]:
    out = []
    for path in paths:
        p = Path(path)
        if p.is_dir():
            out.extend(sorted(p.glob("*.dv")))
            out.extend(sorted(p.glob("*.DV")))
            out.extend(sorted(p.glob("*.deconzs")))
            out.extend(sorted(p.glob("*_add_decon")))
            out.extend(sorted(p.glob("*.zs")))
        else:
            out.append(p)
    return out


def convert_one(
    input_path: Path,
    output_path: Path,
    spacing_fallback: dict[str, float] | None,
    channel_names: Sequence[str] | None,
    negate_translation: bool,
    stage_units: str,
    overwrite: bool,
) -> None:
    print("")
    print(f"Converting file {input_path}")
    with DVFile(str(input_path)) as dvf:
        header = dvf.hdr
        data = np.array(dvf.data, copy=True)

    spacing = _spacing_from_header(header, spacing_fallback)
    translation = _translation_from_header(header, negate=negate_translation)

    # Accept 4D (c, z, y, x) or 5D (c, t, z, y, x) with a singleton time.
    if data.ndim == 5:
        if data.shape[1] == 1:
            data = np.squeeze(data, axis=1)
        else:
            raise ValueError(
                f"{input_path} has time axis size {data.shape[1]}, expected 1."
            )
    if data.ndim != 4:
        raise ValueError(f"{input_path} is not 4D after squeeze: {data.shape}")

    channels = _channel_names(data.shape[0], channel_names)

    sim = si_utils.get_sim_from_array(
        data,
        dims=["c", "z", "y", "x"],
        scale=spacing,
        translation=translation,
        transform_key="stage_metadata",
        c_coords=channels,
    )

    ngff_utils.write_sim_to_ome_zarr(
        sim,
        output_zarr_url=str(output_path),
        overwrite=overwrite,
    )

    config = configparser.ConfigParser()
    config["metadata"] = {"units": stage_units}
    config["stage_translation"] = {
        "z": f"{translation['z']:.6f}",
        "y": f"{translation['y']:.6f}",
        "x": f"{translation['x']:.6f}",
    }
    ini_path = output_path.with_suffix(output_path.suffix + ".ini")
    with ini_path.open("w", encoding="utf-8") as handle:
        config.write(handle)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert DeltaVision files to OME-Zarr."
    )
    parser.add_argument(
        "inputs",
        nargs="+",
        help="Input files or directories with DeltaVision files.",
    )
    parser.add_argument(
        "--output-dir",
        default=".",
        help="Directory to write OME-Zarr outputs.",
    )
    parser.add_argument(
        "--spacing",
        default=None,
        help="Fallback spacing as 'z,y,x' if header spacing is missing.",
    )
    parser.add_argument(
        "--channel-names",
        nargs="+",
        help="Optional channel names in order (must match number of channels).",
    )
    parser.add_argument(
        "--negate-translation",
        action="store_true",
        help="Negate stage offsets from header to match image axis orientation.",
    )
    parser.add_argument(
        "--stage-units",
        "--stage-unit",
        default="unknown",
        help="Units for stage positions stored in the INI file (e.g. um).",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing output zarrs.",
    )

    args = parser.parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    spacing_fallback = _parse_spacing(args.spacing)
    input_paths = _iter_paths(args.inputs)

    if not input_paths:
        raise SystemExit("No input files found.")

    for input_path in input_paths:
        output_name = f"{input_path.stem}.ome.zarr"
        output_path = output_dir / output_name
        convert_one(
            input_path=input_path,
            output_path=output_path,
            spacing_fallback=spacing_fallback,
            channel_names=args.channel_names,
            negate_translation=args.negate_translation,
            stage_units=args.stage_units,
            overwrite=args.overwrite,
        )
        print(f"Wrote {output_path}")


if __name__ == "__main__":
    main()
