from random import shuffle
from typing import Literal, cast

from napari.layers import Image, Points
from napari.utils.notifications import show_info
from napari.viewer import ViewerModel
from qtpy.QtCore import Qt, QTimer
from qtpy.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from carltonlab_napari_count_tool._protocols import (
    MainWidgetCallBacks,
    ScoreWidgetButtonAPI,
)
from carltonlab_napari_count_tool._score_nuclei_widget_model import (
    CLSPSbsObject,
    add_flag_to_sbs,
    flag_in_image,
    generate_scored_points_spline_plot,
    generate_scored_points_spline_summary,
    load_tile_bounding_boxes_from_gonad_dir,
    open_image_layer_from_clsp_object,
    open_points_layer_from_clsp_object,
    open_scoring_file,
    open_scoring_zarr_directory,
    remove_flag_from_sbs,
    save_points_layer_from_clsp_object,
)
from carltonlab_napari_count_tool._shared_widgets import confirm_dialog

NAVIGATE_BUTTONS_WIDTH = 30
DEFAULT_SBS_LINE_EDIT_TEXT = "No SBS selected"
DEFAULT_BLIND_SBS_LINE_EDIT_TEXT = "Blind scoring"


class SBSListItemWidget(QWidget):
    def __init__(
        self,
        parent_widget: QWidget,
        clsp_sbs: CLSPSbsObject,
        blind_index: int | None = 0,
    ):
        super().__init__(parent_widget)
        self._sbs_object: CLSPSbsObject = clsp_sbs
        self._blind_index: int | None = blind_index

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

    def set_data(self, blind_selection: bool = False) -> None:
        self._sbs_object.load_number_of_points()
        setting_text: str
        if blind_selection:
            setting_text: str = str(self._blind_index) + " - blind_sbs"
        else:
            setting_text: str = self._sbs_object.get_display_name()
        self._sbs_label.setText(setting_text)
        ignored_flag: bool = flag_in_image(
            self._sbs_object.get_image_path(), "ignore"
        )
        if not ignored_flag:
            self._points_label.setText(
                " -- "
                + str(self._sbs_object.get_number_of_points())
                + " Points"
            )
            saved_state: bool = self._sbs_object.saved_state()
            setting_saved_str: str = (
                " -- Saved" if saved_state else " -- Not saved"
            )
            self._saved_state_label.setText(setting_saved_str)
            if saved_state:
                self._saved_state_label.setStyleSheet("color: green")
            else:
                self._saved_state_label.setStyleSheet("color: red")
        else:
            self._points_label.setText(" -- Ignored")
            self._saved_state_label.setStyleSheet("color: black")
            self._saved_state_label.setText("")

    def get_clsp_object(self) -> CLSPSbsObject:
        return self._sbs_object


OpenFileReturns = Literal["failed"] | None | tuple[list[CLSPSbsObject], str]


class ScoreNucleiWidget(QWidget):
    def __init__(
        self,
        napari_viewer: "ViewerModel",
        parent_widget: MainWidgetCallBacks,
        score_widget_api: ScoreWidgetButtonAPI,
    ):
        parent_q_widget: QWidget = cast(QWidget, parent_widget)
        super().__init__(parent_q_widget)

        self.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )

        self._napari_viewer = napari_viewer
        self._parent_widget = parent_widget
        self._scoring_layer: Image | None = None
        self._extra_layer: Image | None = None
        self._showing_points_layer: Points | None = None
        self._adding_points_layer: Points | None = None
        self._scoring_sbs_list: list[CLSPSbsObject] = []
        self._tile_bounding_boxes: dict[str, dict[int, dict[str, int]]] = {}
        self._showing_sbs_indexes: list[int] = []
        self._ct_button: ScoreWidgetButtonAPI = score_widget_api
        self._blind_state: bool = self._ct_button.get_blind_checkbox_state()
        self._shuffle_state: bool = (
            self._ct_button.get_shuffle_checkbox_state()
        )
        self._current_index: int | None = None

        self._layout: QVBoxLayout = QVBoxLayout()
        self.setLayout(self._layout)

        self._main_scroll_area: QScrollArea = QScrollArea()
        self._main_scroll_area.setWidgetResizable(True)
        self._main_scroll_area.setViewportMargins(0, 0, 10, 0)
        self._layout.addWidget(self._main_scroll_area, 1)

        self._main_container: QWidget = QWidget()
        self._main_scroll_area.setWidget(self._main_container)
        self._main_layout: QVBoxLayout = QVBoxLayout()
        self._main_container.setLayout(self._main_layout)

        self._main_title_label = QLabel("CL Score Nuclei")
        self._main_title_label.setStyleSheet(
            "font-weight: bold; font-size: 20px"
        )
        self._main_title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._main_layout.addWidget(self._main_title_label)

        self._scoring_file_container: QWidget = QWidget()
        self._scoring_file_container_layout: QVBoxLayout = QVBoxLayout()
        self._scoring_file_container_layout.setContentsMargins(12, 0, 12, 0)
        self._scoring_file_container.setLayout(
            self._scoring_file_container_layout
        )
        self._main_layout.addWidget(self._scoring_file_container)

        self._open_file_title: QLabel = QLabel("Scoring file")
        self._open_file_title.setStyleSheet("font-weight: bold")
        self._scoring_file_container_layout.addWidget(self._open_file_title)

        self._open_file_line_edit: QLineEdit = QLineEdit("")
        self._open_file_line_edit.setReadOnly(True)
        self._scoring_file_container_layout.addWidget(
            self._open_file_line_edit
        )

        self._open_file_button: QPushButton = QPushButton("Open file")
        self._open_file_button.clicked.connect(self._open_file_button_pressed)
        self._scoring_file_container_layout.addWidget(self._open_file_button)

        self._open_zarr_button: QPushButton = QPushButton("Open zarr image")
        self._open_zarr_button.clicked.connect(self._open_zarr_button_pressed)
        self._scoring_file_container_layout.addWidget(self._open_zarr_button)

        self._main_layout.addSpacing(6)
        separator = QFrame(self._main_container)
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setFrameShadow(QFrame.Shadow.Sunken)
        separator.setStyleSheet("background-color: gray;")
        separator.setFixedHeight(2)
        self._main_layout.addWidget(separator)
        self._main_layout.addSpacing(6)

        self._points_size_container: QWidget = QWidget()
        self._points_size_container_layout: QHBoxLayout = QHBoxLayout()
        self._points_size_container_layout.setContentsMargins(0, 0, 0, 0)
        self._points_size_container.setLayout(
            self._points_size_container_layout
        )
        self._main_layout.addWidget(self._points_size_container)

        self._points_size_label: QLabel = QLabel("Points size")
        self._points_size_container_layout.addWidget(self._points_size_label)

        self._points_size_spinbox: QSpinBox = QSpinBox()
        self._points_size_spinbox.setRange(1, 100)
        self._points_size_spinbox.setValue(5)
        self._points_size_spinbox.valueChanged.connect(
            self._points_size_spinbox_changed
        )
        self._points_size_container_layout.addWidget(self._points_size_spinbox)
        self._main_layout.addSpacing(6)

        self._sbs_list_container: QWidget = QWidget()
        self._sbs_list_container_layout: QVBoxLayout = QVBoxLayout()
        self._sbs_list_container_layout.setContentsMargins(12, 0, 12, 0)
        self._sbs_list_container.setLayout(self._sbs_list_container_layout)
        self._main_layout.addWidget(self._sbs_list_container)

        self._sbs_list_title: QLabel = QLabel("SBS list")
        self._sbs_list_title.setStyleSheet("font-weight: bold")
        self._sbs_list_container_layout.addWidget(self._sbs_list_title)

        self._sbs_list_scroll_area: QScrollArea = QScrollArea()
        self._sbs_list_scroll_area.setWidgetResizable(True)
        self._sbs_list_container_layout.addWidget(self._sbs_list_scroll_area)

        self._sbs_list_widget: QListWidget = QListWidget()
        self._sbs_list_widget.itemSelectionChanged.connect(
            self._list_selection_changed
        )
        self._sbs_list_scroll_area.setWidget(self._sbs_list_widget)

        self._tile_info_label: QLabel = QLabel("")
        self._sbs_list_container_layout.addWidget(self._tile_info_label)
        self._tile_info_label.setVisible(not self._blind_state)

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

        self._previous_non_scored_button: QPushButton = QPushButton("<<")
        self._previous_non_scored_button.setFixedWidth(NAVIGATE_BUTTONS_WIDTH)
        self._previous_non_scored_button.clicked.connect(
            self._previous_non_scored_button_pressed
        )
        self._navigate_confirm_buttons_container_layout.addWidget(
            self._previous_non_scored_button
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
        self._confirm_button.clicked.connect(self._confirm_button_pressed)
        self._navigate_confirm_buttons_container_layout.addWidget(
            self._confirm_button
        )

        self._next_button: QPushButton = QPushButton("  >  ")
        self._next_button.setFixedWidth(NAVIGATE_BUTTONS_WIDTH)
        self._next_button.clicked.connect(self._next_button_pressed)
        self._navigate_confirm_buttons_container_layout.addWidget(
            self._next_button
        )

        self._next_non_scored_button: QPushButton = QPushButton(">>")
        self._next_non_scored_button.setFixedWidth(NAVIGATE_BUTTONS_WIDTH)
        self._next_non_scored_button.clicked.connect(
            self._next_non_scored_button_pressed
        )
        self._navigate_confirm_buttons_container_layout.addWidget(
            self._next_non_scored_button
        )

        self._ignore_container: QWidget = QWidget()
        self._ignore_container_layout: QHBoxLayout = QHBoxLayout()
        self._ignore_container_layout.setContentsMargins(0, 0, 0, 0)
        self._ignore_container.setLayout(self._ignore_container_layout)
        self._sbs_list_container_layout.addWidget(self._ignore_container)

        self._ignore_button: QPushButton = QPushButton("Add ignore")
        self._ignore_button.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        self._ignore_button.clicked.connect(self._ignore_button_pressed)
        self._ignore_container_layout.addWidget(self._ignore_button)

        self._remove_ignore_button: QPushButton = QPushButton("Remove ignore")
        self._remove_ignore_button.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        self._remove_ignore_button.clicked.connect(
            self._remove_ignore_button_pressed
        )
        self._ignore_container_layout.addWidget(self._remove_ignore_button)

        self._sbs_list_container_layout.addWidget(
            self._navigate_confirm_buttons_container
        )

        self._progress_label: QLabel = QLabel("")
        self._main_layout.addWidget(self._progress_label)

        self._peek_button: QPushButton = QPushButton("Peek")
        self._peek_button.clicked.connect(self._peek_button_pressed)
        self._sbs_list_container_layout.addWidget(self._peek_button)

        self._main_layout.addStretch(1)

    def _reset_gui(self) -> None:
        return

    def _update_list(self) -> None:
        if len(self._scoring_sbs_list) == 0:
            self._sbs_list_widget.clear()
            return
        scoring_list: QListWidget = self._sbs_list_widget
        scoring_list.clear()
        blind_selection: bool = self._blind_state
        shuffle_selection: bool = self._shuffle_state
        self._showing_sbs_indexes = []
        if shuffle_selection:
            self._make_shuffled_indexes()
        else:
            self._showing_sbs_indexes = list(
                range(len(self._scoring_sbs_list))
            )
        for loop_index, showing_index in enumerate(self._showing_sbs_indexes):
            setting_item: QListWidgetItem = QListWidgetItem(scoring_list)
            clsp_object: CLSPSbsObject = self._scoring_sbs_list[showing_index]
            setting_widget: SBSListItemWidget
            if blind_selection:
                setting_widget = SBSListItemWidget(
                    scoring_list,
                    self._scoring_sbs_list[showing_index],
                    loop_index + 1,
                )
            else:
                setting_widget = SBSListItemWidget(
                    scoring_list, self._scoring_sbs_list[showing_index]
                )
            setting_widget.set_data(blind_selection)
            setting_item.setSizeHint(setting_widget.sizeHint())
            setting_item.setData(Qt.ItemDataRole.UserRole, clsp_object)
            scoring_list.addItem(setting_item)
            scoring_list.setItemWidget(setting_item, setting_widget)
        self._update_progress_label()

    def _make_shuffled_indexes(self) -> None:
        number_of_sbs: int = len(self._scoring_sbs_list)
        unshuffled_list: list[int] = list(range(number_of_sbs))
        shuffled_list: list[int] = unshuffled_list.copy()
        shuffle(shuffled_list)
        self._showing_sbs_indexes = shuffled_list

    def _update_progress_label(self) -> None:
        number_of_items: int = self._sbs_list_widget.count()
        saved_items: int = 0
        for item_index in range(number_of_items):
            current_item = self._sbs_list_widget.item(item_index)
            item_widget: SBSListItemWidget = cast(
                SBSListItemWidget,
                self._sbs_list_widget.itemWidget(current_item),
            )
            clsp_object: CLSPSbsObject = item_widget.get_clsp_object()
            if clsp_object.saved_state():
                saved_items += 1
        setting_string: str = f"SBS counted: {saved_items} / {number_of_items}"
        self._progress_label.setText(setting_string)
        if saved_items == number_of_items:
            self._progress_label.setStyleSheet("color: green")
        else:
            self._progress_label.setStyleSheet("color: red")

        return

    def _blind_score_checkbox_state_changed(self) -> None:
        return

    def _shuffle_sbs_indexes_state_changed(self) -> None:
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
        self._load_tile_bounding_boxes()
        self._open_file_line_edit.setText(open_list_validation[1])
        self._update_list()

    def _open_zarr_button_pressed(self) -> None:
        open_list_validation: OpenFileReturns = open_scoring_zarr_directory(
            self._napari_viewer, self
        )
        if open_list_validation is None:
            return
        if open_list_validation == "failed":
            return
        self._scoring_sbs_list = open_list_validation[0]
        self._load_tile_bounding_boxes()
        self._open_file_line_edit.setText(open_list_validation[1])
        self._update_list()

    def _load_tile_bounding_boxes(self) -> None:
        self._tile_bounding_boxes = {}
        for gonad_dir in self._get_gonad_dirs():
            self._tile_bounding_boxes[gonad_dir] = (
                load_tile_bounding_boxes_from_gonad_dir(gonad_dir)
            )

    def _get_non_scored_entries(self) -> list[int]:
        total_entries: int = self._sbs_list_widget.count()
        returning_list: list[int] = []
        for searching_entry in range(total_entries):
            list_item: QListWidgetItem = self._sbs_list_widget.item(
                searching_entry
            )
            item_widget: SBSListItemWidget = cast(
                SBSListItemWidget, self._sbs_list_widget.itemWidget(list_item)
            )
            clsp_object: CLSPSbsObject = item_widget.get_clsp_object()
            clsp_object.load_number_of_points()
            if not clsp_object.saved_state():
                returning_list.append(searching_entry)
        return returning_list

    def _previous_non_scored_button_pressed(self) -> None:
        current_list_index: int = self._sbs_list_widget.currentRow()
        found_non_scored: list[int] = self._get_non_scored_entries()
        smaller_ints: list[int] = [
            smaller_value
            for smaller_value in found_non_scored
            if smaller_value < current_list_index
        ]
        if len(smaller_ints) == 0:
            show_info("No smaller entries without scoring found")
            return
        max_smaller: int = max(smaller_ints)
        self._sbs_list_widget.setCurrentRow(max_smaller)

    def _previous_button_pressed(self) -> None:
        current_list_index: int = self._sbs_list_widget.currentRow()
        minus_one: int = current_list_index - 1
        if minus_one < 0 or minus_one >= self._sbs_list_widget.count():
            last_index: int = self._sbs_list_widget.count() - 1
            self._sbs_list_widget.setCurrentRow(last_index)
            return
        self._sbs_list_widget.setCurrentRow(minus_one)

    def _next_button_pressed(self) -> None:
        current_list_index: int = self._sbs_list_widget.currentRow()
        plus_one: int = current_list_index + 1
        if plus_one >= self._sbs_list_widget.count() or plus_one < 0:
            self._sbs_list_widget.setCurrentRow(0)
            return
        self._sbs_list_widget.setCurrentRow(plus_one)

    def _next_non_scored_button_pressed(self) -> None:
        current_list_index: int = self._sbs_list_widget.currentRow()
        found_non_scored: list[int] = self._get_non_scored_entries()
        larger_ints: list[int] = [
            larger_int
            for larger_int in found_non_scored
            if larger_int > current_list_index
        ]
        if len(larger_ints) == 0:
            show_info("No larger entries without scoring found")
            return
        min_larger: int = min(larger_ints)
        self._sbs_list_widget.setCurrentRow(min_larger)

    print("")

    def _confirm_button_pressed(self) -> None:
        selected_item: QListWidgetItem = self._sbs_list_widget.currentItem()
        selection_index: int = self._sbs_list_widget.currentRow()
        selected_widget: SBSListItemWidget = cast(
            SBSListItemWidget, self._sbs_list_widget.itemWidget(selected_item)
        )
        clsp_object: CLSPSbsObject = selected_widget.get_clsp_object()
        clsp_object.load_number_of_points()
        if clsp_object.saved_state():
            confirm_answer: bool = confirm_dialog(
                self._napari_viewer, "Points file already created, replace?"
            )
            if not confirm_answer:
                return
        if self._adding_points_layer is None:
            return
        save_points_layer_from_clsp_object(
            self._adding_points_layer, clsp_object
        )
        blind_state: bool = self._blind_state
        selected_widget.set_data(blind_state)
        next_index: int = selection_index + 1
        if next_index < self._sbs_list_widget.count():
            self._next_non_scored_button_pressed()
            return
        self._list_selection_changed()

    def _peek_button_pressed(self) -> None:
        selected_index: int = self._sbs_list_widget.currentRow()
        if not selected_index >= 0:
            return
        confirm_answer: bool = confirm_dialog(
            self._napari_viewer, "Peek at the current sbs?"
        )
        if not confirm_answer:
            return
        selected_item: QListWidgetItem = self._sbs_list_widget.currentItem()
        selected_widget: SBSListItemWidget = cast(
            SBSListItemWidget, self._sbs_list_widget.itemWidget(selected_item)
        )
        clsp_object: CLSPSbsObject = selected_widget.get_clsp_object()
        image_path: str = clsp_object.get_image_path()
        print("")
        print(f"PEEK: The peeked image path is: {image_path}")
        print("")

    def _list_selection_changed(self) -> None:
        selected_index: int = self._sbs_list_widget.currentRow()
        if (
            self._scoring_layer is not None
            and self._current_index != selected_index
        ):
            self._napari_viewer.layers.remove(self._scoring_layer)
        if self._showing_points_layer is not None:
            self._napari_viewer.layers.remove(self._showing_points_layer)
        if self._adding_points_layer is not None:
            self._napari_viewer.layers.remove(self._adding_points_layer)
        if (
            self._extra_layer is not None
            and selected_index != self._current_index
        ):
            self._napari_viewer.layers.remove(self._extra_layer)
        blind_state: bool = self._blind_state
        selected_item: QListWidgetItem = self._sbs_list_widget.currentItem()
        selected_widget: SBSListItemWidget = cast(
            SBSListItemWidget, self._sbs_list_widget.itemWidget(selected_item)
        )
        selected_clsp_object = selected_widget.get_clsp_object()
        overlapping_tiles = selected_clsp_object.overlapping_tiles
        if len(overlapping_tiles) == 0:
            tile_string = "Tiles: none"
        else:
            tile_string = "Tiles: " + ", ".join(
                str(tile) for tile in overlapping_tiles
            )
        self._tile_info_label.setText(
            tile_string
            + " | Contrast source: "
            + selected_clsp_object.contrast_source
        )
        self._tile_info_label.setVisible(not blind_state)
        selected_widget.set_data(blind_state)
        if selected_index != self._current_index:
            opening_image_layer: tuple[Image, Image] = (
                open_image_layer_from_clsp_object(
                    self._napari_viewer,
                    selected_clsp_object,
                    blind=blind_state,
                )
            )
            self._scoring_layer = opening_image_layer[1]
            self._extra_layer = opening_image_layer[0]
            self._current_index = selected_index
        if self._scoring_layer is None:
            return
        layer_dims = self._scoring_layer.ndim
        opening_points_layer: Points = open_points_layer_from_clsp_object(
            self._napari_viewer,
            selected_clsp_object,
            points_size=self._points_size_spinbox.value(),
            layer_dims=layer_dims,
        )
        self._showing_points_layer = opening_points_layer
        QTimer.singleShot(
            0,
            lambda setting_layer=self._showing_points_layer: self._set_layer_opacity_and_color(
                setting_layer, 0.3, "red", out_of_slice_display=True
            ),
        )
        self._showing_points_layer.refresh()
        number_of_points_in_showing_layer: int = len(
            self._showing_points_layer.data
        )
        if number_of_points_in_showing_layer > 0:
            showing_data = self._showing_points_layer.data.copy()
            self._adding_points_layer = self._napari_viewer.add_points(
                showing_data, name="adding_points", ndim=layer_dims
            )
        else:
            self._adding_points_layer = self._napari_viewer.add_points(
                name="adding_points", ndim=layer_dims
            )
        self._napari_viewer.layers.selection.active = self._adding_points_layer
        self._adding_points_layer.mode = "add"
        self._adding_points_layer.size = self._points_size_spinbox.value()
        self._adding_points_layer.current_size = (
            self._points_size_spinbox.value()
        )
        self._adding_points_layer.refresh()
        QTimer.singleShot(
            0,
            lambda setting_layer=self._adding_points_layer: self._set_layer_opacity_and_color(
                setting_layer, 1.0, "white", out_of_slice_display=True
            ),
        )
        self._update_progress_label()

    def _set_layer_opacity_and_color(
        self,
        layer: Points,
        opacity: float,
        color: str,
        out_of_slice_display: bool = True,
    ) -> None:
        layer.opacity = opacity
        layer.border_color = color
        layer.face_color = color
        layer.out_of_slice_display = out_of_slice_display
        layer.refresh_colors()
        layer.refresh()

    def _points_size_spinbox_changed(self, value: int) -> None:
        if self._showing_points_layer is not None:
            self._showing_points_layer.size = value
            self._showing_points_layer.current_size = value
            self._showing_points_layer.refresh()
        if self._adding_points_layer is not None:
            self._adding_points_layer.size = value
            self._adding_points_layer.current_size = value
            self._adding_points_layer.refresh()

    def set_blind_state(self, state: bool) -> None:
        self._blind_state = state
        self._tile_info_label.setVisible(not state)
        if self._scoring_sbs_list:
            self._update_list()

    def set_shuffle_state(self, state: bool) -> None:
        self._shuffle_state = state
        if self._scoring_sbs_list:
            self._update_list()

    def _create_summary_pressed(self) -> None:
        gonad_dirs = self._get_gonad_dirs()
        if not gonad_dirs:
            show_info("No scoring file loaded")
            return
        created_paths: list[str] = []
        for gonad_dir in gonad_dirs:
            created_path = generate_scored_points_spline_summary(gonad_dir)
            if created_path is not None:
                created_paths.append(created_path)
        if not created_paths:
            show_info("Failed to create scored points spline summary")
            return
        if len(created_paths) == 1:
            show_info(f"Summary saved: {created_paths[0]}")
        else:
            show_info(f"Summaries saved: {len(created_paths)}")

    def _create_plot_pressed(self) -> None:
        gonad_dirs = self._get_gonad_dirs()
        if not gonad_dirs:
            show_info("No scoring file loaded")
            return
        created_paths: list[str] = []
        for gonad_dir in gonad_dirs:
            created_path = generate_scored_points_spline_plot(gonad_dir)
            if created_path is not None:
                created_paths.append(created_path)
        if not created_paths:
            show_info("Failed to create scored points spline plot")
            return
        if len(created_paths) == 1:
            show_info(f"Plot saved: {created_paths[0]}")
        else:
            show_info(f"Plots saved: {len(created_paths)}")

    def _ignore_button_pressed(self) -> None:
        current_item = self._sbs_list_widget.currentItem()
        current_item_sbs: SBSListItemWidget = cast(
            SBSListItemWidget, self._sbs_list_widget.itemWidget(current_item)
        )
        clsp_object: CLSPSbsObject = current_item_sbs.get_clsp_object()
        image_path: str = clsp_object.get_image_path()
        add_flag_to_sbs(image_path, "ignore")
        current_item_sbs.set_data(self._blind_state)
        selection_index: int = self._sbs_list_widget.currentRow()
        next_index: int = selection_index + 1
        if next_index < self._sbs_list_widget.count():
            self._next_non_scored_button_pressed()
            return
        return

    def _remove_ignore_button_pressed(self) -> None:
        current_item = self._sbs_list_widget.currentItem()
        current_item_sbs = cast(
            SBSListItemWidget, self._sbs_list_widget.itemWidget(current_item)
        )
        clsp_object: CLSPSbsObject = current_item_sbs.get_clsp_object()
        image_path: str = clsp_object.get_image_path()
        remove_flag_from_sbs(image_path, "ignore")
        current_item_sbs.set_data(self._blind_state)
        self._list_selection_changed()
        return

    def _get_gonad_dirs(self) -> list[str]:
        if not self._scoring_sbs_list:
            return []
        gonad_dirs = []
        for sbs_object in self._scoring_sbs_list:
            gonad_dirs.append(sbs_object.get_gonad_dir())
        return sorted(set(gonad_dirs))
