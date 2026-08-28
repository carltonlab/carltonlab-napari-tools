from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

from qtpy.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from carltonlab_napari_tools._shared_widgets import get_directory
from carltonlab_napari_tools.foci_count_widgets._plot_manager import (
    generate_foci_count_plots,
)
from carltonlab_napari_tools.general_widgets._project_list_widget import (
    CLTProjectListWidget,
)

if TYPE_CHECKING:
    from napari.viewer import ViewerModel


class CLTGeneratePlotsWidget(QWidget):
    def __init__(
        self,
        napari_viewer: "ViewerModel",
        parent: QWidget,
        project_list_widget: CLTProjectListWidget,
        status_update_callback: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(parent)

        self._napari_viewer = napari_viewer
        self._project_list_widget = project_list_widget
        self._status_update_callback = status_update_callback
        self._output_directory: Path | None = None

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(layout)

        title_label = QLabel("CLT Generate Plots")
        title_label.setStyleSheet("font-weight: bold; font-size: 20px;")
        layout.addWidget(title_label)

        path_container = QWidget()
        path_layout = QHBoxLayout()
        path_layout.setContentsMargins(0, 0, 0, 0)
        path_container.setLayout(path_layout)

        path_label = QLabel("Combined plot directory")
        path_label.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Preferred,
        )
        path_layout.addWidget(path_label)

        self._output_path_line_edit = QLineEdit()
        self._output_path_line_edit.setReadOnly(True)
        self._output_path_line_edit.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Preferred,
        )
        path_layout.addWidget(self._output_path_line_edit)

        browse_button = QPushButton("Browse")
        browse_button.clicked.connect(self._browse_button_pressed)
        path_layout.addWidget(browse_button)

        layout.addWidget(path_container)

        generate_button = QPushButton("Generate plots")
        generate_button.clicked.connect(self._generate_plots_button_pressed)
        layout.addWidget(generate_button)
        layout.addStretch()

    def _browse_button_pressed(self) -> None:
        selected_directory = get_directory(
            self,
            caption="Select combined plot directory",
        )
        if selected_directory is None:
            return

        self._output_directory = Path(selected_directory)
        self._output_path_line_edit.setText(str(self._output_directory))

    def _generate_plots_button_pressed(self) -> None:
        if self._output_directory is None:
            return

        generate_foci_count_plots(
            self._project_list_widget.get_project_paths(),
            self._output_directory,
        )
        if self._status_update_callback is not None:
            self._status_update_callback()
