from configparser import ConfigParser
from datetime import datetime
from pathlib import Path

from carltonlab_napari_tools._multigonad_project import (
    load_multigonad_project,
    save_multigonad_project,
)


def test_save_multigonad_project_writes_config(
    tmp_path: Path,
) -> None:
    save_path = tmp_path / "experiment"
    project_paths = [
        tmp_path / "genotype_a" / "gonad1_clsp_project",
        tmp_path / "genotype_a" / "gonad2_clsp_project",
    ]

    assert save_multigonad_project(
        saving_path=save_path,
        project_directories=project_paths,
        project_type="clsp",
    )

    config_path = tmp_path / "experiment.config"
    config = load_multigonad_project(config_path)

    assert config is not None
    assert config.get("project", "type") == "clsp"
    assert config.get("project", "version") == "0.0.1"
    assert config.get("project_directories", "project_1") == str(
        project_paths[0]
    )
    assert config.get("project_directories", "project_2") == str(
        project_paths[1]
    )
    datetime.fromisoformat(config.get("project", "created_at"))


def test_save_multigonad_project_does_not_duplicate_config_suffix(
    tmp_path: Path,
) -> None:
    save_path = tmp_path / "experiment.config"

    assert save_multigonad_project(
        saving_path=save_path,
        project_directories=[],
        project_type="clsp",
    )

    assert save_path.is_file()
    assert not (tmp_path / "experiment.config.config").exists()


def test_save_multigonad_project_rejects_unknown_type(
    tmp_path: Path,
) -> None:
    save_path = tmp_path / "experiment.config"

    assert not save_multigonad_project(
        saving_path=save_path,
        project_directories=[],
        project_type="unknown",
    )
    assert not save_path.exists()


def test_load_multigonad_project_returns_none_for_missing_file(
    tmp_path: Path,
) -> None:
    assert load_multigonad_project(tmp_path / "missing.config") is None


def test_load_multigonad_project_returns_config_parser(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "project.config"
    config = ConfigParser()
    config["project"] = {"type": "clsp", "version": "0.0.1"}

    with config_path.open("w", encoding="utf-8") as config_file:
        config.write(config_file)

    loaded_config = load_multigonad_project(config_path)

    assert loaded_config is not None
    assert loaded_config.get("project", "type") == "clsp"
