from pathlib import Path

from carltonlab_napari_tools.automatic_foci_count import _auto_settings
from carltonlab_napari_tools.automatic_foci_count._auto_settings import (
    AutoFociCountSettings,
    AutoFociCountSettingsManager,
)


def make_manager(tmp_path: Path, monkeypatch) -> AutoFociCountSettingsManager:
    config_directory = tmp_path / "config"
    monkeypatch.setattr(
        _auto_settings,
        "user_config_path",
        lambda _app_name: config_directory,
    )
    return AutoFociCountSettingsManager()


def test_load_creates_default_settings_file(
    tmp_path: Path,
    monkeypatch,
) -> None:
    manager = make_manager(tmp_path, monkeypatch)

    settings = manager.load()

    assert settings == AutoFociCountSettings()
    assert manager.config_path.is_file()


def test_save_and_load_preserve_all_settings(
    tmp_path: Path,
    monkeypatch,
) -> None:
    manager = make_manager(tmp_path, monkeypatch)
    expected = AutoFociCountSettings(
        registration_channel=2,
        registration_scale=4,
        use_gpu=False,
        num_workers=3,
        n_batch=5,
        filter_channels_enabled=False,
        filter_channels="1,3",
        minimum_colocalization_intensity_ratio=0.75,
    )

    manager.save(expected)

    assert manager.load() == expected


def test_save_writes_automatic_registration_scale(
    tmp_path: Path,
    monkeypatch,
) -> None:
    manager = make_manager(tmp_path, monkeypatch)
    manager.save(AutoFociCountSettings(registration_scale=None))

    config_text = manager.config_path.read_text(encoding="utf-8")

    assert "registration_scale = automatic" in config_text
    assert manager.load().registration_scale is None


def test_load_missing_section_restores_defaults(
    tmp_path: Path,
    monkeypatch,
) -> None:
    manager = make_manager(tmp_path, monkeypatch)
    manager.config_directory.mkdir()
    manager.config_path.write_text("[OtherSection]\nvalue = test\n")

    assert manager.load() == AutoFociCountSettings()
