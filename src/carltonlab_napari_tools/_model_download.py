from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from urllib.request import urlopen

_BIOIMAGEIO_WEIGHT_URL = (
    "https://hypha.aicell.io/bioimage-io/artifacts/"
    "{model_id}/files/{weight_source}"
)


def download_bioimageio_weight(
    *,
    model_id: str,
    weight_source: str,
    expected_sha256: str,
    output_directory: str | Path,
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

        while chunk := response.read(1024 * 1024):
            output.write(chunk)
            digest.update(chunk)
            downloaded_bytes += len(chunk)

            if downloaded_bytes % (100 * 1024 * 1024) < len(chunk):
                downloaded_mb = downloaded_bytes / (1024 * 1024)
                print(f"Downloaded {downloaded_mb:.0f} MB", flush=True)

    actual_sha256 = digest.hexdigest()
    if actual_sha256 != expected_sha256:
        partial_path.unlink(missing_ok=True)
        raise RuntimeError(
            "BioImage.IO weight checksum mismatch: "
            f"expected {expected_sha256}, got {actual_sha256}"
        )

    partial_path.replace(output_path)
    return output_path


def _matches_sha256(path: Path, expected_sha256: str) -> bool:
    digest = sha256()
    with path.open("rb") as input_file:
        while chunk := input_file.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest() == expected_sha256
