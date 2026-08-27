from collections.abc import Callable
from pathlib import Path

from qtpy.QtCore import QSignalBlocker, Qt
from qtpy.QtWidgets import QListWidget, QListWidgetItem, QWidget


class CLTProjectListWidget(QListWidget):
    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        row_factory: Callable[[Path], QWidget],
    ) -> None:
        super().__init__(parent)

        self._project_paths: list[Path] = []
        self._row_factory = row_factory
        self.setSpacing(6)

    def set_project_paths(self, project_paths: list[Path]) -> None:
        self._project_paths = list(project_paths)
        self._update_rows()

    def add_project_paths(self, project_paths: list[Path]) -> None:
        for project_path in project_paths:
            if project_path not in self._project_paths:
                self._project_paths.append(project_path)

        self._update_rows()

    def get_project_paths(self) -> list[Path]:
        return list(self._project_paths)

    def get_current_project_path(self) -> Path | None:
        current_item = self.currentItem()
        if current_item is None:
            return None

        project_path = current_item.data(Qt.ItemDataRole.UserRole)
        return project_path if isinstance(project_path, Path) else None

    def remove_selected_project_paths(self) -> None:
        selected_paths = {
            item.data(Qt.ItemDataRole.UserRole)
            for item in self.selectedItems()
        }

        self._project_paths = [
            project_path
            for project_path in self._project_paths
            if project_path not in selected_paths
        ]
        self._update_rows()

    def refresh_rows(self) -> None:
        self._update_rows()

    def _update_rows(self) -> None:
        current_project_path = self.get_current_project_path()

        with QSignalBlocker(self):
            self.clear()

            for project_path in self._project_paths:
                list_item = QListWidgetItem()
                list_item.setData(Qt.ItemDataRole.UserRole, project_path)
                self.addItem(list_item)

                row_widget = self._row_factory(project_path)
                list_item.setSizeHint(row_widget.sizeHint())
                self.setItemWidget(list_item, row_widget)

            if current_project_path is not None:
                for index in range(self.count()):
                    item = self.item(index)
                    if (
                        item.data(Qt.ItemDataRole.UserRole)
                        == current_project_path
                    ):
                        self.setCurrentItem(item)
                        break
