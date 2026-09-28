from pathlib import Path

from carltonlab_napari_tools import _model_directories as model_directories
from carltonlab_napari_tools._model_directories import ModelDirectoriesManager


def make_manager(tmp_path: Path, monkeypatch) -> ModelDirectoriesManager:
    config_directory = tmp_path / "config"
    data_directory = tmp_path / "data"
    monkeypatch.setattr(
        model_directories,
        "user_config_path",
        lambda _app_name: config_directory,
    )
    monkeypatch.setattr(
        model_directories,
        "user_data_path",
        lambda _app_name: data_directory,
    )
    return ModelDirectoriesManager()


def test_load_returns_empty_list_without_configuration(
    tmp_path: Path,
    monkeypatch,
) -> None:
    manager = make_manager(tmp_path, monkeypatch)

    assert manager.load() == []


def test_load_returns_empty_list_without_model_directories_section(
    tmp_path: Path,
    monkeypatch,
) -> None:
    manager = make_manager(tmp_path, monkeypatch)
    manager.config_directory.mkdir()
    manager.config_path.write_text("[OtherSection]\nvalue = test\n")

    assert manager.load() == []


def test_save_and_load_preserve_directory_order(
    tmp_path: Path,
    monkeypatch,
) -> None:
    manager = make_manager(tmp_path, monkeypatch)
    directories = [tmp_path / "first", tmp_path / "second"]

    manager.save(directories)

    assert manager.load() == directories


def test_load_removes_duplicate_directories(
    tmp_path: Path,
    monkeypatch,
) -> None:
    manager = make_manager(tmp_path, monkeypatch)
    directory = tmp_path / "models"

    manager.save([directory, directory])

    assert manager.load() == [directory]


def test_ensure_default_configuration_creates_default_directory(
    tmp_path: Path,
    monkeypatch,
) -> None:
    manager = make_manager(tmp_path, monkeypatch)

    directories = manager.ensure_default_configuration()

    assert directories == [manager.default_models_directory]
    assert manager.default_models_directory.is_dir()
    assert manager.config_path.is_file()
