from configparser import ConfigParser
from datetime import datetime
from pathlib import Path

from carltonlab_napari_tools._shared_variables import PROJECT_TYPES


def save_multigonad_project(
    saving_path: str | Path,
    project_directories: list[str | Path],
    project_type: str,
) -> bool:
    if project_type not in PROJECT_TYPES:
        return False

    version_config_path = (
        Path(__file__).resolve().parent / PROJECT_TYPES[project_type]
    )
    version_config = ConfigParser()
    try:
        version_config.read(version_config_path)
        project_version = version_config.get("project", "version")
    except (ConfigParser.Error, OSError, KeyError):
        return False

    config_path = Path(saving_path)
    if config_path.suffix.lower() == ".config":
        config_path = config_path.with_name(f"{config_path.stem}.config")
    else:
        config_path = config_path.with_name(f"{config_path.name}.config")

    config = ConfigParser()
    config["project"] = {
        "type": project_type,
        "version": project_version,
        "created_at": datetime.now()
        .astimezone()
        .isoformat(timespec="seconds"),
    }
    config["project_directories"] = {
        f"project_{index}": str(project_directory)
        for index, project_directory in enumerate(
            project_directories,
            start=1,
        )
    }

    try:
        with config_path.open("w", encoding="utf-8") as config_file:
            config.write(config_file)
    except OSError:
        return False

    return True


def load_multigonad_project(
    project_file_path: str | Path,
) -> ConfigParser | None:
    config = ConfigParser()

    try:
        with Path(project_file_path).open(encoding="utf-8") as config_file:
            config.read_file(config_file)
    except (OSError, ConfigParser.Error):
        return None

    return config
