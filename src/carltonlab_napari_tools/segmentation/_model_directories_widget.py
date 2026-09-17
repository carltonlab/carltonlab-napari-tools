from collections.abc import Callable
from pathlib import Path

from qtpy.QtGui import QColor
from qtpy.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QListWidget,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from carltonlab_napari_tools._model_directories import ModelDirectoriesManager
from carltonlab_napari_tools._model_download import (
    download_bioimageio_weight,
    is_bioimageio_weight_available,
    load_bioimageio_model_config,
)

_CELLPOSE_MODEL_NAME = "cellpose_meiotic_nuclei_3d"
_VALID_COLOR = QColor("#29BA00")
_INVALID_COLOR = QColor("#A80000")


class CLTSegmentationModelDirectoriesWidget(QWidget):
    """Edit the directories used to store segmentation models."""

    def __init__(
        self,
        parent: QWidget,
        status_update_callback: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(parent)

        self._manager = ModelDirectoriesManager()
        self._status_update_callback = status_update_callback

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

        self._download_button = QPushButton("Download model")
        self._download_button.clicked.connect(self._on_download)
        self._controls_layout.addWidget(self._download_button)

        self._load_directories()
        self._update_directory_colors()

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
            self._update_directory_colors()

    def _on_remove_directory(self) -> None:
        for item in self._directories_list.selectedItems():
            self._directories_list.takeItem(self._directories_list.row(item))
        self._update_directory_colors()

    def _on_save(self) -> None:
        self._manager.save(self._get_directories())
        self._update_directory_colors()
        self._notify_status_update()

    def _on_download(self) -> None:
        directories = self._get_directories()
        if not directories:
            QMessageBox.warning(
                self,
                "No model directory",
                "Add a model directory before downloading the model.",
            )
            return

        selected_items = self._directories_list.selectedItems()
        destination = (
            Path(selected_items[0].text())
            if selected_items
            else directories[0]
        )

        try:
            model_config = load_bioimageio_model_config(_CELLPOSE_MODEL_NAME)
            download_bioimageio_weight(
                model_id=model_config["model_id"],
                weight_source=model_config["weight_source"],
                expected_sha256=model_config["sha256"],
                output_directory=destination,
            )
        except (
            FileNotFoundError,
            KeyError,
            ValueError,
            OSError,
            RuntimeError,
        ) as error:
            QMessageBox.critical(
                self,
                "Model download failed",
                str(error),
            )
            return

        self._update_directory_colors()
        self._notify_status_update()

    def _update_directory_colors(self) -> None:
        for index in range(self._directories_list.count()):
            item = self._directories_list.item(index)
            found = is_bioimageio_weight_available(
                _CELLPOSE_MODEL_NAME,
                Path(item.text()),
            )
            item.setForeground(_VALID_COLOR if found else _INVALID_COLOR)

    def _notify_status_update(self) -> None:
        if self._status_update_callback is not None:
            self._status_update_callback()

    def _get_directories(self) -> list[Path]:
        return [
            Path(self._directories_list.item(index).text())
            for index in range(self._directories_list.count())
        ]
