from dataclasses import dataclass
from pathlib import Path
from random import shuffle
from typing import TYPE_CHECKING

import pandas as pd
import tifffile
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
    QSpinBox,
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
    STITCHED_IMAGE_DIR_NAME,
    TILES_DIR_NAME,
)
from carltonlab_napari_tools._shared_widgets import FrameSeparator
from carltonlab_napari_tools._tile_utils import (
    TileBoundingBox,
    find_tile_for_sbs,
    load_tile_bounding_boxes,
    load_tile_contrasts,
)
from carltonlab_napari_tools._utils import get_project_stitched_image_path
from carltonlab_napari_tools.foci_count_widgets._sbs_flags_manager import (
    SBSFlag,
    SBSFlagsManager,
)
from carltonlab_napari_tools.general_widgets._project_list_widget import (
    CLTProjectListWidget,
)
from carltonlab_napari_tools.image_processing import crop_sbs_data
from carltonlab_napari_tools.image_resolver import resolve_lazy_image_data

if TYPE_CHECKING:
    from napari.components import ViewerModel


@dataclass
class ProjectScoringData:
    project_path: Path
    project_name: str
    features: pd.DataFrame
    flags_manager: SBSFlagsManager
    tile_bounding_boxes: dict[Path, TileBoundingBox]

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


@dataclass
class ScoreSBSEntry:
    project_path: Path
    sbs_number: int
    foci_count: int | None
    scored: bool
    flags: list[str]


class CLTScoreSBSRow(QWidget):
    def __init__(
        self,
        sbs_name: str,
        foci_count: int,
        *,
        scored: bool = False,
        flags: list[SBSFlag | str] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)

        layout = QHBoxLayout()
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(4)
        self.setLayout(layout)

        self.showing_label = QLabel(sbs_name)
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


class CLTScoreSBSListItem(QListWidgetItem):
    def __init__(
        self,
        entry: ScoreSBSEntry,
        parent: QListWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.entry = entry


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

        self._sbs_images: list[Image] = []
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
        self._cut_sbs_button.clicked.connect(self._on_cut_sbs_button_pressed)
        self._sbs_status_layout.addWidget(self._cut_sbs_button)
        self._sbs_status_layout.addStretch()
        self._control_layout.addWidget(self._sbs_status_widget)

        self._blind_nuclei_checkbox = QCheckBox("Blind nuclei")
        self._blind_nuclei_checkbox.setChecked(True)
        self._blind_nuclei_checkbox.toggled.connect(
            self._scoring_options_changed
        )

        self._shuffle_nuclei_checkbox = QCheckBox("Shuffle nuclei")
        self._shuffle_nuclei_checkbox.setChecked(True)
        self._shuffle_nuclei_checkbox.toggled.connect(
            self._scoring_options_changed
        )

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
        self._peek_toggle.toggled.connect(self._on_peek_toggled)
        self._peek_layout.addWidget(self._peek_toggle)
        self._peek_layout.addStretch()
        self._control_layout.addWidget(self._peek_widget)

        self._peek_details_widget = QWidget()
        self._peek_details_layout = QVBoxLayout()
        self._peek_details_layout.setContentsMargins(12, 0, 0, 0)
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
            label.setStyleSheet("font-style: italic;")
        self._peek_details_layout.addWidget(self._sbs_name_label)
        self._peek_details_layout.addWidget(self._flags_label)
        self._peek_details_layout.addWidget(self._region_label)
        self._control_layout.addWidget(self._peek_details_widget)

        self._layout.addWidget(FrameSeparator(parent=self))

        self._sbs_list_title = QLabel("SBS list")
        self._sbs_list_title.setStyleSheet("font-weight: bold;")
        self._layout.addWidget(self._sbs_list_title)

        self._sbs_dimensions_widget = QWidget()
        self._sbs_dimensions_layout = QHBoxLayout()
        self._sbs_dimensions_layout.setContentsMargins(0, 0, 0, 0)
        self._sbs_dimensions_widget.setLayout(self._sbs_dimensions_layout)

        for label_text in ("W:", "H:", "Z:"):
            label = QLabel(label_text)
            label.setSizePolicy(
                QSizePolicy.Policy.Maximum,
                QSizePolicy.Policy.Preferred,
            )
            self._sbs_dimensions_layout.addWidget(label)
            if label_text == "W:":
                self._width_spinbox = QSpinBox()
                self._width_spinbox.setRange(1, 1_000_000)
                self._width_spinbox.setValue(100)
                self._width_spinbox.setSizePolicy(
                    QSizePolicy.Policy.Maximum,
                    QSizePolicy.Policy.Preferred,
                )
                self._sbs_dimensions_layout.addWidget(self._width_spinbox)
            elif label_text == "H:":
                self._height_spinbox = QSpinBox()
                self._height_spinbox.setRange(1, 1_000_000)
                self._height_spinbox.setValue(100)
                self._height_spinbox.setSizePolicy(
                    QSizePolicy.Policy.Maximum,
                    QSizePolicy.Policy.Preferred,
                )
                self._sbs_dimensions_layout.addWidget(self._height_spinbox)
            else:
                self._z_sections_spinbox = QSpinBox()
                self._z_sections_spinbox.setRange(1, 1_000_000)
                self._z_sections_spinbox.setValue(27)
                self._z_sections_spinbox.setSizePolicy(
                    QSizePolicy.Policy.Maximum,
                    QSizePolicy.Policy.Preferred,
                )
                self._sbs_dimensions_layout.addWidget(self._z_sections_spinbox)

        self._apply_dimensions_button = QPushButton("Apply")
        self._apply_dimensions_button.setSizePolicy(
            QSizePolicy.Policy.Maximum,
            QSizePolicy.Policy.Preferred,
        )
        self._sbs_dimensions_layout.addWidget(self._apply_dimensions_button)
        self._sbs_dimensions_layout.addStretch()
        self._layout.addWidget(self._sbs_dimensions_widget)

        self._sbs_list_widget = QListWidget()
        self._layout.addWidget(self._sbs_list_widget)
        self._sbs_list_widget.currentItemChanged.connect(
            self._sbs_selection_changed
        )
        self._mode_combo.currentTextChanged.connect(
            self._load_project_scoring_data
        )
        self._project_list_widget.currentItemChanged.connect(
            self._project_selection_changed
        )

        self._sbs_flags_widget = QWidget()
        self._sbs_flags_layout = QVBoxLayout()
        self._sbs_flags_layout.setContentsMargins(0, 0, 0, 0)
        self._sbs_flags_widget.setLayout(self._sbs_flags_layout)

        self._flags_summary_label = QLabel("Flags: None")
        self._flags_summary_label.setSizePolicy(
            QSizePolicy.Policy.Maximum,
            QSizePolicy.Policy.Preferred,
        )
        self._sbs_flags_layout.addWidget(self._flags_summary_label)

        self._add_flags_widget = QWidget()
        self._add_flags_layout = QHBoxLayout()
        self._add_flags_layout.setContentsMargins(0, 0, 0, 0)
        self._add_flags_widget.setLayout(self._add_flags_layout)
        self._add_flags_button = QPushButton("Add flags")
        self._add_flags_button.setSizePolicy(
            QSizePolicy.Policy.Maximum,
            QSizePolicy.Policy.Preferred,
        )
        self._add_flags_combo = QComboBox()
        self._add_flags_combo.addItems(flag.value for flag in SBSFlag)
        self._add_flags_combo.setSizePolicy(
            QSizePolicy.Policy.Maximum,
            QSizePolicy.Policy.Preferred,
        )
        self._add_flags_layout.addWidget(self._add_flags_button)
        self._add_flags_layout.addWidget(self._add_flags_combo)
        self._add_flags_layout.addStretch()
        self._sbs_flags_layout.addWidget(self._add_flags_widget)

        self._remove_flags_widget = QWidget()
        self._remove_flags_layout = QHBoxLayout()
        self._remove_flags_layout.setContentsMargins(0, 0, 0, 0)
        self._remove_flags_widget.setLayout(self._remove_flags_layout)
        self._remove_flags_button = QPushButton("Remove flags")
        self._remove_flags_button.setSizePolicy(
            QSizePolicy.Policy.Maximum,
            QSizePolicy.Policy.Preferred,
        )
        self._remove_flags_combo = QComboBox()
        self._remove_flags_combo.setSizePolicy(
            QSizePolicy.Policy.Maximum,
            QSizePolicy.Policy.Preferred,
        )
        flags_combo_width = max(
            self._add_flags_combo.sizeHint().width(),
            self._remove_flags_combo.sizeHint().width(),
        )
        self._add_flags_combo.setFixedWidth(flags_combo_width)
        self._remove_flags_combo.setFixedWidth(flags_combo_width)
        flags_button_width = max(
            self._add_flags_button.sizeHint().width(),
            self._remove_flags_button.sizeHint().width(),
        )
        self._add_flags_button.setFixedWidth(flags_button_width)
        self._remove_flags_button.setFixedWidth(flags_button_width)
        self._remove_flags_layout.addWidget(self._remove_flags_button)
        self._remove_flags_layout.addWidget(self._remove_flags_combo)
        self._remove_flags_layout.addStretch()
        self._sbs_flags_layout.addWidget(self._remove_flags_widget)
        self._layout.addWidget(self._sbs_flags_widget)

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

            stitched_directory = project_path / STITCHED_IMAGE_DIR_NAME
            stitched_paths = sorted(stitched_directory.glob("*.ome.zarr"))
            tile_bounding_boxes = (
                load_tile_bounding_boxes(
                    stitched_paths[0],
                    project_path / TILES_DIR_NAME,
                )
                if stitched_paths
                else {}
            )

            self._project_scoring_data[project_path] = ProjectScoringData(
                project_path=project_path,
                project_name=project_path.name.removesuffix(
                    CLSP_PROJECT_SUFFIX
                ),
                features=features,
                flags_manager=flags_manager,
                tile_bounding_boxes=tile_bounding_boxes,
            )

        has_missing_sbs = False
        for project_data in self._project_scoring_data.values():
            missing_sbs_paths = project_data.get_sbs_images_needing_crop()
            if missing_sbs_paths:
                has_missing_sbs = True

        self._cut_sbs_button.setEnabled(has_missing_sbs)
        self._update_sbs_list()

    def _sbs_selection_changed(
        self,
        current_item: QListWidgetItem | None,
        _previous_item: QListWidgetItem | None,
    ) -> None:
        self._napari_viewer.layers.clear()
        self._sbs_images = []
        self._foci_points = None

        if current_item is None:
            return

        if not isinstance(current_item, CLTScoreSBSListItem):
            return

        project_path = current_item.entry.project_path
        sbs_number = current_item.entry.sbs_number
        project_data = self._project_scoring_data.get(project_path)
        if project_data is None:
            return

        if self._peek_toggle.isChecked():
            self._update_peek_details()

        sbs_path = project_data.get_sbs_image_path(f"sbs{sbs_number}")
        if sbs_path is None:
            return

        image_data = tifffile.imread(sbs_path)
        opened_images = self._napari_viewer.add_image(
            image_data,
            channel_axis=0,
        )
        self._sbs_images = (
            opened_images
            if isinstance(opened_images, list)
            else [opened_images]
        )

        feature_matches = project_data.features[
            project_data.features["sbs_number"] == sbs_number
        ]
        if feature_matches.empty:
            return

        tile_path = find_tile_for_sbs(
            feature_matches.iloc[0].to_dict(),
            project_data.tile_bounding_boxes,
        )
        if tile_path is None:
            return

        tile_contrasts = load_tile_contrasts(tile_path)
        for channel_index, image_layer in enumerate(self._sbs_images):
            contrast_limits = tile_contrasts.get(channel_index)
            if contrast_limits is not None:
                image_layer.contrast_limits = contrast_limits

    def _on_peek_toggled(self, checked: bool) -> None:
        if not checked:
            self._peek_details_widget.setVisible(False)
            return

        self._update_peek_details()

    def _update_peek_details(self) -> None:
        current_item = self._sbs_list_widget.currentItem()
        if not isinstance(current_item, CLTScoreSBSListItem):
            self._peek_details_widget.setVisible(False)
            return

        entry = current_item.entry
        project_data = self._project_scoring_data.get(entry.project_path)
        if project_data is None:
            self._peek_details_widget.setVisible(False)
            return

        matching_features = project_data.features[
            project_data.features["sbs_number"] == entry.sbs_number
        ]
        if matching_features.empty:
            self._peek_details_widget.setVisible(False)
            return

        feature = matching_features.iloc[0]
        sbs_name = f"sbs{entry.sbs_number}"
        sbs_path = project_data.get_sbs_image_path(sbs_name)
        sbs_filename = sbs_path.name if sbs_path is not None else "Not cut"
        flags = project_data.flags_manager.get_flags(sbs_name)
        flags_text = ", ".join(flags) if flags else "None"

        region = feature.get("region")
        region_text = "None" if pd.isna(region) else str(region)

        self._sbs_name_label.setText(f"SBS name: {sbs_filename}")
        self._flags_label.setText(f"Flags: {flags_text}")
        self._region_label.setText(f"Region: {region_text}")
        self._peek_details_widget.setVisible(True)

    def _project_selection_changed(self, *_args: object) -> None:
        if self._mode_combo.currentText() == "Single":
            self._load_project_scoring_data()

    def _scoring_options_changed(self, _state: bool) -> None:
        self._update_sbs_list()

    def _on_cut_sbs_button_pressed(self) -> None:
        for project_data in self._project_scoring_data.values():
            self._cut_project_sbs(project_data)

        self._load_project_scoring_data()

    def _cut_project_sbs(
        self,
        project_data: ProjectScoringData,
    ) -> None:
        stitched_path = get_project_stitched_image_path(
            project_data.project_path
        )
        if stitched_path is None:
            return

        stitched_data = resolve_lazy_image_data(stitched_path)
        if stitched_data is None:
            return

        flags_changed = False
        cut_sbs_directory = (
            project_data.project_path
            / PROJECT_FILE_DIR_NAME
            / PICK_NUCLEI_DIR_NAME
            / CUT_SBS_DIR_NAME
        )
        cut_sbs_directory.mkdir(parents=True, exist_ok=True)

        for feature in project_data.features.to_dict(orient="records"):
            sbs_number = int(feature["sbs_number"])
            sbs_name = f"sbs{sbs_number}"
            sbs_flags = project_data.flags_manager.get_flags(sbs_name)
            needs_recalculation = (
                SBSFlag.COORD_RECALC_NEEDED.value in sbs_flags
            )
            output_path = cut_sbs_directory / (
                f"{project_data.project_name}_{sbs_name}"
                f"{SBS_FILE_NAME_EXTENSION}"
            )

            if output_path.is_file() and not needs_recalculation:
                continue

            cropped_data = crop_sbs_data(stitched_data, feature)
            if cropped_data is None:
                continue

            try:
                tifffile.imwrite(
                    output_path,
                    cropped_data.compute().values,
                )
            except (OSError, ValueError):
                continue

            if needs_recalculation:
                project_data.flags_manager.remove_flag(
                    sbs_name,
                    SBSFlag.COORD_RECALC_NEEDED,
                )
                flags_changed = True

        if flags_changed:
            project_data.flags_manager.save()

    def _update_sbs_list(self) -> None:
        self._sbs_list_widget.clear()

        sbs_entries: list[ScoreSBSEntry] = []

        for project_path, project_data in self._project_scoring_data.items():
            for feature in project_data.features.to_dict(orient="records"):
                sbs_number = int(feature["sbs_number"])
                foci_value = feature["scored_foci_number"]
                foci_count = None if pd.isna(foci_value) else int(foci_value)
                flag_key = f"sbs{sbs_number}"
                flags = project_data.flags_manager.get_flags(flag_key)

                sbs_entries.append(
                    ScoreSBSEntry(
                        project_path=project_path,
                        sbs_number=sbs_number,
                        foci_count=foci_count,
                        scored=foci_count is not None,
                        flags=flags,
                    )
                )

        if self._shuffle_nuclei_checkbox.isChecked():
            shuffle(sbs_entries)

        blind = self._blind_nuclei_checkbox.isChecked()

        for display_index, entry in enumerate(sbs_entries, start=1):
            sbs_name = (
                f"Blind {display_index}"
                if blind
                else f"sbs{entry.sbs_number} - {entry.project_path.name}"
            )

            row_widget = CLTScoreSBSRow(
                sbs_name=sbs_name,
                foci_count=entry.foci_count,
                scored=entry.scored,
                flags=entry.flags,
            )
            list_item = CLTScoreSBSListItem(entry)
            list_item.setSizeHint(row_widget.sizeHint())
            self._sbs_list_widget.addItem(list_item)
            self._sbs_list_widget.setItemWidget(list_item, row_widget)
