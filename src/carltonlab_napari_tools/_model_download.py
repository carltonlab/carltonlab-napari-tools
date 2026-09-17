from __future__ import annotations

from collections.abc import Callable
from configparser import ConfigParser
from hashlib import sha256
from pathlib import Path
from urllib.request import urlopen

_MODEL_CONFIG_PATH = (
    Path(__file__).resolve().parent / "segmentation" / "models.config"
)
_BIOIMAGEIO_WEIGHT_URL = (
    "https://hypha.aicell.io/bioimage-io/artifacts/"
    "{model_id}/files/{weight_source}"
)


def load_bioimageio_model_config(model_name: str) -> dict[str, str]:
    """Load one BioImage.IO model entry from the package configuration."""
    config = ConfigParser()
    if not _MODEL_CONFIG_PATH.is_file():
        raise FileNotFoundError(
            f"BioImage.IO model configuration not found: {_MODEL_CONFIG_PATH}"
        )

    config.read(_MODEL_CONFIG_PATH)
    if not config.has_section(model_name):
        raise KeyError(
            f"BioImage.IO model {model_name!r} is not configured in "
            f"{_MODEL_CONFIG_PATH}"
        )

    required_keys = ("model_id", "weight_source", "sha256")
    values = {
        key: config.get(model_name, key).strip() for key in required_keys
    }
    missing_keys = [key for key, value in values.items() if not value]
    if missing_keys:
        raise ValueError(
            f"BioImage.IO model {model_name!r} is missing: "
            f"{', '.join(missing_keys)}"
        )
    return values


def download_bioimageio_weight(
    *,
    model_id: str,
    weight_source: str,
    expected_sha256: str,
    output_directory: str | Path,
    progress_callback: Callable[[int], None] | None = None,
) -> Path:
    """Download and verify one BioImage.IO model weight."""
    output_directory_path = Path(output_directory)
    output_directory_path.mkdir(parents=True, exist_ok=True)
    output_path = output_directory_path / weight_source

    if output_path.is_file():
        if _matches_sha256(output_path, expected_sha256):
            return output_path
        output_path.unlink()

    partial_path = output_path.with_name(f"{output_path.name}.part")
    url = _BIOIMAGEIO_WEIGHT_URL.format(
        model_id=model_id,
        weight_source=weight_source,
    )

    print(f"Downloading BioImage.IO weight: {weight_source}", flush=True)
    with urlopen(url) as response, partial_path.open("wb") as output:
        digest = sha256()
        downloaded_bytes = 0
        last_reported_bucket = 0
        progress_interval = 100 * 1024 * 1024

        while chunk := response.read(1024 * 1024):
            output.write(chunk)
            digest.update(chunk)
            downloaded_bytes += len(chunk)

            completed_bucket = downloaded_bytes // progress_interval
            if completed_bucket > last_reported_bucket:
                downloaded_mb = completed_bucket * 100
                print(f"Downloaded {downloaded_mb} MB", flush=True)
                if progress_callback is not None:
                    progress_callback(downloaded_mb)
                last_reported_bucket = completed_bucket

    actual_sha256 = digest.hexdigest()
    if actual_sha256 != expected_sha256:
        partial_path.unlink(missing_ok=True)
        raise RuntimeError(
            "BioImage.IO weight checksum mismatch: "
            f"expected {expected_sha256}, got {actual_sha256}"
        )

    partial_path.replace(output_path)
    return output_path


def get_bioimageio_weight_path(
    model_name: str,
    model_directory: str | Path,
) -> Path:
    """Return the configured weight path inside one model directory."""
    model_config = load_bioimageio_model_config(model_name)
    return Path(model_directory) / model_config["weight_source"]


def is_bioimageio_weight_available(
    model_name: str,
    model_directory: str | Path,
) -> bool:
    """Return whether one directory contains the valid configured weight."""
    model_config = load_bioimageio_model_config(model_name)
    weight_path = Path(model_directory) / model_config["weight_source"]
    return weight_path.is_file() and _matches_sha256(
        weight_path,
        model_config["sha256"],
    )


def _matches_sha256(path: Path, expected_sha256: str) -> bool:
    digest = sha256()
    with path.open("rb") as input_file:
        while chunk := input_file.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest() == expected_sha256
