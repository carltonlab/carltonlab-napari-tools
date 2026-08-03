import itertools
import os
import struct
from argparse import ArgumentParser
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

from bioio_base.exceptions import UnsupportedFileFormatError
from mrc import DVFile
from mrc._new import BE_HDR, LE_HDR, _byte_order
from ndevio import nImage


def _is_dv_like_file(image_path: Path) -> bool:
    name = image_path.name.lower()
    return name.endswith((".dv", ".deconzs", ".zs", "_add_decon"))


def _carltonlab_dv_metadata_check(image_path: Path) -> bool:
    try:
        with DVFile(image_path) as dv:
            if dv.hdr.nc <= 1:
                return True
            if dv.ext_hdr is None:
                return False

            data = dv.to_xarray(delayed=False, squeeze=False)
            channels = data.coords.get("C")
            return channels is not None and len(channels) == dv.hdr.nc
    except (OSError, ValueError, IndexError, KeyError, TypeError):
        return False


def _repair_dv_metadata(image_path: Path) -> str:
    with DVFile(image_path) as dv:
        header = dv.hdr
        data_bytes = dv.data.tobytes()

    if header.nc <= 1:
        return str(image_path)

    with image_path.open("rb") as source:
        byte_order = _byte_order(source)
        if byte_order is None:
            raise ValueError(f"Invalid DV byte order: {image_path}")

        header_struct = LE_HDR if byte_order == "<" else BE_HDR
        unpacked = header_struct.unpack(source.read(header_struct.size))
        title = unpacked[-1]

    n_ints = 8
    n_floats = 32
    record_length = (n_ints + n_floats) * 4
    extended_header_length = header.n_sections * record_length

    repaired_header = header._replace(
        ext_hdr_len=extended_header_length,
        n_ints=n_ints,
        n_floats=n_floats,
    )

    frame_struct = struct.Struct(f"{byte_order}8i14f")
    wavelengths = [
        header.wave1,
        header.wave2,
        header.wave3,
        header.wave4,
        header.wave5,
    ][: header.nc]

    sizes = {"T": header.nt, "C": header.nc, "Z": header.nz}
    frames = bytearray()

    for coordinates in itertools.product(
        *(range(sizes[axis]) for axis in header.sequence_order)
    ):
        coordinate_map = dict(
            zip(header.sequence_order, coordinates, strict=True)
        )
        channel = coordinate_map["C"]
        z_index = coordinate_map["Z"]
        wavelength = wavelengths[channel]

        frame = frame_struct.pack(
            *(0,) * 8,
            0.0,
            0.0,
            float(header.x0),
            float(header.y0),
            float(header.z0 + z_index * header.dz),
            float(header.min),
            float(header.max),
            float(header.mean),
            0.0,
            0.0,
            float(wavelength),
            float(wavelength),
            1.0,
            1.0,
        )
        frames.extend(frame)
        frames.extend(b"\x00" * (record_length - len(frame)))

    header_bytes = header_struct.pack(*repaired_header, title)
    temporary_path: str | None = None

    try:
        with NamedTemporaryFile(
            mode="wb",
            dir=image_path.parent,
            prefix=f".{image_path.name}.",
            suffix=".dv",
            delete=False,
        ) as temporary:
            temporary_path = temporary.name
            temporary.write(header_bytes)
            temporary.write(frames)
            temporary.write(data_bytes)

        repaired_image = nImage(temporary_path)
        _ = repaired_image.shape
        os.replace(temporary_path, image_path)
    except Exception:
        if temporary_path is not None:
            Path(temporary_path).unlink(missing_ok=True)
        raise

    return str(image_path)


def _carltonlab_normalize_dv_path(image_path: Path) -> Path:
    """Repair and normalize CarltonLab DV-related files."""
    if not _is_dv_like_file(image_path):
        return image_path

    if not _carltonlab_dv_metadata_check(image_path):
        image_path = Path(_repair_dv_metadata(image_path))

    normalized_path: Path | None = None
    name = image_path.name

    if name.endswith("_R3D.dv_add_decon.zs"):
        normalized_path = image_path.with_name(
            f"{name.removesuffix('_R3D.dv_add_decon.zs')}_deconzs.dv"
        )
    elif name.endswith("_R3D.dv_add_decon"):
        normalized_path = image_path.with_name(
            f"{name.removesuffix('_R3D.dv_add_decon')}_decon.dv"
        )

    if normalized_path is None:
        return image_path

    if normalized_path.exists():
        raise FileExistsError(
            f"Cannot normalize {image_path}: destination already exists: "
            f"{normalized_path}"
        )

    image_path.rename(normalized_path)
    return normalized_path


def _carltonlab_normalize_image_data(data: Any) -> Any:
    """Normalize CarltonLab image data for downstream readers."""
    if not data.dtype.isnative:
        data = data.astype(data.dtype.newbyteorder("="), copy=False)

    for dimension in ("S", "T"):
        if dimension in data.dims:
            if data.sizes[dimension] != 1:
                raise ValueError(
                    f"CarltonLab images must have one {dimension} dimension."
                )
            data = data.isel({dimension: 0}, drop=True)

    rename_map = {
        dimension: dimension.lower()
        for dimension in data.dims
        if dimension in {"C", "Z", "Y", "X"}
    }
    return data.rename(rename_map)


def resolve_image_data(image_path: str | Path) -> Any | None:
    """Resolve a CarltonLab image and return normalized image data."""
    image = resolve_image(image_path)
    if image is None:
        return None
    return _carltonlab_normalize_image_data(image.xarray_data)


def resolve_image(image_path: str | Path) -> nImage | None:
    image_path = Path(image_path)

    image_path = _carltonlab_normalize_dv_path(image_path)

    image: nImage
    try:
        image = nImage(str(image_path))
    except UnsupportedFileFormatError:
        print(
            "UnsupportedFileFormatError, try unstalling the corresponding bioio package"
        )
        return None
    return image


if __name__ == "__main__":
    arg_parser = ArgumentParser()
    arg_parser.add_argument("-f", "--file", type=Path)
    arguments = arg_parser.parse_args()

    if not arguments.file.exists():
        raise ValueError(f"File {arguments.file} does not exist.")
    image = resolve_image(str(arguments.file))
    print("")
    print(f"The image is: {str(arguments.file)}")
    print(f"The image shape is: {image.shape}")
