#!/usr/bin/env python3
import argparse
import configparser
from collections.abc import Iterable
from pathlib import Path

from mrc import DVFile


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


def _translation_from_header(header, negate: bool) -> dict[str, float]:
    trans = {
        "z": float(getattr(header, "z0", 0.0)),
        "y": float(getattr(header, "y0", 0.0)),
        "x": float(getattr(header, "x0", 0.0)),
    }
    if negate:
        return {k: -v for k, v in trans.items()}
    return trans


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extract DeltaVision stage positions into a config file."
    )
    parser.add_argument(
        "inputs",
        nargs="+",
        help="Input files or directories with DeltaVision files.",
    )
    parser.add_argument(
        "--output",
        default="stage_positions.ini",
        help="Output INI file path.",
    )
    parser.add_argument(
        "--negate-translation",
        action="store_true",
        help="Negate stage offsets from header to match image axis orientation.",
    )
    parser.add_argument(
        "--units",
        default="unknown",
        help="Units for stage positions (e.g. um).",
    )

    args = parser.parse_args()
    input_paths = _iter_paths(args.inputs)

    if not input_paths:
        raise SystemExit("No input files found.")

    config = configparser.ConfigParser()
    config["metadata"] = {"units": args.units}

    for input_path in input_paths:
        with DVFile(str(input_path)) as dvf:
            trans = _translation_from_header(
                dvf.hdr, negate=args.negate_translation
            )
        section = f"tile:{input_path.name}"
        config[section] = {
            "z": f"{trans['z']:.6f}",
            "y": f"{trans['y']:.6f}",
            "x": f"{trans['x']:.6f}",
        }

    output_path = Path(args.output)
    with output_path.open("w", encoding="utf-8") as handle:
        config.write(handle)

    print(f"Wrote {output_path}")


if __name__ == "__main__":
    main()
