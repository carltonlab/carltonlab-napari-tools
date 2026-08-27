from pathlib import Path
from typing import TYPE_CHECKING

from napari.layers import Image, Points
from qtpy.QtCore import Qt
from qtpy.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)
from superqt import QToggleSwitch

from carltonlab_napari_tools._shared_widgets import FrameSeparator
from carltonlab_napari_tools.foci_count_widgets._sbs_flags_manager import (
    SBSFlag,
    SBSFlagsManager,
)
from carltonlab_napari_tools.general_widgets._project_list_widget import (
    CLTProjectListWidget,
)

if TYPE_CHECKING:
    from napari.components import ViewerModel


class CLTScoreSBSRow(QWidget):
    def __init__(
        self,
        sbs_name: str,
        foci_count: int,
        *,
        blind: bool = False,
        scored: bool = False,
        flags: list[SBSFlag | str] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)

        layout = QHBoxLayout()
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(4)
        self.setLayout(layout)

        self.showing_label = QLabel("Blind" if blind else sbs_name)
        self.showing_label.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Preferred,
        )
        layout.addWidget(self.showing_label)

        separator_label = QLabel(" --- ")
        separator_label.setSizePolicy(
            QSizePolicy.Policy.Maximum,
            QSizePolicy.Policy.Preferred,
        )
        layout.addWidget(separator_label)

        foci_label = QLabel(f"foci: {foci_count}")
        foci_label.setSizePolicy(
            QSizePolicy.Policy.Maximum,
            QSizePolicy.Policy.Preferred,
        )
        layout.addWidget(foci_label)

        flagged_values = {
            flag.value if isinstance(flag, SBSFlag) else flag
            for flag in flags or []
        }
        flagged = flagged_values.intersection(
            {SBSFlag.IGNORE.value, SBSFlag.APOPTOTIC.value}
        )

        if flagged:
            self.showing_label.setStyleSheet("color: #A80000;")
        elif scored:
            self.showing_label.setStyleSheet("color: #29BA00;")
        else:
            self.showing_label.setStyleSheet("color: black;")


class CLTScoreNucleiWidget(QWidget):
    def __init__(
        self,
        napari_viewer: "ViewerModel",
        parent: QWidget,
        project_list_widget: CLTProjectListWidget,
    ) -> None:
        super().__init__(parent)

        self._napari_viewer = napari_viewer
        self._project_list_widget = project_list_widget

        self._sbs_image: Image | None = None
        self._foci_points: Points | None = None
        self._sbs_flags_managers: dict[Path, SBSFlagsManager] = {}

        self._layout = QVBoxLayout()
        self._layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(self._layout)

        self._title_label = QLabel("CLT Score Nuclei")
        self._title_label.setStyleSheet("font-weight: bold; font-size: 20px")
        self._title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._layout.addWidget(self._title_label)

        self._layout.addWidget(FrameSeparator(parent=self))

        self._control_widget = QWidget()
        self._control_layout = QVBoxLayout()
        self._control_layout.setContentsMargins(0, 0, 0, 0)
        self._control_widget.setLayout(self._control_layout)
        self._layout.addWidget(self._control_widget)

        self._mode_widget = QWidget()
        self._mode_layout = QHBoxLayout()
        self._mode_layout.setContentsMargins(0, 0, 0, 0)
        self._mode_widget.setLayout(self._mode_layout)

        self._mode_label = QLabel("Score projects mode:")
        self._mode_label.setSizePolicy(
            QSizePolicy.Policy.Maximum,
            QSizePolicy.Policy.Preferred,
        )
        self._mode_layout.addWidget(self._mode_label)

        self._mode_combo = QComboBox()
        self._mode_combo.addItems(["All", "Single"])
        self._mode_combo.setSizePolicy(
            QSizePolicy.Policy.Maximum,
            QSizePolicy.Policy.Preferred,
        )
        self._mode_layout.addWidget(self._mode_combo)
        self._mode_layout.addStretch()
        self._control_layout.addWidget(self._mode_widget)

        self._sbs_status_widget = QWidget()
        self._sbs_status_layout = QHBoxLayout()
        self._sbs_status_layout.setContentsMargins(0, 0, 0, 0)
        self._sbs_status_widget.setLayout(self._sbs_status_layout)

        self._sbs_status_label = QLabel("SBS not cut")
        self._sbs_status_label.setSizePolicy(
            QSizePolicy.Policy.Maximum,
            QSizePolicy.Policy.Preferred,
        )
        self._sbs_status_label.setStyleSheet(
            "color: gray; font-style: italic;"
        )
        self._sbs_status_layout.addWidget(self._sbs_status_label)

        self._cut_sbs_button = QPushButton("Cut project(s) SBS")
        self._cut_sbs_button.setSizePolicy(
            QSizePolicy.Policy.Maximum,
            QSizePolicy.Policy.Preferred,
        )
        self._sbs_status_layout.addWidget(self._cut_sbs_button)
        self._sbs_status_layout.addStretch()
        self._control_layout.addWidget(self._sbs_status_widget)

        self._blind_nuclei_checkbox = QCheckBox("Blind nuclei")
        self._shuffle_nuclei_checkbox = QCheckBox("Shuffle nuclei")
        self._control_layout.addWidget(self._blind_nuclei_checkbox)
        self._control_layout.addWidget(self._shuffle_nuclei_checkbox)

        self._peek_widget = QWidget()
        self._peek_layout = QHBoxLayout()
        self._peek_layout.setContentsMargins(0, 0, 0, 0)
        self._peek_widget.setLayout(self._peek_layout)

        self._peek_label = QLabel("Peek nuclei")
        self._peek_label.setSizePolicy(
            QSizePolicy.Policy.Maximum,
            QSizePolicy.Policy.Preferred,
        )
        self._peek_layout.addWidget(self._peek_label)

        self._peek_toggle = QToggleSwitch()
        self._peek_layout.addWidget(self._peek_toggle)
        self._peek_layout.addStretch()
        self._control_layout.addWidget(self._peek_widget)

        self._peek_details_widget = QWidget()
        self._peek_details_layout = QVBoxLayout()
        self._peek_details_layout.setContentsMargins(0, 0, 0, 0)
        self._peek_details_widget.setLayout(self._peek_details_layout)
        self._peek_details_widget.setVisible(False)

        self._sbs_name_label = QLabel("SBS name:")
        self._flags_label = QLabel("Flags:")
        self._region_label = QLabel("Region:")
        for label in (
            self._sbs_name_label,
            self._flags_label,
            self._region_label,
        ):
            label.setSizePolicy(
                QSizePolicy.Policy.Maximum,
                QSizePolicy.Policy.Preferred,
            )
        self._peek_details_layout.addWidget(self._sbs_name_label)
        self._peek_details_layout.addWidget(self._flags_label)
        self._peek_details_layout.addWidget(self._region_label)
        self._control_layout.addWidget(self._peek_details_widget)

        self._layout.addWidget(FrameSeparator(parent=self))

        self._sbs_list_widget = QListWidget()
        self._layout.addWidget(self._sbs_list_widget)

        sample_rows = (
            CLTScoreSBSRow("SBS 1", 0),
            CLTScoreSBSRow("SBS 2", 12, scored=True),
            CLTScoreSBSRow(
                "SBS 3",
                4,
                flags=[SBSFlag.IGNORE],
            ),
        )

        for row_widget in sample_rows:
            list_item = QListWidgetItem()
            list_item.setSizeHint(row_widget.sizeHint())
            self._sbs_list_widget.addItem(list_item)
            self._sbs_list_widget.setItemWidget(list_item, row_widget)

    def _get_flags_manager(
        self,
        project_path: Path,
    ) -> SBSFlagsManager:
        flags_manager = self._sbs_flags_managers.get(project_path)

        if flags_manager is None:
            flags_manager = SBSFlagsManager(project_path)
            self._sbs_flags_managers[project_path] = flags_manager

        return flags_manager
