import os
from configparser import ConfigParser
from enum import Enum
from pathlib import Path
from tempfile import NamedTemporaryFile

from carltonlab_napari_tools._shared_variables import (
    PICK_NUCLEI_DIR_NAME,
    PROJECT_FILE_DIR_NAME,
    SBS_FLAGS_FILE_NAME,
)


class SBSFlag(str, Enum):
    IGNORE = "Ignore"
    APOPTOTIC = "Apoptotic"
    COORD_RECALC_NEEDED = "COORD_RECALC_NEEDED"
    OUT_OF_SPLINE = "OUT_OF_SPLINE"


class SBSFlagsManager:
    def __init__(self, project_path: Path) -> None:
        self._project_path = project_path
        self._flags: dict[str, list[str]] = {}

    @property
    def flags(self) -> dict[str, list[str]]:
        return {
            sbs_name: list(sbs_flags)
            for sbs_name, sbs_flags in self._flags.items()
        }

    def _get_flags_path(self) -> Path:
        return (
            self._project_path
            / PROJECT_FILE_DIR_NAME
            / PICK_NUCLEI_DIR_NAME
            / SBS_FLAGS_FILE_NAME
        )

    def load(self) -> bool:
        flags_path = self._get_flags_path()
        self._flags = {}
        if not flags_path.is_file():
            return True

        config = ConfigParser()
        try:
            config.read(flags_path)
            if not config.has_section("sbs_flags"):
                return True
        except (ConfigParser.Error, OSError):
            return False

        self._flags = {
            sbs_name: [
                flag.strip() for flag in raw_flags.split(";") if flag.strip()
            ]
            for sbs_name, raw_flags in config.items("sbs_flags")
        }
        return True

    def get_flags(self, sbs_name: str) -> list[str]:
        return list(self._flags.get(sbs_name, []))

    def add_flag(self, sbs_name: str, flag: SBSFlag | str) -> None:
        flag_value = flag.value if isinstance(flag, SBSFlag) else flag
        if flag_value not in self._flags.setdefault(sbs_name, []):
            self._flags[sbs_name].append(flag_value)

    def remove_flag(self, sbs_name: str, flag: SBSFlag | str) -> None:
        flag_value = flag.value if isinstance(flag, SBSFlag) else flag
        if sbs_name not in self._flags:
            return

        self._flags[sbs_name] = [
            current_flag
            for current_flag in self._flags[sbs_name]
            if current_flag != flag_value
        ]
        if not self._flags[sbs_name]:
            del self._flags[sbs_name]

    def save(self) -> bool:
        config = ConfigParser()
        config["sbs_flags"] = {
            sbs_name: ";".join(sbs_flags) + ";"
            for sbs_name, sbs_flags in self._flags.items()
        }

        temporary_path: Path | None = None
        try:
            flags_path = self._get_flags_path()
            flags_path.parent.mkdir(parents=True, exist_ok=True)
            with NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=flags_path.parent,
                prefix=f".{flags_path.name}.",
                suffix=".tmp",
                delete=False,
            ) as temporary_file:
                temporary_path = Path(temporary_file.name)
                config.write(temporary_file)

            os.replace(temporary_path, flags_path)
            temporary_path = None
        except OSError:
            return False
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)

        return True
