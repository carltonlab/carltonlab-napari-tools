import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from carltonlab_napari_tools import _sbs_lock_manager as lock_module
from carltonlab_napari_tools._sbs_lock_manager import SBSLockManager


def test_acquire_creates_lock_and_records_ownership(
    tmp_path: Path,
) -> None:
    manager = SBSLockManager(tmp_path)

    assert manager.acquire("sbs1")
    assert manager.owns("sbs1")
    assert manager.is_locked("sbs1")
    assert manager._lock_path("sbs1").is_file()


def test_second_manager_cannot_acquire_active_lock(
    tmp_path: Path,
) -> None:
    first_manager = SBSLockManager(tmp_path)
    second_manager = SBSLockManager(tmp_path)

    assert first_manager.acquire("sbs1")
    assert not second_manager.acquire("sbs1")
    assert first_manager.owns("sbs1")
    assert not second_manager.owns("sbs1")


def test_release_allows_another_manager_to_acquire(
    tmp_path: Path,
) -> None:
    first_manager = SBSLockManager(tmp_path)
    second_manager = SBSLockManager(tmp_path)

    assert first_manager.acquire("sbs1")
    assert first_manager.release("sbs1")
    assert not first_manager.owns("sbs1")
    assert second_manager.acquire("sbs1")


def test_manager_cannot_release_another_manager_lock(
    tmp_path: Path,
) -> None:
    first_manager = SBSLockManager(tmp_path)
    second_manager = SBSLockManager(tmp_path)

    assert first_manager.acquire("sbs1")
    assert not second_manager.release("sbs1")
    assert first_manager.owns("sbs1")


def test_stale_lock_is_removed_and_can_be_reacquired(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(lock_module, "SBS_LOCK_TIMEOUT_SECONDS", 300)

    first_manager = SBSLockManager(tmp_path)
    second_manager = SBSLockManager(tmp_path)
    assert first_manager.acquire("sbs1")

    lock_path = first_manager._lock_path("sbs1")
    stale_created_at = datetime.now(UTC) - timedelta(seconds=301)
    lock_data = json.loads(lock_path.read_text(encoding="utf-8"))
    lock_data["created_at"] = stale_created_at.isoformat()
    lock_path.write_text(json.dumps(lock_data), encoding="utf-8")

    assert not second_manager.is_locked("sbs1")
    assert not lock_path.exists()
    assert second_manager.acquire("sbs1")


def test_release_all_releases_owned_locks(
    tmp_path: Path,
) -> None:
    manager = SBSLockManager(tmp_path)

    assert manager.acquire("sbs1")
    assert manager.acquire("sbs2")

    manager.release_all()

    assert not manager.owns("sbs1")
    assert not manager.owns("sbs2")
    assert not manager.is_locked("sbs1")
    assert not manager.is_locked("sbs2")
