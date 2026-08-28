from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import pandas as pd
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

from carltonlab_napari_tools._shared_variables import (
    CLSP_PROJECT_SUFFIX,
    CUT_SBS_DIR_NAME,
    NUCLEI_POINTS_FEATURES_TABLE_FILE_NAME,
    PICK_NUCLEI_DIR_NAME,
    PROJECT_FILE_DIR_NAME,
    SBS_FILE_NAME_EXTENSION,
)
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


@dataclass
class ProjectScoringData:
    project_path: Path
    project_name: str
    features: pd.DataFrame
    flags_manager: SBSFlagsManager
    tile_bounding_boxes: dict[int, dict[str, int]]

    def get_sbs_image_path(self, sbs_name: str) -> Path | None:
        if not sbs_name.startswith("sbs"):
            return None

        cut_sbs_directory = (
            self.project_path
            / PROJECT_FILE_DIR_NAME
            / PICK_NUCLEI_DIR_NAME
            / CUT_SBS_DIR_NAME
        )
        sbs_path = cut_sbs_directory / (
            f"{self.project_name}_{sbs_name}{SBS_FILE_NAME_EXTENSION}"
        )

        return sbs_path if sbs_path.is_file() else None

    def get_sbs_images_needing_crop(self) -> list[Path]:
        cut_sbs_directory = (
            self.project_path
            / PROJECT_FILE_DIR_NAME
            / PICK_NUCLEI_DIR_NAME
            / CUT_SBS_DIR_NAME
        )
        missing_sbs_paths: list[Path] = []

        for sbs_number in self.features["sbs_number"]:
            sbs_name = f"sbs{int(sbs_number)}"
            sbs_path = cut_sbs_directory / (
                f"{self.project_name}_{sbs_name}{SBS_FILE_NAME_EXTENSION}"
            )
            sbs_flags = self.flags_manager.get_flags(sbs_name)
            needs_coordinate_recalculation = (
                SBSFlag.COORD_RECALC_NEEDED.value in sbs_flags
            )
            if not sbs_path.is_file() or needs_coordinate_recalculation:
                missing_sbs_paths.append(sbs_path)

        return missing_sbs_paths


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
        self._project_scoring_data: dict[Path, ProjectScoringData] = {}

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
        self._mode_combo.currentTextChanged.connect(
            self._load_project_scoring_data
        )
        self._project_list_widget.currentItemChanged.connect(
            self._project_selection_changed
        )
        self._load_project_scoring_data()

    def _get_scoring_project_paths(self) -> list[Path]:
        if self._mode_combo.currentText() == "Single":
            current_project_path = (
                self._project_list_widget.get_current_project_path()
            )
            return (
                [] if current_project_path is None else [current_project_path]
            )

        return self._project_list_widget.get_project_paths()

    @staticmethod
    def _resolve_project_path(starting_path: Path) -> Path | None:
        if starting_path.name.endswith(CLSP_PROJECT_SUFFIX):
            return starting_path

        project_paths = [
            path
            for path in starting_path.iterdir()
            if path.is_dir() and path.name.endswith(CLSP_PROJECT_SUFFIX)
        ]
        return project_paths[0] if project_paths else None

    def _load_project_scoring_data(self, *_args: object) -> None:
        self._project_scoring_data.clear()

        for starting_path in self._get_scoring_project_paths():
            project_path = self._resolve_project_path(starting_path)
            if project_path is None:
                continue

            features_path = (
                project_path
                / PROJECT_FILE_DIR_NAME
                / PICK_NUCLEI_DIR_NAME
                / NUCLEI_POINTS_FEATURES_TABLE_FILE_NAME
            )
            if not features_path.is_file():
                continue

            features = pd.read_csv(features_path)
            flags_manager = SBSFlagsManager(project_path)
            flags_manager.load()
            self._project_scoring_data[project_path] = ProjectScoringData(
                project_path=project_path,
                project_name=project_path.name.removesuffix(
                    CLSP_PROJECT_SUFFIX
                ),
                features=features,
                flags_manager=flags_manager,
                tile_bounding_boxes={},
            )

        has_missing_sbs = False
        for project_data in self._project_scoring_data.values():
            missing_sbs_paths = project_data.get_sbs_images_needing_crop()
            if missing_sbs_paths:
                has_missing_sbs = True

        self._cut_sbs_button.setEnabled(has_missing_sbs)
        self._update_sbs_list()

    def _project_selection_changed(self, *_args: object) -> None:
        if self._mode_combo.currentText() == "Single":
            self._load_project_scoring_data()

    def _update_sbs_list(self) -> None:
        self._sbs_list_widget.clear()

        for project_path, project_data in self._project_scoring_data.items():
            for feature in project_data.features.to_dict(orient="records"):
                sbs_number = int(feature["sbs_number"])
                foci_value = feature["scored_foci_number"]
                foci_count = None if pd.isna(foci_value) else int(foci_value)
                sbs_name = f"sbs{sbs_number} - {project_path.name}"
                flag_key = f"sbs{sbs_number}"

                row_widget = CLTScoreSBSRow(
                    sbs_name=sbs_name,
                    foci_count=foci_count,
                    scored=foci_count is not None,
                    flags=project_data.flags_manager.get_flags(flag_key),
                )
                list_item = QListWidgetItem()
                list_item.setData(
                    Qt.ItemDataRole.UserRole,
                    (project_path, sbs_number),
                )
                list_item.setSizeHint(row_widget.sizeHint())
                self._sbs_list_widget.addItem(list_item)
                self._sbs_list_widget.setItemWidget(
                    list_item,
                    row_widget,
                )
