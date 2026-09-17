from __future__ import annotations

from configparser import ConfigParser
from dataclasses import dataclass

from platformdirs import user_config_path

_APP_NAME = "carltonlab-napari-tools"
_CONFIG_FILE_NAME = "auto_foci_count.config"
_CONFIG_SECTION = "AutomaticFociCount"
_AUTOMATIC_VALUE = "automatic"


@dataclass
class AutoFociCountSettings:
    """Settings for the automatic foci-counting workflow."""

    run_entire_workflow: bool = True
    registration_channel: int = 1
    registration_scale: int | None = None
    use_gpu: bool = True
    num_workers: int = 0
    n_batch: int = 0
    filter_channels_enabled: bool = True
    filter_channels: str = "1"
    minimum_colocalization_intensity_ratio: float = 0.25


class AutoFociCountSettingsManager:
    """Load and save automatic foci-counting settings."""

    def __init__(self) -> None:
        self.config_directory = user_config_path(_APP_NAME)
        self.config_path = self.config_directory / _CONFIG_FILE_NAME

    def load(self) -> AutoFociCountSettings:
        if not self.config_path.is_file():
            settings = AutoFociCountSettings()
            self.save(settings)
            return settings

        config = ConfigParser()
        config.read(self.config_path)
        if not config.has_section(_CONFIG_SECTION):
            settings = AutoFociCountSettings()
            self.save(settings)
            return settings

        return AutoFociCountSettings(
            run_entire_workflow=config.getboolean(
                _CONFIG_SECTION,
                "run_entire_workflow",
                fallback=True,
            ),
            registration_channel=config.getint(
                _CONFIG_SECTION,
                "registration_channel",
                fallback=1,
            ),
            registration_scale=self._get_optional_int(
                config,
                "registration_scale",
            ),
            use_gpu=config.getboolean(
                _CONFIG_SECTION,
                "use_gpu",
                fallback=True,
            ),
            num_workers=config.getint(
                _CONFIG_SECTION,
                "num_workers",
                fallback=0,
            ),
            n_batch=config.getint(
                _CONFIG_SECTION,
                "n_batch",
                fallback=0,
            ),
            filter_channels_enabled=config.getboolean(
                _CONFIG_SECTION,
                "filter_channels_enabled",
                fallback=True,
            ),
            filter_channels=config.get(
                _CONFIG_SECTION,
                "filter_channels",
                fallback="1",
            ),
            minimum_colocalization_intensity_ratio=config.getfloat(
                _CONFIG_SECTION,
                "minimum_colocalization_intensity_ratio",
                fallback=0.25,
            ),
        )

    def save(self, settings: AutoFociCountSettings) -> None:
        config = ConfigParser()
        config[_CONFIG_SECTION] = {
            "run_entire_workflow": str(settings.run_entire_workflow),
            "registration_channel": str(settings.registration_channel),
            "registration_scale": (
                _AUTOMATIC_VALUE
                if settings.registration_scale is None
                else str(settings.registration_scale)
            ),
            "use_gpu": str(settings.use_gpu),
            "num_workers": str(settings.num_workers),
            "n_batch": str(settings.n_batch),
            "filter_channels_enabled": str(settings.filter_channels_enabled),
            "filter_channels": settings.filter_channels,
            "minimum_colocalization_intensity_ratio": str(
                settings.minimum_colocalization_intensity_ratio
            ),
        }

        self.config_directory.mkdir(parents=True, exist_ok=True)
        with self.config_path.open("w", encoding="utf-8") as config_file:
            config.write(config_file)

    @staticmethod
    def _get_optional_int(
        config: ConfigParser,
        option: str,
    ) -> int | None:
        value = (
            config.get(
                _CONFIG_SECTION,
                option,
                fallback=_AUTOMATIC_VALUE,
            )
            .strip()
            .lower()
        )
        if value == _AUTOMATIC_VALUE:
            return None
        return int(value)
