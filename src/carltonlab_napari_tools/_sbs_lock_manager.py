import json
import os
import socket
import uuid
from datetime import UTC, datetime
from getpass import getuser
from pathlib import Path

from carltonlab_napari_tools._shared_variables import (
    PICK_NUCLEI_DIR_NAME,
    PROJECT_FILE_DIR_NAME,
    SBS_LOCK_FILE_SUFFIX,
    SBS_LOCK_TIMEOUT_SECONDS,
    SBS_LOCKS_DIR_NAME,
)


class SBSLockManager:
    def __init__(self, project_path: Path) -> None:
        self._project_path = project_path
        self._owner_token = uuid.uuid4().hex
        self._owned_sbs_names: set[str] = set()

    def _lock_path(self, sbs_name: str) -> Path:
        return (
            self._project_path
            / PROJECT_FILE_DIR_NAME
            / PICK_NUCLEI_DIR_NAME
            / SBS_LOCKS_DIR_NAME
            / f"{sbs_name}{SBS_LOCK_FILE_SUFFIX}"
        )

    def owns(self, lock_name: str) -> bool:
        return lock_name in self._owned_sbs_names

    def is_locked(self, lock_name: str) -> bool:
        lock_path = self._lock_path(lock_name)
        if not lock_path.is_file():
            return False
        if not self._is_stale(lock_path):
            return True
        try:
            lock_path.unlink()
        except (FileNotFoundError, OSError):
            return True
        return False

    @staticmethod
    def _is_stale(lock_path: Path) -> bool:
        try:
            with lock_path.open(encoding="utf-8") as lock_file:
                lock_data = json.load(lock_file)
            created_at = datetime.fromisoformat(lock_data["created_at"])
        except (
            KeyError,
            OSError,
            TypeError,
            ValueError,
            json.JSONDecodeError,
        ):
            return False

        age_seconds = (datetime.now(UTC) - created_at).total_seconds()
        return age_seconds > SBS_LOCK_TIMEOUT_SECONDS

    def acquire(self, sbs_name: str) -> bool:
        lock_path = self._lock_path(sbs_name)
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        lock_data = {
            "owner_token": self._owner_token,
            "user": getuser(),
            "host": socket.gethostname(),
            "pid": os.getpid(),
            "created_at": datetime.now(UTC).isoformat(),
        }

        try:
            with lock_path.open("x", encoding="utf-8") as lock_file:
                json.dump(lock_data, lock_file, indent=2)
        except FileExistsError:
            if not self._is_stale(lock_path):
                return False
            try:
                lock_path.unlink()
            except (FileNotFoundError, OSError):
                return False
            try:
                with lock_path.open("x", encoding="utf-8") as lock_file:
                    json.dump(lock_data, lock_file, indent=2)
            except (FileExistsError, OSError):
                return False
        except OSError:
            return False

        self._owned_sbs_names.add(sbs_name)
        return True

    def release(self, sbs_name: str) -> bool:
        lock_path = self._lock_path(sbs_name)
        try:
            with lock_path.open(encoding="utf-8") as lock_file:
                lock_data = json.load(lock_file)
        except (FileNotFoundError, OSError, json.JSONDecodeError):
            self._owned_sbs_names.discard(sbs_name)
            return False

        if lock_data.get("owner_token") != self._owner_token:
            return False

        try:
            lock_path.unlink()
        except OSError:
            return False

        self._owned_sbs_names.discard(sbs_name)
        return True

    def release_all(self) -> None:
        for sbs_name in tuple(self._owned_sbs_names):
            self.release(sbs_name)
