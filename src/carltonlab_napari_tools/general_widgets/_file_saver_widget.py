import re
from collections.abc import Callable
from pathlib import Path

from qtpy.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)


class CLToggleSavePathWidget(QWidget):
    def __init__(
        self,
        parent: QWidget,
        *,
        title: str = "Save file",
        toggled: bool = True,
        allow_overwrite: bool = False,
        force_suffix: str | None = None,
    ) -> None:
        super().__init__(parent)

        self._saving_path: Path = Path("")
        self._allow_overwrite: bool = allow_overwrite
        self._force_suffix: str | None = force_suffix
        self._save_callback: Callable[[], None] | None = None

        self._layout = QVBoxLayout()
        self._layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(self._layout)

        self._title_cb = QCheckBox(title)
        self._title_cb.setStyleSheet("font-weight: bold")
        self._title_cb.toggled.connect(self._on_title_toggled)
        self._layout.addWidget(self._title_cb)

        self._path_c = QWidget()
        self._path_layout = QHBoxLayout()
        self._path_layout.setContentsMargins(0, 0, 0, 0)
        self._path_c.setLayout(self._path_layout)
        self._layout.addWidget(self._path_c)

        self._path_title_lb = QLabel("Path")
        self._path_title_lb.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Preferred,
        )
        self._path_layout.addWidget(self._path_title_lb)

        self._path_le = QLineEdit()
        self._path_le.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Preferred,
        )
        self._path_le.textEdited.connect(self._on_path_edited)
        self._path_layout.addWidget(self._path_le)

        self._status_lb = QLabel("")
        self._layout.addWidget(self._status_lb)

        self._save_button = QPushButton("Save")
        self._save_button.clicked.connect(self._on_save_button_pressed)
        self._layout.addWidget(self._save_button)

        self._on_title_toggled(toggled)
        self._update_status_label()

    def _on_title_toggled(self, state: bool) -> None:
        self._path_c.setEnabled(state)
        self._status_lb.setEnabled(state)
        self._update_status_label()

    def _update_status_label(self) -> None:
        path_text = self._path_le.text().strip()

        if not path_text:
            self._status_lb.setText("No path specified")
            self._status_lb.setStyleSheet("color: gray; font-style: italic;")
            self._save_button.setEnabled(False)
        elif Path(path_text).exists():
            self._status_lb.setText("Path already exists")
            self._status_lb.setStyleSheet(
                "color: #A80000; font-style: normal;"
            )
            self._save_button.setEnabled(
                self._title_cb.isChecked() and self._allow_overwrite
            )
        else:
            self._status_lb.setText("Path does not exist")
            self._status_lb.setStyleSheet(
                "color: #29BA00; font-style: normal;"
            )
            self._save_button.setEnabled(self._title_cb.isChecked())

    def _on_path_edited(self, text: str) -> None:
        text = text.strip()
        if not text:
            self._saving_path = Path("")
            self._update_status_label()
            return

        path = Path(text)
        file_name = path.name.lower()
        file_name = re.sub(r"[^a-z0-9_.-]", "", file_name)

        force_suffix = self._force_suffix
        if force_suffix is not None:
            force_suffix = force_suffix.lower()
            if not file_name.endswith(force_suffix):
                file_name += force_suffix

        final_path = path.with_name(file_name)
        self._path_le.setText(str(final_path))
        self._saving_path = final_path
        self._update_status_label()

    @property
    def saving_path(self) -> Path:
        return self._saving_path

    @saving_path.setter
    def saving_path(self, value: str | Path | None) -> None:
        if value is None:
            self._path_le.clear()
            self._saving_path = Path("")
            self._update_status_label()
            return

        self._on_path_edited(str(value))

    def _path_exists(self) -> None:
        if self._allow_overwrite:
            return

    @property
    def allow_overwrite(self) -> bool:
        return self._allow_overwrite

    @allow_overwrite.setter
    def allow_overwrite(self, value: bool) -> None:
        self._allow_overwrite = value
        self._update_status_label()

    @property
    def force_suffix(self) -> str | None:
        return self._force_suffix

    @force_suffix.setter
    def force_suffix(self, value: str | None) -> None:
        if self._force_suffix == value:
            return

        self._force_suffix = value
        self._on_path_edited(self._path_le.text())

    def connect_save_callback(
        self,
        callback: Callable[[], None],
    ) -> None:
        self._save_callback = callback

    def _on_save_button_pressed(self) -> None:
        if self._save_callback is None:
            return
        if not self._path_le.text().strip():
            return
        if Path(self._path_le.text()).exists() and not self._allow_overwrite:
            return
        self._save_callback()

    @property
    def title(self) -> str | None:
        return self._title

    @title.setter
    def title(self, value: str | None) -> None:
        self._title = value
        self._title_cb.setText(value or "")
