from typing import TYPE_CHECKING, Literal

from qtpy.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from carltonlab_napari_count_tool._score_nuclei_widget_model import (
    CLSPSbsObject,
    open_scoring_file,
)

if TYPE_CHECKING:
    from napari.components import ViewerModel
    from napari.layers import Image, Points

NAVIGATE_BUTTONS_WIDTH = 30
DEFAULT_SBS_LINE_EDIT_TEXT = "No SBS selected"
DEFAULT_BLIND_SBS_LINE_EDIT_TEXT = "Blind scoring"


class SBSListItemWidget(QWidget):
    def __init__(
        self,
        parent_widget: QWidget,
        clsp_sbs: CLSPSbsObject,
    ):
        super().__init__(parent_widget)
        self._sbs_object: CLSPSbsObject = clsp_sbs

        self._layout: QHBoxLayout = QHBoxLayout()
        self.setLayout(self._layout)

        self._sbs_label: QLabel = QLabel("default")
        self._sbs_label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        self._layout.addWidget(self._sbs_label)

        self._points_label: QLabel = QLabel("NA")
        self._layout.addWidget(self._points_label)

        self._saved_state_label: QLabel = QLabel("")
        self._layout.addWidget(self._saved_state_label)


OpenFileReturns = Literal["failed"] | None | tuple[list[CLSPSbsObject], str]


class ScoreNucleiWidget(QWidget):
    def __init__(self, parent_widget: QWidget, napari_viewer: "ViewerModel"):
        super().__init__(parent_widget)

        self._napari_viewer = napari_viewer
        self._scoring_layer: Image | None = None
        self._points_layer: Points | None = None
        self._scoring_sbs_list: list[CLSPSbsObject] = []
        self._shuffled_sbs_indexes: list[int] = []

        self._layout: QVBoxLayout = QVBoxLayout()
        self.setLayout(self._layout)

        self._main_scroll_area: QScrollArea = QScrollArea()
        self._main_scroll_area.setWidgetResizable(True)
        self._layout.addWidget(self._main_scroll_area)

        self._main_container: QWidget = QWidget()
        self._main_scroll_area.setWidget(self._main_container)
        self._main_layout: QVBoxLayout = QVBoxLayout()
        self._main_container.setLayout(self._main_layout)

        self._open_file_title: QLabel = QLabel("Scoring file")
        self._open_file_title.setStyleSheet("font-weight: bold")
        self._main_layout.addWidget(self._open_file_title)

        self._open_file_line_edit: QLineEdit = QLineEdit("")
        self._open_file_line_edit.setReadOnly(True)
        self._main_layout.addWidget(self._open_file_line_edit)

        self._blind_score_checkbox: QCheckBox = QCheckBox("Blind scoring")
        self._blind_score_checkbox.setChecked(True)
        self._blind_score_checkbox.stateChanged.connect(
            self._blind_score_checkbox_state_changed
        )
        self._main_layout.addWidget(self._blind_score_checkbox)

        self._open_file_button: QPushButton = QPushButton("Open file")
        self._open_file_button.clicked.connect(self._open_file_button_pressed)
        self._main_layout.addWidget(self._open_file_button)

        self._list_container: QWidget = QWidget()
        self._list_container_layout: QVBoxLayout = QVBoxLayout()
        self._list_container_layout.setContentsMargins(0, 0, 0, 0)
        self._list_container.setLayout(self._list_container_layout)
        self._main_layout.addWidget(self._list_container)

        self._sbs_list_title: QLabel = QLabel("SBS list")
        self._sbs_list_title.setStyleSheet("font-weight: bold")
        self._list_container_layout.addWidget(self._sbs_list_title)

        self._sbs_list_scroll_area: QScrollArea = QScrollArea()
        self._sbs_list_scroll_area.setWidgetResizable(True)
        self._list_container_layout.addWidget(self._sbs_list_scroll_area)

        self._sbs_list_widget: QListWidget = QListWidget()
        self._sbs_list_scroll_area.setWidget(self._sbs_list_widget)

        self._sbs_name_line_edit: QLineEdit = QLineEdit(
            DEFAULT_SBS_LINE_EDIT_TEXT
        )

        self._navigate_confirm_buttons_container: QWidget = QWidget()
        self._navigate_confirm_buttons_container_layout: QHBoxLayout = (
            QHBoxLayout()
        )
        self._navigate_confirm_buttons_container_layout.setContentsMargins(
            0, 0, 0, 0
        )
        self._navigate_confirm_buttons_container.setLayout(
            self._navigate_confirm_buttons_container_layout
        )

        self._previous_button: QPushButton = QPushButton("  <  ")
        self._previous_button.setFixedWidth(NAVIGATE_BUTTONS_WIDTH)
        self._previous_button.clicked.connect(self._previous_button_pressed)
        self._navigate_confirm_buttons_container_layout.addWidget(
            self._previous_button
        )

        self._confirm_button: QPushButton = QPushButton("Confirm")
        self._confirm_button.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        self._navigate_confirm_buttons_container_layout.addWidget(
            self._confirm_button
        )

        self._next_button: QPushButton = QPushButton("  >  ")
        self._next_button.setFixedWidth(NAVIGATE_BUTTONS_WIDTH)
        self._next_button.clicked.connect(self._next_button_pressed)
        self._navigate_confirm_buttons_container_layout.addWidget(
            self._next_button
        )

        self._main_layout.addWidget(self._navigate_confirm_buttons_container)

        self._remove_sbs_button: QPushButton = QPushButton("Remove points")
        self._main_layout.addWidget(self._remove_sbs_button)

        self._progress_label: QLabel = QLabel("")
        self._main_layout.addWidget(self._progress_label)

    def _update_list(self) -> None:
        if len(self._scoring_sbs_list) == 0:
            self._sbs_list_widget.clear()
            return

    def _update_progress_label(self) -> None:
        return

    def _blind_score_checkbox_state_changed(self) -> None:
        return

    def _open_file_button_pressed(self) -> None:
        open_list_validation: OpenFileReturns = open_scoring_file(
            self._napari_viewer, self
        )
        if open_list_validation is None:
            return
        if open_list_validation == "failed":
            return
        self._scoring_sbs_list = open_list_validation[0]
        self._open_file_line_edit.setText(open_list_validation[1])
        self._update_list()

    def _previous_button_pressed(self) -> None:
        return

    def _next_button_pressed(self) -> None:
        return
