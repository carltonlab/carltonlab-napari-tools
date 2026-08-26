from qtpy.QtCore import Qt
from qtpy.QtWidgets import (
    QLabel,
    QListWidget,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from carltonlab_napari_tools._shared_widgets import FrameSeparator
from carltonlab_napari_tools.general_widgets._project_list_widget import (
    CLTProjectListWidget,
)


class CLTPickNucleiWidget(QWidget):
    def __init__(
        self,
        parent: QWidget,
        project_list_widget: CLTProjectListWidget,
    ) -> None:
        super().__init__(parent)

        self._parent_widget = parent
        self._project_list_widget = project_list_widget

        self._layout = QVBoxLayout()
        self._layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(self._layout)

        self._title_label = QLabel("CLT Pick Points")
        self._title_label.setStyleSheet("font-weight: bold; font-size: 20px")
        self._title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._layout.addWidget(self._title_label)

        self._layout.addWidget(FrameSeparator(parent=self))

        self._regions_title_label = QLabel("Regions")
        self._regions_title_label.setStyleSheet("font-weight: bold")
        self._layout.addWidget(self._regions_title_label)

        self._regions_list_widget = QListWidget()
        self._regions_list_widget.setUniformItemSizes(True)
        self._regions_list_widget.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Preferred,
        )
        self._regions_list_widget.setMaximumHeight(7 * 24 + 2)
        self._layout.addWidget(self._regions_list_widget)

        self._layout.addWidget(FrameSeparator(parent=self))

        self._save_nuclei_features_button = QPushButton("Save nuclei features")
        self._layout.addWidget(self._save_nuclei_features_button)
