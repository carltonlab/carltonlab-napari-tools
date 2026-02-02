from typing import TYPE_CHECKING, Literal, cast

from napari.layers import Image, Points, Shapes
from napari.utils.notifications import show_info
from qtpy.QtCore import Qt
from qtpy.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from carltonlab_napari_count_tool._pick_nuclei_widget_model import (
    get_points_saved_list,
    open_project,
    open_squares_layers,
    save_points_layer,
)
from carltonlab_napari_count_tool._shared_widgets import confirm_dialog

if TYPE_CHECKING:
    from napari.viewer import ViewerModel


class PickNucleiWidget(QWidget):
    def __init__(self, parent_widget: QWidget, napari_viewer: "ViewerModel"):
        super().__init__(parent_widget)

        self._napari_viewer = napari_viewer
        self._parent_widget = parent_widget
        self._image_layer: Image | None = None
        self._points_layers: list[Points] | None = None
        self._squares_shapes_layers: list[Shapes] | None = None
        self._edited_regions_layer: Shapes | None = None
        self._current_region_layer: Shapes | None = None
        self._pick_nuclei_directory: str | None = None
        self._number_of_regions: int
        # The points saved list contains a list of the regions. If the entry is None,
        # the squares haven't been set yet. If the entry is a tuple, the first value is the number of points and the second value is the saved state of the points region.
        # The third value is the saved state of the squares region.
        # The fourth value is the state of the saved sbs files
        # a points layer without points is saved only in the points summary file, not as a layer because empty layers are not saved.
        self._points_saved_list: list[None | tuple[int, bool, bool, bool]] = []

        self._layout = QVBoxLayout()
        self.setLayout(self._layout)

        self._open_image_container: QWidget = QWidget()
        self._open_image_container_layout = QVBoxLayout()
        self._open_image_container.setLayout(self._open_image_container_layout)

        self._layout.addWidget(self._open_image_container)

        self._open_image_container.setVisible(True)

        self._open_image_title: QLabel = QLabel("Open image")
        self._open_image_title.setStyleSheet("font-weight: bold")
        self._open_image_container_layout.addWidget(self._open_image_title)

        self._open_image_line_edit: QLineEdit = QLineEdit("")
        self._open_image_line_edit.setDisabled(True)
        self._open_image_container_layout.addWidget(self._open_image_line_edit)

        self._open_image_button: QPushButton = QPushButton("Open")
        self._open_image_button.clicked.connect(
            self._open_image_button_pressed
        )
        self._open_image_container_layout.addWidget(self._open_image_button)

        self._image_opened_label: QLabel = QLabel("")
        self._open_image_container_layout.addWidget(self._image_opened_label)
        self._set_open_image_label_state(False)

        self._regions_container: QWidget = QWidget()
        self._regions_container_layout = QVBoxLayout()
        self._regions_container.setLayout(self._regions_container_layout)
        self._layout.addWidget(self._regions_container)

        self._regions_title_label: QLabel = QLabel("Regions")
        self._regions_title_label.setStyleSheet("font-weight: bold")
        self._regions_container_layout.addWidget(self._regions_title_label)

        self._regions_qlist: QListWidget = QListWidget()
        self._regions_qlist.itemSelectionChanged.connect(
            self._regions_qlist_item_selection_changed
        )
        self._regions_container_layout.addWidget(self._regions_qlist)

        self._confirm_points_container: QWidget = QWidget()
        self._confirm_points_container_layout = QVBoxLayout()
        self._confirm_points_container.setLayout(
            self._confirm_points_container_layout
        )
        self._layout.addWidget(self._confirm_points_container)

        self._show_region_points_layer_button: QPushButton = QPushButton(
            "Show region points layer"
        )
        self._show_region_points_layer_button.clicked.connect(
            self._show_region_points_layer_button_pressed
        )
        self._confirm_points_container_layout.addWidget(
            self._show_region_points_layer_button
        )

        self._save_points_button: QPushButton = QPushButton(
            "Save points layer"
        )
        self._save_points_button.clicked.connect(
            self._save_points_button_pressed
        )
        self._confirm_points_container_layout.addWidget(
            self._save_points_button
        )

        self._points_saved_label: QLabel = QLabel("")
        self._confirm_points_container_layout.addWidget(
            self._points_saved_label
        )
        self._set_points_saved_label_state(False)

        self._square_size_title_label: QLabel = QLabel("Square size")
        self._square_size_title_label.setStyleSheet("font-weight: bold")
        self._confirm_points_container_layout.addWidget(
            self._square_size_title_label
        )

        self._square_size_spinbox: QSpinBox = QSpinBox()
        self._square_size_spinbox.setRange(0, 1000000)
        self._square_size_spinbox.setValue(90)
        self._square_size_spinbox.valueChanged.connect(
            self._square_size_spinbox_value_changed
        )
        self._confirm_points_container_layout.addWidget(
            self._square_size_spinbox
        )

        self._create_squares_button: QPushButton = QPushButton(
            "Create squares"
        )
        self._create_squares_button.clicked.connect(
            self._create_squares_button_pressed
        )
        self._confirm_points_container_layout.addWidget(
            self._create_squares_button
        )

        self._squares_created_label: QLabel = QLabel("")
        self._confirm_points_container_layout.addWidget(
            self._squares_created_label
        )
        self._set_set_squares_created_label_state(False)

        self._show_region_squares_layer_button: QPushButton = QPushButton(
            "Show region squares layer"
        )
        self._show_region_squares_layer_button.clicked.connect(
            self._show_region_squares_layer_button_pressed
        )
        self._confirm_points_container_layout.addWidget(
            self._show_region_squares_layer_button
        )

        self._save_squares_button: QPushButton = QPushButton("Save squares")
        self._save_squares_button.clicked.connect(
            self._save_squares_button_pressed
        )
        self._confirm_points_container_layout.addWidget(
            self._save_squares_button
        )

        self._saved_squares_label: QLabel = QLabel("")
        self._confirm_points_container_layout.addWidget(
            self._saved_squares_label
        )
        self._set_saved_squares_label_state(False)

        self._all_regions_completed_label: QLabel = QLabel("")
        self._all_regions_completed_label.setStyleSheet("font-weight: bold")
        self._all_regions_completed_label.setAlignment(
            Qt.AlignmentFlag.AlignCenter
        )
        self._confirm_points_container_layout.addWidget(
            self._all_regions_completed_label
        )
        self._set_all_regions_completed_label_state(False)

        self._create_sbs_files_button: QPushButton = QPushButton(
            "Create SBS files"
        )
        self._create_sbs_files_button.clicked.connect(
            self._create_sbs_files_button_pressed
        )
        self._confirm_points_container_layout.addWidget(
            self._create_sbs_files_button
        )

        self._create_sbs_files_label: QLabel = QLabel("")
        self._confirm_points_container_layout.addWidget(
            self._create_sbs_files_label
        )
        self._set_create_sbs_files_label_state(False)

        self._reset_gui()

    def _reset_gui(self) -> None:
        return

    def _open_image_button_pressed(self) -> None:
        if self._image_layer is not None:
            confirmed_result: bool = confirm_dialog(
                self._napari_viewer, "Image already open, open new project?"
            )
            if not confirmed_result:
                return
        self._reset_gui()
        file_dialog: QFileDialog = QFileDialog(
            self, caption="Select the project image"
        )
        file_path: str = file_dialog.getOpenFileName(
            filter="Image files (*.jpg *.jpeg *.png *.tif)"
        )[0]
        if file_path == "":
            return
        if len(self._napari_viewer.layers) > 0:
            confirmed_result: bool = confirm_dialog(
                self._napari_viewer,
                "Layers are open, it is recommended to close all non-image layers now. Confirm close all non-image layers?",
                no_mode=True,
            )
            if confirmed_result:
                removing_layer_names: list[str] = []
                layers_list = self._napari_viewer.layers
                for layer in layers_list:
                    if not isinstance(layer, Image):
                        layer_name = layer.name
                        removing_layer_names.append(layer_name)
                for removing_layer_name in removing_layer_names:
                    for napari_layer in self._napari_viewer.layers:
                        current_layer_name = napari_layer.name
                        if removing_layer_name == current_layer_name:
                            self._napari_viewer.layers.remove(napari_layer)
                            break
        open_answer: (
            Literal["failed"] | tuple[str, Image, list[Points], Shapes, Shapes]
        ) = open_project(self._napari_viewer, file_path)
        if open_answer == "failed":
            show_info("Failed to open project")
            return
        self._pick_nuclei_directory = open_answer[0]
        self._image_layer = open_answer[1]
        self._points_layers = open_answer[2]
        self._edited_regions_layer = open_answer[3]
        self._current_region_layer = open_answer[4]
        self._number_of_regions = len(
            self._edited_regions_layer._data_view.shapes
        )
        self._load_points_saved_list(self._number_of_regions)
        self._squares_shapes_layers = self._open_squares_layers()
        self._update_labels()
        self._update_list()
        self._evaluate_points_saved()

    def _load_points_saved_list(self, number_of_regions: int) -> None:
        self._points_saved_list = get_points_saved_list(
            self._pick_nuclei_directory, number_of_regions=number_of_regions
        )

    def _open_squares_layers(self) -> list[Shapes]:
        if self._pick_nuclei_directory is None:
            return []
        return open_squares_layers(
            self._napari_viewer,
            self._pick_nuclei_directory,
            self._points_saved_list,
        )

    def _update_labels(self) -> None:
        if self._image_layer is None:
            self._open_image_line_edit.setText("")
            self._set_open_image_label_state(False)
        else:
            self._open_image_line_edit.setText(self._image_layer.name)
            self._set_open_image_label_state(True)

    def _update_list(self) -> None:
        q_list = self._regions_qlist
        number_of_regions = self._number_of_regions
        if q_list.count() <= 0:
            for region_index in range(number_of_regions):
                region_string: str = "region-" + str(region_index + 1)
                adding_widget: RegionListWidget = RegionListWidget(
                    region_string, region_index
                )
                q_list_item: QListWidgetItem = QListWidgetItem()
                q_list_item.setSizeHint(adding_widget.sizeHint())
                q_list.addItem(q_list_item)
                q_list.setItemWidget(q_list_item, adding_widget)
        for region_index in range(number_of_regions):
            if self._points_saved_list[region_index] is None:
                continue
            tuple_entry: tuple[int, bool, bool, bool] = cast(
                tuple[int, bool, bool, bool],
                self._points_saved_list[region_index],
            )
            saved_points_state = tuple_entry[1]
            saved_squares_state = tuple_entry[2]
            saved_sbs_state = tuple_entry[3]
            q_list_item: QListWidgetItem = q_list.item(region_index)
            q_list_widget: RegionListWidget = cast(
                RegionListWidget, q_list.itemWidget(q_list_item)
            )
            q_list_widget.set_points_created_label_state(saved_points_state)
            q_list_widget.set_squares_created_label_state(saved_squares_state)
            q_list_widget.set_sbs_cut_label_state(saved_sbs_state)
        q_list.repaint()
        self._evaluate_points_saved()

    def _set_open_image_label_state(self, state: bool) -> None:
        if state:
            self._image_opened_label.setText("Image opened")
            self._image_opened_label.setStyleSheet("color: green")
        else:
            self._image_opened_label.setText("Image not opened")
            self._image_opened_label.setStyleSheet("color: red")

    def _set_points_saved_label_state(self, state: bool) -> None:
        if state:
            self._points_saved_label.setText("Points saved")
            self._points_saved_label.setStyleSheet("color: green")
        else:
            self._points_saved_label.setText("Points not saved")
            self._points_saved_label.setStyleSheet("color: red")

    def _set_saved_squares_label_state(self, state: bool) -> None:
        if state:
            self._saved_squares_label.setText("Squares saved")
            self._saved_squares_label.setStyleSheet("color: green")
        else:
            self._saved_squares_label.setText("Squares not saved")
            self._saved_squares_label.setStyleSheet("color: red")

    def _set_set_squares_created_label_state(self, state: bool) -> None:
        if state:
            self._squares_created_label.setText("Squares created")
            self._squares_created_label.setStyleSheet("color: green")
        else:
            self._squares_created_label.setText("Squares not created")
            self._squares_created_label.setStyleSheet("color: red")

    def _set_all_regions_completed_label_state(self, state: bool) -> None:
        if state:
            self._all_regions_completed_label.setText("All regions completed")
            self._all_regions_completed_label.setStyleSheet("color: green")
        else:
            self._all_regions_completed_label.setText(
                "Not all regions completed"
            )
            self._all_regions_completed_label.setStyleSheet("color: red")

    def _set_create_sbs_files_label_state(self, state: bool) -> None:
        if state:
            self._create_sbs_files_label.setText("SBS files created")
            self._create_sbs_files_label.setStyleSheet("color: green")
        else:
            self._create_sbs_files_label.setText("SBS files not created")
            self._create_sbs_files_label.setStyleSheet("color: red")

    def _regions_qlist_item_selection_changed(self) -> None:
        widget_selected_index = self._regions_qlist.currentRow()
        image_layer = cast(Image, self._image_layer)
        edited_regions_layer = cast(Shapes, self._edited_regions_layer)
        current_region_data_copy = edited_regions_layer._data_view.shapes[
            widget_selected_index
        ].data.copy()
        current_region_layer = cast(Shapes, self._current_region_layer)
        current_region_layer.data = []
        current_region_layer.add_polygons(current_region_data_copy)
        current_region_layer.visible = True
        current_region_layer.refresh()
        for layer in self._napari_viewer.layers:
            if layer.name == image_layer.name:
                continue
            if layer.name == current_region_layer.name:
                continue
            layer.visible = False
        points_layers_list: list[Points] = cast(
            list[Points], self._points_layers
        )
        points_layers_list[widget_selected_index].visible = True
        squares_shapes_layers_list: list[Shapes] = cast(
            list[Shapes], self._squares_shapes_layers
        )
        squares_shapes_layers_list[widget_selected_index].visible = True
        current_saved_points_tuple: tuple[int, bool, bool, bool] = cast(
            tuple[int, bool, bool, bool],
            self._points_saved_list[widget_selected_index],
        )
        if not current_saved_points_tuple[1]:
            self._napari_viewer.layers.selection.active = points_layers_list[
                widget_selected_index
            ]
            return
        self._napari_viewer.layers.selection.active = (
            squares_shapes_layers_list[widget_selected_index]
        )

    def _save_points_button_pressed(self) -> None:
        print("")
        print("Really before:")
        print(self._points_saved_list)
        if self._pick_nuclei_directory is None:
            return
        selected_region_index = self._regions_qlist.currentRow()
        casting_first: list[Points] = cast(list[Points], self._points_layers)
        saving_points_layer: Points = cast(
            Points, casting_first[selected_region_index]
        )
        number_of_points: int = len(saving_points_layer.data)
        print("The number of points is:")
        print(number_of_points)

        if save_points_layer(
            saving_points_layer,
            number_of_points,
            self._pick_nuclei_directory,
            selected_region_index,
        ):
            print("Before change: ")
            print(self._points_saved_list)
            tuple_element: tuple[int, bool, bool, bool] = cast(
                tuple[int, bool, bool, bool],
                self._points_saved_list[selected_region_index],
            )
            new_tuple_element: tuple[int, bool, bool, bool] = (
                number_of_points,
                True,
                tuple_element[2],
                tuple_element[3],
            )
            self._points_saved_list[selected_region_index] = new_tuple_element
            print("after change:")
            print(self._points_saved_list)
        self._update_list()
        self._evaluate_points_saved()

        return

    def _evaluate_points_saved(self) -> None:
        points_saved_list = self._points_saved_list
        if points_saved_list is None:
            return
        all_points_saved_list: list[bool] = [
            save_tuple[1] for save_tuple in points_saved_list
        ]
        if not any(all_points_saved_list):
            self._set_points_saved_label_state(False)
        else:
            self._set_points_saved_label_state(True)

    def _square_size_spinbox_value_changed(self) -> None:
        return

    def _create_squares_button_pressed(self) -> None:
        return

    def _save_squares_button_pressed(self) -> None:
        return

    def _create_sbs_files_button_pressed(self) -> None:
        return

    def _show_region_points_layer_button_pressed(self) -> None:
        return

    def _show_region_squares_layer_button_pressed(self) -> None:
        return


class RegionListWidget(QWidget):
    def __init__(self, region_string: str, region_index: int):
        super().__init__()

        self._region_string: str = region_string
        self._region_index: int = region_index

        self._layout = QHBoxLayout()
        self._layout.setContentsMargins(5, 2, 5, 2)
        self.setLayout(self._layout)

        self._region_label: QLabel = QLabel(region_string)
        self._points_created_label: QLabel = QLabel("")
        self._squares_created_label: QLabel = QLabel("")
        self._sbs_cut_label: QLabel = QLabel("")

        self._layout.addWidget(self._region_label)
        self._layout.addWidget(self._points_created_label)
        self._layout.addWidget(self._squares_created_label)
        self._layout.addWidget(self._sbs_cut_label)

    def set_points_created_label_state(self, state: bool) -> None:
        if state:
            self._points_created_label.setText(" +Points")
            self._points_created_label.setStyleSheet("color: green")
        else:
            self._points_created_label.setText(" -Points")
            self._points_created_label.setStyleSheet("color: red")

    def set_squares_created_label_state(self, state: bool) -> None:
        if state:
            self._squares_created_label.setText(" +Squares")
            self._squares_created_label.setStyleSheet("color: green")
        else:
            self._squares_created_label.setText(" -Squares")
            self._squares_created_label.setStyleSheet("color: red")

    def set_sbs_cut_label_state(self, state: bool) -> None:
        if state:
            self._sbs_cut_label.setText(" +SBS")
            self._sbs_cut_label.setStyleSheet("color: green")
        else:
            self._sbs_cut_label.setText(" -SBS")
            self._sbs_cut_label.setStyleSheet("color: red")
