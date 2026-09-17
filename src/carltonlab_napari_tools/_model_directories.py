from __future__ import annotations

from collections.abc import Iterable
from configparser import ConfigParser
from pathlib import Path

from platformdirs import user_config_path, user_data_path

_APP_NAME = "carltonlab-napari-tools"
_CONFIG_DIRECTORY_NAME = "carltonlab-napari-tools"
_CONFIG_FILE_NAME = "models.config"
_CONFIG_SECTION = "ModelDirectories"


class ModelDirectoriesManager:
    """Load and save user-configured model directories."""

    def __init__(self) -> None:
        self.config_directory = user_config_path(_APP_NAME)
        self.config_path = self.config_directory / _CONFIG_FILE_NAME
        self.default_models_directory = user_data_path(_APP_NAME) / "models"

    def ensure_default_configuration(self) -> list[Path]:
        """Ensure a usable configuration and default model directory exist."""
        directories = self.load()
        if not directories:
            directories = [self.default_models_directory]
            self.save(directories)

        for directory in directories:
            directory.mkdir(parents=True, exist_ok=True)

        return directories

    def load(self) -> list[Path]:
        """Return the configured model directories."""
        if not self.config_path.is_file():
            return []

        config = ConfigParser()
        config.read(self.config_path)

        if not config.has_section(_CONFIG_SECTION):
            return []

        directories: list[Path] = []
        for _, value in config.items(_CONFIG_SECTION):
            directory = Path(value).expanduser()
            if directory not in directories:
                directories.append(directory)

        return directories

    def save(self, directories: Iterable[Path]) -> None:
        """Save model directories in their original order."""
        config = ConfigParser()
        config.add_section(_CONFIG_SECTION)

        for index, directory in enumerate(directories, start=1):
            config.set(_CONFIG_SECTION, f"directory_{index}", str(directory))

        self.config_directory.mkdir(parents=True, exist_ok=True)
        with self.config_path.open("w", encoding="utf-8") as config_file:
            config.write(config_file)
