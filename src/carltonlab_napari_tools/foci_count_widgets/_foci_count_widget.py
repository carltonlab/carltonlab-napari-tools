import configparser
from pathlib import Path
from typing import TYPE_CHECKING

from napari.utils.notifications import show_error
from qtpy.QtCore import QSize, Qt, QTimer
from qtpy.QtGui import QIcon
from qtpy.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from carltonlab_napari_tools._multigonad_project import (
    load_multigonad_project,
    save_multigonad_project,
)
from carltonlab_napari_tools._shared_variables import (
    CLSP_PROJECT_SUFFIX,
    MULTIGONAD_FOCI_COUNT_TOOL_FILE_SUFFIX,
    SUPPORTED_STITCH_EXTENSIONS,
)
from carltonlab_napari_tools._shared_widgets import (
    FrameSeparator,
    KeepChannelsWidget,
    ToggleVisibilityButton,
    get_directories,
    get_file,
)
from carltonlab_napari_tools.foci_count_widgets._auto_foci_count_widget import (
    AutoFociCountWidget,
)
from carltonlab_napari_tools.foci_count_widgets._generate_plots_widget import (
    CLTGeneratePlotsWidget,
)
from carltonlab_napari_tools.foci_count_widgets._pick_nuclei_widget import (
    CLTPickNucleiWidget,
)
from carltonlab_napari_tools.foci_count_widgets._plot_manager import (
    is_project_plot_complete,
)
from carltonlab_napari_tools.foci_count_widgets._score_nuclei_widget import (
    CLTScoreNucleiWidget,
)
from carltonlab_napari_tools.foci_count_widgets._stitch_widget import (
    ProjectStatus,
    StitchOmeZarrWidget,
)
from carltonlab_napari_tools.general_widgets._file_saver_widget import (
    CLToggleSavePathWidget,
)
from carltonlab_napari_tools.general_widgets._project_list_widget import (
    CLTProjectListWidget,
)
from carltonlab_napari_tools.general_widgets._set_contrast_widget import (
    CLTSetContrastWidget,
)
from carltonlab_napari_tools.stitched_regions_widgets._stitched_regions_widget import (
    CLTStitchedRegionsWidget,
)

if TYPE_CHECKING:
    import napari
    from napari.components import ViewerModel


BUTTONS_WIDTH = 30
ICONS_DIR = Path(__file__).resolve().parent.parent / "assets" / "icons"
ADD_DIR_ICON = ICONS_DIR / "add_dir.svg"
LOAD_PROJECT_ICON = ICONS_DIR / "file_settings.svg"
REMOVE_ICON = ICONS_DIR / "remove.svg"


class IntegrationProjectRow(QWidget):
    _status_button_stylesheet = (
        "QPushButton {"
        "border: 1px solid black;"
        "border-radius: 4px;"
        "background-color: white;"
        "color: black;"
        "font-weight: bold;"
        "}"
    )

    def __init__(
        self,
        display_name: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)

        self._layout = QHBoxLayout()
        self._layout.setContentsMargins(4, 0, 4, 0)
        self._layout.setSpacing(4)
        self.setLayout(self._layout)

        self._name_label = QLabel(display_name)
        self._name_label.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Preferred,
        )
        self._layout.addWidget(self._name_label)

        self._status_container = QWidget()
        self._status_container.setStyleSheet("background-color: transparent;")
        self._status_container_layout = QHBoxLayout()
        self._status_container_layout.setContentsMargins(0, 0, 0, 0)
        self._status_container_layout.setSpacing(6)
        self._status_container.setLayout(self._status_container_layout)
        self._layout.addWidget(self._status_container)

        self._extraction_button = QPushButton("Ex")
        self._stitching_button = QPushButton("St")
        self._contrast_button = QPushButton("Co")
        self._regions_button = QPushButton("Re")
        self._nuclei_button = QPushButton("Nu")
        self._scoring_button = QPushButton("Sc")
        self._generate_plots_button = QPushButton("GP")

        status_buttons = (
            self._extraction_button,
            self._stitching_button,
            self._contrast_button,
            self._nuclei_button,
            self._scoring_button,
            self._regions_button,
            self._generate_plots_button,
        )

        for button in status_buttons:
            button.setFixedSize(QSize(BUTTONS_WIDTH, BUTTONS_WIDTH))
            button.setStyleSheet(self._status_button_stylesheet)
            self._status_container_layout.addWidget(button)

    def _set_status_button(
        self,
        button: QPushButton,
        text: str,
        color: str,
        tooltip: str,
    ) -> None:
        button.setText(text)
        button.setToolTip(tooltip)
        button.setStyleSheet(
            "QPushButton {"
            "border: 1px solid black;"
            "border-radius: 4px;"
            "background-color: white;"
            f"color: {color};"
            "font-weight: bold;"
            "}"
        )

    def apply_project_status(self, status: ProjectStatus) -> None:
        self._set_status_button(
            self._extraction_button,
            "Ex",
            status.extraction_color,
            status.extraction_tooltip,
        )
        self._set_status_button(
            self._stitching_button,
            status.stitching_text,
            status.stitching_color,
            status.stitching_tooltip,
        )
        self._set_status_button(
            self._contrast_button,
            "Co",
            status.contrast_color,
            status.contrast_tooltip,
        )

    def apply_nuclei_status(self, saved: bool) -> None:
        self._set_status_button(
            self._nuclei_button,
            "Nu",
            "green" if saved else "red",
            (
                "Nuclei points and features saved"
                if saved
                else "Nuclei points and features not saved"
            ),
        )

    def apply_scoring_status(self, complete: bool) -> None:
        self._set_status_button(
            self._scoring_button,
            "Sc",
            "green" if complete else "red",
            (
                "All SBS nuclei scored"
                if complete
                else "SBS nuclei scoring is incomplete"
            ),
        )

    def apply_regions_status(self, complete: bool) -> None:
        self._set_status_button(
            self._regions_button,
            "Re",
            "green" if complete else "red",
            (
                "Nuclei regions assigned"
                if complete
                else "Nuclei regions are incomplete"
            ),
        )

    def apply_plots_status(self, complete: bool) -> None:
        self._set_status_button(
            self._generate_plots_button,
            "GP",
            "green" if complete else "red",
            (
                "Project plots generated"
                if complete
                else "Project plots not generated"
            ),
        )


class ManualFociCountWidget(QWidget):
    def __init__(
        self,
        napari_viewer: "ViewerModel",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)

        self._napari_viewer = napari_viewer

        self._layout = QVBoxLayout()
        self._layout.setContentsMargins(0, 0, 0, 5)
        self.setLayout(self._layout)

        self._title_label = QLabel("CL Count Tool")
        self._title_label.setStyleSheet("font-weight: bold; font-size: 20px")
        self._title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._layout.addWidget(self._title_label)

        self._title_separator = FrameSeparator(parent=self)
        self._layout.addWidget(self._title_separator)

        self._project_directories_container = QWidget()
        self._project_directories_layout = QVBoxLayout()
        self._project_directories_layout.setContentsMargins(0, 0, 0, 0)
        self._project_directories_container.setLayout(
            self._project_directories_layout
        )
        self._project_directories_container.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Preferred,
        )
        self._layout.addWidget(self._project_directories_container)

        self._project_directories_header = QWidget()
        self._project_directories_header_layout = QHBoxLayout()
        self._project_directories_header_layout.setContentsMargins(0, 0, 0, 0)
        self._project_directories_header_layout.setSpacing(6)
        self._project_directories_header.setLayout(
            self._project_directories_header_layout
        )
        self._project_directories_layout.addWidget(
            self._project_directories_header
        )

        self._project_directories_title = QLabel("Project directories")
        self._project_directories_title.setStyleSheet("font-weight: bold")
        self._project_directories_title.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Preferred,
        )
        self._project_directories_header_layout.addWidget(
            self._project_directories_title
        )

        self._add_project_directory_button = QPushButton("")
        self._add_project_directory_button.setIcon(QIcon(str(ADD_DIR_ICON)))
        self._add_project_directory_button.setFixedSize(
            BUTTONS_WIDTH,
            BUTTONS_WIDTH,
        )
        self._add_project_directory_button.setIconSize(
            QSize(BUTTONS_WIDTH - 6, BUTTONS_WIDTH - 6)
        )
        self._add_project_directory_button.setToolTip("Add project directory")
        self._project_directories_header_layout.addWidget(
            self._add_project_directory_button
        )

        self._add_multigonad_config_button = QPushButton("")
        self._add_multigonad_config_button.setIcon(
            QIcon(str(LOAD_PROJECT_ICON))
        )
        self._add_multigonad_config_button.setFixedSize(
            BUTTONS_WIDTH,
            BUTTONS_WIDTH,
        )
        self._add_multigonad_config_button.setIconSize(
            QSize(BUTTONS_WIDTH - 6, BUTTONS_WIDTH - 6)
        )
        self._add_multigonad_config_button.setToolTip(
            "Add multigonad config file"
        )
        self._project_directories_header_layout.addWidget(
            self._add_multigonad_config_button
        )

        self._remove_project_directory_button = QPushButton("")
        self._remove_project_directory_button.setIcon(QIcon(str(REMOVE_ICON)))
        self._remove_project_directory_button.setFixedSize(
            BUTTONS_WIDTH,
            BUTTONS_WIDTH,
        )
        self._remove_project_directory_button.setIconSize(
            QSize(BUTTONS_WIDTH - 6, BUTTONS_WIDTH - 6)
        )
        self._remove_project_directory_button.setToolTip(
            "Remove selected project directories"
        )
        self._project_directories_header_layout.addWidget(
            self._remove_project_directory_button
        )

        self._project_directories_list = CLTProjectListWidget(
            self,
            row_factory=self._create_project_row,
        )
        self._project_directories_list.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Preferred,
        )
        self._project_directories_layout.addWidget(
            self._project_directories_list
        )

        self._project_directories_visibility_button = ToggleVisibilityButton(
            self._project_directories_list,
            parent=self,
        )
        self._project_directories_header_layout.insertWidget(
            1,
            self._project_directories_visibility_button,
        )

        self._project_directories_separator = FrameSeparator(parent=self)
        self._layout.addWidget(self._project_directories_separator)

        self._keep_channels_widget = KeepChannelsWidget(parent=self)
        self._layout.addWidget(self._keep_channels_widget)

        self._keep_channels_separator = FrameSeparator(parent=self)
        self._layout.addWidget(self._keep_channels_separator)

        self._multigonad_project_saver = CLToggleSavePathWidget(
            self,
            title="Save multigonad project",
            toggled=False,
            allow_overwrite=False,
            force_suffix=MULTIGONAD_FOCI_COUNT_TOOL_FILE_SUFFIX,
        )
        self._layout.addWidget(self._multigonad_project_saver)

        self._multigonad_separator = FrameSeparator(parent=self)
        self._layout.addWidget(self._multigonad_separator)

        self._layout.addSpacing(6)

        self._process_workflow_container = QWidget()
        self._process_workflow_layout = QVBoxLayout()
        self._process_workflow_layout.setContentsMargins(0, 0, 0, 0)
        self._process_workflow_layout.setSpacing(6)
        self._process_workflow_container.setLayout(
            self._process_workflow_layout
        )

        self._process_workflow_title_row = QWidget()
        self._process_workflow_title_layout = QHBoxLayout()
        self._process_workflow_title_layout.setContentsMargins(
            0,
            0,
            0,
            0,
        )
        self._process_workflow_title_row.setLayout(
            self._process_workflow_title_layout
        )

        self._process_workflow_title = QLabel("Process workflow")
        self._process_workflow_title.setStyleSheet("font-weight: bold")
        self._process_workflow_title.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Preferred,
        )
        self._process_workflow_title_layout.addWidget(
            self._process_workflow_title
        )

        self._process_workflow_visibility_button = ToggleVisibilityButton(
            self._process_workflow_container,
            parent=self,
        )
        self._process_workflow_title_layout.addWidget(
            self._process_workflow_visibility_button
        )

        self._layout.addWidget(self._process_workflow_title_row)
        self._layout.addWidget(self._process_workflow_container)

        self._stitch_gonads_button = QPushButton("1.Stitch gonads")
        self._stitch_gonads_button.clicked.connect(self._show_stitch_widget)

        self._set_contrast_button = QPushButton("2.Set contrast")
        self._set_contrast_button.clicked.connect(
            self._show_set_contrast_widget
        )
        self._pick_nuclei_button = QPushButton("3.Pick Nuclei")
        self._pick_nuclei_button.clicked.connect(self._show_pick_nuclei_widget)
        self._score_nuclei_button = QPushButton("4.Score Nuclei")
        self._score_nuclei_button.clicked.connect(
            self._show_score_nuclei_widget
        )
        self._define_regions_button = QPushButton("5.Define Regions")
        self._define_regions_button.clicked.connect(
            self._show_stitched_regions_widget
        )
        self._generate_reports_button = QPushButton("6.Generate Plots")
        self._generate_reports_button.clicked.connect(
            self._show_generate_plots_widget
        )

        self._process_status_labels: dict[str, QLabel] = {}
        self._add_process_button(self._stitch_gonads_button, "stitching")
        self._add_process_button(self._set_contrast_button, "contrast")
        self._add_process_button(self._pick_nuclei_button, "nuclei")
        self._add_process_button(self._score_nuclei_button, "scoring")
        self._add_process_button(self._define_regions_button, "regions")
        self._add_process_button(self._generate_reports_button, "reports")

        self._update_process_status_labels()

        self._layout.addSpacing(6)

        self._layout.addWidget(FrameSeparator(parent=self))

        self._workflow_scroll_area = QScrollArea()
        self._workflow_scroll_area.setWidgetResizable(True)
        self._workflow_scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self._workflow_scroll_area.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )

        self._workflow_widget_container = QWidget()
        self._workflow_widget_layout = QVBoxLayout()
        self._workflow_widget_layout.setContentsMargins(0, 0, 0, 0)
        self._workflow_widget_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._workflow_widget_container.setLayout(self._workflow_widget_layout)
        self._workflow_widget_container.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Preferred,
        )

        self._workflow_scroll_area.setWidget(self._workflow_widget_container)
        self._layout.addWidget(self._workflow_scroll_area, 1)

        self._current_widget: QWidget | None = None

    def detach_shared_controls(self) -> list[QWidget]:
        shared_widgets = [
            self._project_directories_container,
            self._project_directories_separator,
            self._keep_channels_widget,
            self._keep_channels_separator,
            self._multigonad_project_saver,
            self._multigonad_separator,
        ]
        for widget in shared_widgets:
            self._layout.removeWidget(widget)
            widget.setParent(None)
        return shared_widgets

    def _add_process_button(
        self,
        button: QPushButton,
        process_name: str,
    ) -> None:
        row = QWidget()
        row_layout = QHBoxLayout()
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(6)
        row.setLayout(row_layout)

        row_layout.addWidget(button)

        status_label = QLabel("0/0")
        status_label.setFixedWidth(40)
        status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        row_layout.addWidget(status_label)

        self._process_status_labels[process_name] = status_label
        self._process_workflow_layout.addWidget(row)

    def _set_process_status_label(
        self,
        label: QLabel,
        completed: int,
        total: int,
    ) -> None:
        label.setText(f"{completed}/{total}")

        if total > 0 and completed == total:
            label.setStyleSheet("color: green; font-weight: bold;")
        else:
            label.setStyleSheet("color: red;")

    def _update_process_status_labels(self) -> None:
        project_paths = self._project_directories_list.get_project_paths()
        total = len(project_paths)
        requested_channels = self._keep_channels_widget.get_channels()

        stitched_count = sum(
            StitchOmeZarrWidget.get_project_status(
                project_path,
                requested_channels,
            ).stitching_color
            == "green"
            for project_path in project_paths
        )

        self._set_process_status_label(
            self._process_status_labels["stitching"],
            stitched_count,
            total,
        )

        contrast_count = sum(
            StitchOmeZarrWidget.get_project_status(
                project_path,
                requested_channels,
            ).contrast_color
            == "green"
            for project_path in project_paths
        )
        self._set_process_status_label(
            self._process_status_labels["contrast"],
            contrast_count,
            total,
        )

        nuclei_count = sum(
            CLTPickNucleiWidget.is_project_nuclei_complete(project_path)
            for project_path in project_paths
        )
        self._set_process_status_label(
            self._process_status_labels["nuclei"],
            nuclei_count,
            total,
        )

        scoring_count = sum(
            CLTScoreNucleiWidget.is_project_scoring_complete(project_path)
            for project_path in project_paths
        )
        self._set_process_status_label(
            self._process_status_labels["scoring"],
            scoring_count,
            total,
        )

        regions_count = sum(
            CLTStitchedRegionsWidget.is_project_regions_complete(project_path)
            for project_path in project_paths
        )
        self._set_process_status_label(
            self._process_status_labels["regions"],
            regions_count,
            total,
        )
        plots_count = sum(
            is_project_plot_complete(project_path)
            for project_path in project_paths
        )
        self._set_process_status_label(
            self._process_status_labels["reports"],
            plots_count,
            total,
        )

    def _remove_current_widget(self) -> None:
        if self._current_widget is None:
            return

        if isinstance(self._current_widget, CLTScoreNucleiWidget):
            self._napari_viewer.bind_key("u", None)

        self._workflow_widget_layout.removeWidget(self._current_widget)
        self._current_widget.setParent(None)
        self._current_widget.deleteLater()
        self._current_widget = None

    def _set_current_widget(self, widget: QWidget) -> None:
        self._remove_current_widget()
        self._workflow_widget_layout.addWidget(widget)
        self._current_widget = widget

    def _show_stitch_widget(self) -> None:
        stitch_widget = StitchOmeZarrWidget(
            napari_viewer=self._napari_viewer,
            parent=self,
            project_list_widget=self._project_directories_list,
            keep_channels_widget=self._keep_channels_widget,
        )
        self._set_current_widget(stitch_widget)

    def _show_set_contrast_widget(self) -> None:
        contrast_widget = CLTSetContrastWidget(
            napari_viewer=self._napari_viewer,
            parent=self,
            project_list_widget=self._project_directories_list,
            status_update_callback=self._update_process_status_labels,
        )
        self._set_current_widget(contrast_widget)

    def _show_pick_nuclei_widget(self) -> None:
        pick_nuclei_widget = CLTPickNucleiWidget(
            napari_viewer=self._napari_viewer,
            parent=self,
            project_list_widget=self._project_directories_list,
            status_update_callback=self._on_nuclei_saved,
        )
        self._set_current_widget(pick_nuclei_widget)

    def _show_score_nuclei_widget(self) -> None:
        score_nuclei_widget = CLTScoreNucleiWidget(
            napari_viewer=self._napari_viewer,
            parent=self,
            project_list_widget=self._project_directories_list,
            status_update_callback=self._on_scoring_saved,
        )
        self._set_current_widget(score_nuclei_widget)
        self._napari_viewer.bind_key(
            "u",
            self._save_score_nuclei_from_key,
            overwrite=True,
        )

    def _show_stitched_regions_widget(self) -> None:
        stitched_regions_widget = CLTStitchedRegionsWidget(
            napari_viewer=self._napari_viewer,
            parent=self,
            project_list_widget=self._project_directories_list,
            status_update_callback=self._on_regions_saved,
        )
        self._set_current_widget(stitched_regions_widget)

    def _show_generate_plots_widget(self) -> None:
        generate_plots_widget = CLTGeneratePlotsWidget(
            napari_viewer=self._napari_viewer,
            parent=self,
            project_list_widget=self._project_directories_list,
            status_update_callback=self._on_plots_generated,
        )
        self._set_current_widget(generate_plots_widget)

    def _save_score_nuclei_from_key(self, _event=None) -> None:
        if not isinstance(self._current_widget, CLTScoreNucleiWidget):
            return
        if not self._current_widget.isVisible():
            return

        self._current_widget._on_save_foci_points_button_pressed()

    def _on_nuclei_saved(self) -> None:
        self._project_directories_list.refresh_rows()
        self._update_process_status_labels()

    def _on_scoring_saved(self) -> None:
        self._project_directories_list.refresh_rows()
        self._update_process_status_labels()

    def _on_regions_saved(self) -> None:
        self._project_directories_list.refresh_rows()
        self._update_process_status_labels()

    def _on_plots_generated(self) -> None:
        self._project_directories_list.refresh_rows()
        self._update_process_status_labels()

    def _refresh_score_nuclei_widget(self) -> None:
        if isinstance(self._current_widget, CLTScoreNucleiWidget):
            self._current_widget.refresh_project_data()


class CarltonLabCountTool(QWidget):
    # your QWidget.__init__ can optionally request the napari viewer instance
    # use a type annotation of 'napari.viewer.Viewer' for any parameter
    def __init__(self, viewer: "napari.viewer.Viewer"):  # type: ignore
        super().__init__()
        self._napari_viewer = viewer
        self._already_shown = False
        self._parent_widget = None

        self._scroll_timer: QTimer | None = None
        self._scroll_direction: int = 0
        self._scroll_interval_ms = 80
        self._scroll_interval_min_ms = 5
        self._scroll_interval_max_ms = 200

        self._initialize_gui()
        self._install_keybindings()

    def _initialize_gui(self) -> None:
        self._main_layout = QVBoxLayout()
        self.setLayout(self._main_layout)
        self._main_layout.setContentsMargins(25, 2, 2, 25)

        self._main_layout.addSpacing(12)
        speed_separator: QFrame = QFrame(self)
        speed_separator.setFrameShape(QFrame.Shape.HLine)
        speed_separator.setFrameShadow(QFrame.Shadow.Sunken)
        speed_separator.setStyleSheet("background-color: gray;")
        speed_separator.setFixedHeight(2)
        self._main_layout.addWidget(speed_separator)
        self._main_layout.addSpacing(12)

        self._global_scroll_speed_container: QWidget = QWidget()
        self._global_scroll_speed_container_layout: QHBoxLayout = QHBoxLayout()
        self._global_scroll_speed_container_layout.setContentsMargins(
            0, 6, 0, 0
        )
        self._global_scroll_speed_container.setLayout(
            self._global_scroll_speed_container_layout
        )
        self._global_scroll_speed_container.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Maximum,
        )
        self._main_layout.addWidget(self._global_scroll_speed_container)

        self._global_scroll_speed_label: QLabel = QLabel("Scroll speed")
        self._global_scroll_speed_container_layout.addWidget(
            self._global_scroll_speed_label
        )

        self._global_scroll_speed_slider: QSlider = QSlider(
            Qt.Orientation.Horizontal
        )
        self._global_scroll_speed_slider.setRange(
            self._scroll_interval_min_ms, self._scroll_interval_max_ms
        )
        self._global_scroll_speed_slider.setValue(
            self._interval_to_slider_value(self._scroll_interval_ms)
        )
        self._global_scroll_speed_slider.setSingleStep(10)
        self._global_scroll_speed_slider.setPageStep(10)
        self._global_scroll_speed_slider.valueChanged.connect(
            self._scroll_speed_slider_changed
        )
        self._global_scroll_speed_container_layout.addWidget(
            self._global_scroll_speed_slider
        )

        self._main_layout.addWidget(FrameSeparator(parent=self))

        self._workflow_tabs = QTabWidget(self)

        self._manual_scroll_area = QScrollArea(self._workflow_tabs)
        self._manual_scroll_area.setWidgetResizable(True)
        self._manual_scroll_area.setFrameShape(QFrame.Shape.NoFrame)

        self._manual_foci_count_widget = ManualFociCountWidget(
            self._napari_viewer,
            self._manual_scroll_area,
        )
        self._manual_scroll_area.setWidget(self._manual_foci_count_widget)

        for (
            shared_widget
        ) in self._manual_foci_count_widget.detach_shared_controls():
            self._main_layout.addWidget(shared_widget)

        self._project_directories_list = (
            self._manual_foci_count_widget._project_directories_list
        )
        self._keep_channels_widget = (
            self._manual_foci_count_widget._keep_channels_widget
        )
        self._multigonad_project_saver = (
            self._manual_foci_count_widget._multigonad_project_saver
        )
        self._project_directories_list._row_factory = self._create_project_row

        self._keep_channels_widget._keep_channels_cb.toggled.disconnect()
        self._keep_channels_widget._keep_channels_cb.toggled.connect(
            self._on_keep_channels_changed
        )
        self._keep_channels_widget._keep_channels_line_edit.editingFinished.disconnect()
        self._keep_channels_widget._keep_channels_line_edit.editingFinished.connect(
            self._on_keep_channels_changed
        )
        self._manual_foci_count_widget._add_project_directory_button.clicked.disconnect()
        self._manual_foci_count_widget._add_project_directory_button.clicked.connect(
            self._add_project_directory_button_pressed
        )
        self._manual_foci_count_widget._add_multigonad_config_button.clicked.disconnect()
        self._manual_foci_count_widget._add_multigonad_config_button.clicked.connect(
            self._add_multigonad_config_button_pressed
        )
        self._manual_foci_count_widget._remove_project_directory_button.clicked.disconnect()
        self._manual_foci_count_widget._remove_project_directory_button.clicked.connect(
            self._remove_project_directory_button_pressed
        )
        self._multigonad_project_saver.connect_save_callback(
            self._save_multigonad_project
        )

        self._main_layout.addWidget(self._workflow_tabs, 1)
        self._workflow_tabs.addTab(self._manual_scroll_area, "Manual")

        self._auto_scroll_area = QScrollArea(self._workflow_tabs)
        self._auto_scroll_area.setWidgetResizable(True)
        self._auto_scroll_area.setFrameShape(QFrame.Shape.NoFrame)

        self._auto_widget = AutoFociCountWidget(
            viewer=self._napari_viewer,
            parent=self._auto_scroll_area,
            project_list_widget=self._manual_foci_count_widget._project_directories_list,
            set_contrasts_callback=self._show_set_contrast_widget,
        )
        self._auto_scroll_area.setWidget(self._auto_widget)
        self._workflow_tabs.addTab(self._auto_scroll_area, "Auto")

    def _create_project_row(self, project_path: Path) -> QWidget:
        requested_channels = self._keep_channels_widget.get_channels()
        project_status = StitchOmeZarrWidget.get_project_status(
            project_path,
            requested_channels,
        )

        row = IntegrationProjectRow(
            f"{project_path.parent.name}/{project_path.name}"
        )
        row.apply_project_status(project_status)
        row.apply_nuclei_status(
            CLTPickNucleiWidget.is_project_nuclei_complete(project_path)
        )
        row.apply_scoring_status(
            CLTScoreNucleiWidget.is_project_scoring_complete(project_path)
        )
        row.apply_regions_status(
            CLTStitchedRegionsWidget.is_project_regions_complete(project_path)
        )
        row.apply_plots_status(is_project_plot_complete(project_path))
        return row

    def _on_keep_channels_changed(self, *_args: object) -> None:
        self._project_directories_list.refresh_rows()
        self._manual_foci_count_widget._update_process_status_labels()

    def _save_multigonad_project(self, saving_path: str) -> bool:
        project_paths = self._project_directories_list.get_project_paths()
        if not project_paths:
            return False

        return save_multigonad_project(
            saving_path=saving_path,
            project_directories=project_paths,
            project_type="clsp",
        )

    def _verify_project_directory(self, project_path: Path) -> bool:
        has_existing_project = any(
            path.is_dir() and path.name.endswith(CLSP_PROJECT_SUFFIX)
            for path in project_path.iterdir()
        )
        if has_existing_project:
            return True

        supported_entries = [
            path
            for path in project_path.iterdir()
            if path.name.endswith(".ome.zarr")
            or (
                path.is_file()
                and any(
                    path.name.endswith(extension)
                    for extension in SUPPORTED_STITCH_EXTENSIONS
                )
            )
        ]
        if not supported_entries:
            show_error(
                f"The directory {project_path} does not contain "
                "supported image files."
            )
            return False

        unsupported_files = [
            path
            for path in project_path.iterdir()
            if path.is_file() and path not in supported_entries
        ]
        if unsupported_files:
            show_error(
                f"The directory {project_path} contains unsupported files:\n"
                + "\n".join(path.name for path in unsupported_files)
            )
            return False

        return True

    def _add_project_directory_button_pressed(self) -> None:
        project_paths = get_directories(
            self,
            caption="Select project directories",
        )
        if project_paths is None:
            return

        valid_paths = [
            project_path
            for project_path in project_paths
            if (
                project_path
                not in self._project_directories_list.get_project_paths()
                and self._verify_project_directory(project_path)
            )
        ]
        self._project_directories_list.add_project_paths(valid_paths)
        self._manual_foci_count_widget._update_process_status_labels()

    def _add_multigonad_config_button_pressed(self) -> None:
        config_path = get_file(
            self,
            caption="Select a multigonad project configuration",
            filters="Config files (*.config)",
        )
        if config_path is None:
            return

        config = load_multigonad_project(config_path)
        if config is None:
            show_error("Could not load the multigonad project configuration.")
            return

        try:
            if config.get("project", "type") != "clsp":
                show_error("The selected file is not a CLSP project.")
                return
            project_paths = [
                Path(project_path)
                for _, project_path in config.items("project_directories")
            ]
        except configparser.Error:
            show_error(
                "The multigonad project configuration is missing "
                "required sections."
            )
            return

        if not project_paths:
            show_error("The multigonad project contains no directories.")
            return

        for project_path in project_paths:
            if not project_path.is_dir():
                show_error(f"Directory does not exist: {project_path}")
                return
            if not self._verify_project_directory(project_path):
                return

        self._project_directories_list.set_project_paths(project_paths)
        self._manual_foci_count_widget._update_process_status_labels()

    def _remove_project_directory_button_pressed(self) -> None:
        self._project_directories_list.remove_selected_project_paths()
        self._manual_foci_count_widget._update_process_status_labels()

    def _install_keybindings(self) -> None:
        self._napari_viewer.bind_key(
            "j", self._scroll_z_down_hold, overwrite=True
        )
        self._napari_viewer.bind_key(
            "l", self._scroll_z_up_hold, overwrite=True
        )
        self._napari_viewer.bind_key(
            "i", self._increase_scroll_speed, overwrite=True
        )
        self._napari_viewer.bind_key(
            "k", self._decrease_scroll_speed, overwrite=True
        )
        if self._scroll_timer is None:
            self._scroll_timer = QTimer(self)
            self._scroll_timer.setInterval(self._scroll_interval_ms)
            self._scroll_timer.timeout.connect(self._scroll_timer_tick)

    def _get_scroll_axis(self) -> int | None:
        dims = self._napari_viewer.dims
        non_displayed = [
            axis for axis in range(dims.ndim) if axis not in dims.displayed
        ]
        candidate_axes = (
            non_displayed if non_displayed else list(range(dims.ndim))
        )
        axis_labels = [label.lower() for label in dims.axis_labels]
        for axis in candidate_axes:
            nsteps = dims.nsteps[axis]
            if nsteps is None or nsteps < 2:
                continue
            if axis < len(axis_labels) and axis_labels[axis] in (
                "z",
                "depth",
                "slice",
            ):
                return axis
        for axis in candidate_axes:
            nsteps = dims.nsteps[axis]
            if nsteps is not None and nsteps > 1:
                return axis
        return None

    def _scroll_z(self, delta: int) -> None:
        axis = self._get_scroll_axis()
        if axis is None:
            return
        dims = self._napari_viewer.dims
        nsteps = dims.nsteps[axis]
        if nsteps is None or nsteps < 1:
            return
        current_step = int(dims.current_step[axis])
        new_step = max(0, min(current_step + delta, nsteps - 1))
        if new_step == current_step:
            return
        dims.set_current_step(axis, new_step)

    def _start_scroll(self, delta: int) -> None:
        self._scroll_direction = delta
        self._scroll_z(delta)
        if (
            self._scroll_timer is not None
            and not self._scroll_timer.isActive()
        ):
            self._scroll_timer.start()

    def _stop_scroll(self, delta: int) -> None:
        if self._scroll_direction != delta:
            return
        self._scroll_direction = 0
        if self._scroll_timer is not None:
            self._scroll_timer.stop()

    def _scroll_timer_tick(self) -> None:
        if self._scroll_direction == 0:
            return
        self._scroll_z(self._scroll_direction)

    def _adjust_scroll_speed(self, delta_ms: int) -> None:
        new_interval = self._scroll_interval_ms + delta_ms
        new_interval = max(
            self._scroll_interval_min_ms,
            min(new_interval, self._scroll_interval_max_ms),
        )
        if new_interval == self._scroll_interval_ms:
            return
        self._scroll_interval_ms = new_interval
        if self._scroll_timer is not None:
            self._scroll_timer.setInterval(self._scroll_interval_ms)
        self.set_scroll_speed_slider_value(self._scroll_interval_ms)

    def set_scroll_interval_ms(self, interval_ms: int) -> None:
        new_interval = max(
            self._scroll_interval_min_ms,
            min(interval_ms, self._scroll_interval_max_ms),
        )
        if new_interval == self._scroll_interval_ms:
            return
        self._scroll_interval_ms = new_interval
        if self._scroll_timer is not None:
            self._scroll_timer.setInterval(self._scroll_interval_ms)
        self.set_scroll_speed_slider_value(self._scroll_interval_ms)

    def _increase_scroll_speed(self, event=None) -> None:
        self._adjust_scroll_speed(-10)

    def _decrease_scroll_speed(self, event=None) -> None:
        self._adjust_scroll_speed(10)

    def _scroll_z_down_hold(self, event=None):
        self._start_scroll(-1)
        yield
        self._stop_scroll(-1)

    def _scroll_z_up_hold(self, event=None):
        self._start_scroll(1)
        yield
        self._stop_scroll(1)

    def _confirm_score_nuclei(self, event=None) -> None:
        if self._score_nuclei_widget is None:
            return
        if not self._score_nuclei_widget.isVisible():
            return
        if hasattr(self._score_nuclei_widget, "_confirm_button_pressed"):
            self._score_nuclei_widget._confirm_button_pressed()

    def _scroll_speed_slider_changed(self, value: int) -> None:
        self.set_scroll_interval_ms(self._slider_value_to_interval(value))

    def set_scroll_speed_slider_value(self, value: int) -> None:
        self._global_scroll_speed_slider.blockSignals(True)
        self._global_scroll_speed_slider.setValue(
            self._interval_to_slider_value(value)
        )
        self._global_scroll_speed_slider.blockSignals(False)

    def _slider_value_to_interval(self, value: int) -> int:
        min_value = self._global_scroll_speed_slider.minimum()
        max_value = self._global_scroll_speed_slider.maximum()
        return max_value - (value - min_value)

    def _interval_to_slider_value(self, interval: int) -> int:
        min_value = self._global_scroll_speed_slider.minimum()
        max_value = self._global_scroll_speed_slider.maximum()
        return max_value - (interval - min_value)
