from pathlib import Path

from qtpy.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QListWidget,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from carltonlab_napari_tools._model_directories import ModelDirectoriesManager


class CLTSegmentationModelDirectoriesWidget(QWidget):
    """Edit the directories used to store segmentation models."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)

        self._manager = ModelDirectoriesManager()

        self._layout = QVBoxLayout()
        self._layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(self._layout)

        self._directories_list = QListWidget()
        self._layout.addWidget(self._directories_list)

        self._controls = QWidget()
        self._controls_layout = QHBoxLayout()
        self._controls_layout.setContentsMargins(0, 0, 0, 0)
        self._controls.setLayout(self._controls_layout)
        self._layout.addWidget(self._controls)

        self._add_button = QPushButton("Add directory")
        self._add_button.clicked.connect(self._on_add_directory)
        self._controls_layout.addWidget(self._add_button)

        self._remove_button = QPushButton("Remove selected")
        self._remove_button.clicked.connect(self._on_remove_directory)
        self._controls_layout.addWidget(self._remove_button)

        self._save_button = QPushButton("Save")
        self._save_button.clicked.connect(self._on_save)
        self._controls_layout.addWidget(self._save_button)

        self._load_directories()

    def _load_directories(self) -> None:
        for directory in self._manager.load():
            self._directories_list.addItem(str(directory))

    def _on_add_directory(self) -> None:
        directory = QFileDialog.getExistingDirectory(
            self,
            "Select model directory",
        )
        if not directory:
            return

        directory_path = Path(directory)
        existing_directories = self._get_directories()
        if directory_path not in existing_directories:
            self._directories_list.addItem(str(directory_path))

    def _on_remove_directory(self) -> None:
        for item in self._directories_list.selectedItems():
            self._directories_list.takeItem(self._directories_list.row(item))

    def _on_save(self) -> None:
        self._manager.save(self._get_directories())

    def _get_directories(self) -> list[Path]:
        return [
            Path(self._directories_list.item(index).text())
            for index in range(self._directories_list.count())
        ]
