from collections.abc import Iterable, Mapping
from configparser import ConfigParser
from enum import Enum
from pathlib import Path

from carltonlab_napari_tools._shared_variables import (
    PICK_NUCLEI_DIR_NAME,
    PROJECT_FILE_DIR_NAME,
    SBS_FLAGS_FILE_NAME,
)


class SBSFlag(str, Enum):
    IGNORE = "Ignore"
    APOPTOTIC = "Apoptotic"


def _get_sbs_flags_path(project_path: Path) -> Path:
    return (
        project_path
        / PROJECT_FILE_DIR_NAME
        / PICK_NUCLEI_DIR_NAME
        / SBS_FLAGS_FILE_NAME
    )


def load_sbs_flags(project_path: Path) -> dict[str, list[str]]:
    flags_path = _get_sbs_flags_path(project_path)
    if not flags_path.is_file():
        return {}

    config = ConfigParser()
    try:
        config.read(flags_path)
        if not config.has_section("sbs_flags"):
            return {}
    except (ConfigParser.Error, OSError):
        return {}

    return {
        sbs_name: [
            flag.strip() for flag in raw_flags.split(";") if flag.strip()
        ]
        for sbs_name, raw_flags in config.items("sbs_flags")
    }


def save_sbs_flags(
    project_path: Path,
    flags: Mapping[str, Iterable[SBSFlag | str]],
) -> bool:
    flags_path = _get_sbs_flags_path(project_path)
    config = ConfigParser()
    config["sbs_flags"] = {
        sbs_name: ";".join(
            flag.value if isinstance(flag, SBSFlag) else flag
            for flag in sbs_flags
        )
        + ";"
        for sbs_name, sbs_flags in flags.items()
    }

    try:
        flags_path.parent.mkdir(parents=True, exist_ok=True)
        with flags_path.open("w", encoding="utf-8") as config_file:
            config.write(config_file)
    except OSError:
        return False

    return True
