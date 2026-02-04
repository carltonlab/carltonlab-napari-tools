from typing import TYPE_CHECKING, Literal, cast

import numpy as np
from napari.layers import Image, Layer, Points, Shapes
from napari.utils.notifications import show_info
from qtpy.QtCore import QTimer
from qtpy.QtWidgets import (
    QCheckBox,
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
    create_squares_layers_from_points_layer,
    cut_sbs_files_from_squares_and_image_layers,
    get_points_saved_list,
    open_project,
    open_squares_layers,
    save_points_or_square_layer,
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
        self._extra_regions_layer: Shapes | None = None
        self._all_points_layer: Points | None = None
        self._all_points_2d_layer: Points | None = None
        self._current_points_2d_layer: Points | None = None
        self._all_squares_layer: Shapes | None = None
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

        self._show_all_regions_checkbox: QCheckBox = QCheckBox(
            "Show all regions"
        )
        self._show_all_regions_checkbox.setChecked(True)
        self._show_all_regions_checkbox.stateChanged.connect(
            self._show_all_regions_checkbox_state_changed
        )
        self._regions_container_layout.addWidget(
            self._show_all_regions_checkbox
        )

        self._show_in_all_slices_checkbox: QCheckBox = QCheckBox(
            "Show in all slices"
        )
        self._show_in_all_slices_checkbox.setChecked(True)
        self._show_in_all_slices_checkbox.stateChanged.connect(
            self._show_all_regions_checkbox_state_changed
        )
        self._regions_container_layout.addWidget(
            self._show_in_all_slices_checkbox
        )

        self._confirm_points_container: QWidget = QWidget()
        self._confirm_points_container_layout = QVBoxLayout()
        self._confirm_points_container.setLayout(
            self._confirm_points_container_layout
        )
        self._layout.addWidget(self._confirm_points_container)

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
            Literal["failed"]
            | tuple[
                str,
                Image,
                list[Points],
                list[Shapes],
                Shapes,
                Shapes,
                Shapes,
                Points,
                Points,
                Shapes,
                list[tuple[int, bool, bool, bool] | None],
            ]
        ) = open_project(self._napari_viewer, file_path)
        if open_answer == "failed":
            show_info("Failed to open project")
            return
        self._pick_nuclei_directory = open_answer[0]
        self._image_layer = open_answer[1]
        self._points_layers = open_answer[2]
        self._squares_shapes_layers = open_answer[3]
        self._edited_regions_layer = open_answer[4]
        self._current_region_layer = open_answer[5]
        self._extra_regions_layer = open_answer[6]
        self._all_points_layer = open_answer[7]
        self._all_points_2d_layer = open_answer[8]
        self._all_squares_layer = open_answer[9]
        self._points_saved_list = open_answer[10]
        self._number_of_regions = len(
            self._edited_regions_layer._data_view.shapes
        )
        self._update_labels()
        self._update_list()
        self._evaluate_points_saved()
        self._evaluate_squares_saved()

    def _load_points_saved_list(self, number_of_regions: int) -> None:
        self._points_saved_list = get_points_saved_list(
            self._pick_nuclei_directory, number_of_regions=number_of_regions
        )

    def _open_squares_layers(self) -> list[Shapes]:
        if self._pick_nuclei_directory is None:
            return []
        if self._image_layer is None:
            return []
        return open_squares_layers(
            self._napari_viewer,
            self._pick_nuclei_directory,
            self._points_saved_list,
            self._image_layer.ndim,
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

    def _set_create_sbs_files_label_state(self, state: bool) -> None:
        if state:
            self._create_sbs_files_label.setText("SBS files created")
            self._create_sbs_files_label.setStyleSheet("color: green")
        else:
            self._create_sbs_files_label.setText("SBS files not created")
            self._create_sbs_files_label.setStyleSheet("color: red")

    def _set_layers_color_and_opacity(
        self, setting_layer: Layer, opacity: float, color: str
    ):
        if setting_layer.opacity != opacity:
            setting_layer.opacity = opacity
        if isinstance(setting_layer, Shapes):
            setting_layer.edge_color = color
        if isinstance(setting_layer, Points):
            setting_layer.border_color = color
        if isinstance(setting_layer, (Shapes, Points)):
            setting_layer.face_color = color
            setting_layer.refresh_colors()
        setting_layer.refresh()

    def _regions_qlist_item_selection_changed(self) -> None:
        image_layer = cast(Image, self._image_layer)
        current_region_layer = cast(Shapes, self._current_region_layer)
        for layer in self._napari_viewer.layers:
            if layer.name == image_layer.name:
                continue
            if layer.name == current_region_layer.name:
                continue
            layer.visible = False
        show_all_regions_state = self._show_all_regions_checkbox.isChecked()
        show_all_slices_state = self._show_in_all_slices_checkbox.isChecked()
        widget_selected_index = self._regions_qlist.currentRow()
        self._display_edited_regions(
            widget_selected_index, show_all_regions_state
        )
        self._display_points_layers(
            widget_selected_index,
            show_all_regions_state,
            show_all_slices_state,
        )
        self._display_squares_layers(
            widget_selected_index, show_all_regions_state
        )
        current_saved_points_tuple: tuple[int, bool, bool, bool] = cast(
            tuple[int, bool, bool, bool],
            self._points_saved_list[widget_selected_index],
        )
        points_layers_list: list[Points] = cast(
            list[Points], self._points_layers
        )
        squares_layers_list: list[Shapes] = cast(
            list[Shapes], self._squares_shapes_layers
        )
        if not current_saved_points_tuple[1]:
            self._napari_viewer.layers.selection.active = points_layers_list[
                widget_selected_index
            ]
            return
        self._napari_viewer.layers.selection.active = squares_layers_list[
            widget_selected_index
        ]

    def _display_edited_regions(
        self, showing_index: int, show_all_regions_state: bool
    ) -> None:
        current_region_layer = cast(Shapes, self._current_region_layer)
        edited_regions_layer = cast(Shapes, self._edited_regions_layer)
        current_region_data_copy = edited_regions_layer._data_view.shapes[
            showing_index
        ].data.copy()
        current_region_layer.data = []
        current_region_layer.add_polygons(current_region_data_copy)
        current_region_layer.visible = True
        self._set_layers_color_and_opacity(current_region_layer, 0.5, "yellow")
        extra_regions_layer = cast(Shapes, self._extra_regions_layer)
        if show_all_regions_state:
            new_appending_data = []
            for shape_index, shape_object in enumerate(
                edited_regions_layer._data_view.shapes
            ):
                if shape_index != showing_index:
                    new_appending_data.append(shape_object.data)
            extra_regions_layer.data = new_appending_data
            extra_regions_layer.visible = True
            self._set_layers_color_and_opacity(extra_regions_layer, 0.3, "red")
        return

    def _display_points_layers(
        self,
        showing_index: int,
        show_all_regions_state: bool,
        show_all_slices_state: bool,
    ) -> None:
        points_layers_list: list[Points] = cast(
            list[Points], self._points_layers
        )
        if show_all_slices_state and show_all_regions_state:
            points_2d_layer = self._all_points_2d_layer
            if points_2d_layer is None:
                show_info("The points 2D layer is not open. ERROR")
                return
            self._combine_points_data(
                points_2d_layer, points_layers_list, showing_index, True
            )
            points_2d_layer.visible = True
        elif not show_all_slices_state and show_all_regions_state:
            all_points_layer = self._all_points_layer
            if all_points_layer is None:
                show_info("The all points layer is not open. ERROR")
                return
            self._combine_points_data(
                all_points_layer, points_layers_list, showing_index, False
            )
            all_points_layer.visible = True
            all_points_layer.out_of_slice_display = True
        points_layers_list[showing_index].visible = True
        points_layers_list[showing_index].out_of_slice_display = True
        self._set_layers_color_and_opacity(
            points_layers_list[showing_index], 1.0, "yellow"
        )
        return

    def _display_squares_layers(
        self, showing_index: int, showing_all_regions_state: bool
    ):
        squares_layers_list: list[Shapes] = cast(
            list[Shapes], self._squares_shapes_layers
        )
        if showing_all_regions_state:
            all_squares_layer = self._all_squares_layer
            if all_squares_layer is None:
                show_info("The all squares layer is not open. ERROR")
                return
            combined_squares_data = []
            number_of_regions: int = self._number_of_regions
            for region_index in range(number_of_regions):
                if region_index == showing_index:
                    continue
                current_region_data_copy = squares_layers_list[
                    region_index
                ].data.copy()
                for square_data in current_region_data_copy:
                    combined_squares_data.append(square_data)
            setting_np_array: np.ndarray = np.asarray(combined_squares_data)
            all_squares_layer.data = setting_np_array
            self._set_layers_color_and_opacity(all_squares_layer, 0.3, "red")
            all_squares_layer.visible = True
        squares_layers_list[showing_index].visible = True
        self._set_layers_color_and_opacity(
            squares_layers_list[showing_index], 0.5, "yellow"
        )

    def _combine_points_data(
        self,
        combined_layer: Points,
        points_layers_list: list[Points],
        exlcuding_index: int,
        bidimension_mode: bool,
    ) -> None:
        combined_points_data = []
        number_of_regions: int = self._number_of_regions
        for region_index in range(number_of_regions):
            if region_index == exlcuding_index:
                continue
            current_region_data_copy = points_layers_list[
                region_index
            ].data.copy()
            for point_data in current_region_data_copy:
                if bidimension_mode:
                    appending_values = [point_data[-2], point_data[-1]]
                    combined_points_data.append(appending_values)
                else:
                    combined_points_data.append(point_data)
        setting_np_array: np.ndarray = np.asarray(combined_points_data)
        combined_layer.data = setting_np_array
        QTimer.singleShot(
            0,
            lambda setting_layer=combined_layer: self._set_layers_color_and_opacity(
                setting_layer, 0.3, "red"
            ),
        )
        return

    def _save_points_button_pressed(self) -> None:
        if self._pick_nuclei_directory is None:
            return
        selected_region_index = self._regions_qlist.currentRow()
        casting_first: list[Points] = cast(list[Points], self._points_layers)
        saving_points_layer: Points = cast(
            Points, casting_first[selected_region_index]
        )
        number_of_points: int = len(saving_points_layer.data)

        if save_points_or_square_layer(
            saving_points_layer,
            number_of_points,
            self._pick_nuclei_directory,
            selected_region_index,
        ):
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
        current_list_index = self._regions_qlist.currentRow()
        if self._points_layers is None or self._squares_shapes_layers is None:
            show_info("The points of squares layers are not open. EROR")
            return
        if (
            self._points_layers[current_list_index] is None
            or self._squares_shapes_layers[current_list_index] is None
        ):
            show_info("The points of squares layers are not open. EROR")
            return
        if len(self._squares_shapes_layers[current_list_index].data):
            confirm_result = confirm_dialog(
                self._napari_viewer, "Squares are created, replace?", True
            )
            if not confirm_result:
                return
        square_width: int = self._square_size_spinbox.value()
        create_squares_layers_from_points_layer(
            self._points_layers[current_list_index],
            self._squares_shapes_layers[current_list_index],
            square_width,
        )
        self._regions_qlist_item_selection_changed()
        return

    def _save_squares_button_pressed(self) -> None:
        if self._pick_nuclei_directory is None:
            return
        selected_region_index = self._regions_qlist.currentRow()
        squares_list: list[Shapes] = cast(
            list[Shapes], self._squares_shapes_layers
        )
        saving_squares_layer: Shapes = cast(
            Shapes, squares_list[selected_region_index]
        )
        if save_points_or_square_layer(
            saving_squares_layer,
            None,
            self._pick_nuclei_directory,
            selected_region_index,
        ):
            tuple_element: tuple[int, bool, bool, bool] = cast(
                tuple[int, bool, bool, bool],
                self._points_saved_list[selected_region_index],
            )
            new_tuple_element: tuple[int, bool, bool, bool] = (
                tuple_element[0],
                tuple_element[1],
                True,
                tuple_element[3],
            )
            self._points_saved_list[selected_region_index] = new_tuple_element
        self._update_list()
        self._evaluate_squares_saved()

        return

    def _evaluate_squares_saved(self) -> None:
        points_saved_list = self._points_saved_list
        if points_saved_list is None:
            return
        all_squares_saved_list: list[bool] = [
            save_tuple[2] for save_tuple in points_saved_list
        ]
        if not any(all_squares_saved_list):
            self._set_saved_squares_label_state(False)
        else:
            self._set_saved_squares_label_state(True)

    def _create_sbs_files_button_pressed(self) -> None:
        if self._pick_nuclei_directory is None:
            return
        selected_region_index: int = self._regions_qlist.currentRow()
        squares_list: list[Shapes] = cast(
            list[Shapes], self._squares_shapes_layers
        )
        cutting_square_layer: Shapes = squares_list[selected_region_index]
        image_layer: Image = cast(Image, self._image_layer)
        cut_sbs_files_from_squares_and_image_layers(
            image_layer,
            cutting_square_layer,
            self._pick_nuclei_directory,
            selected_region_index,
        )
        print("Saved sbs")
        return

    def _show_all_regions_checkbox_state_changed(self) -> None:
        self._regions_qlist_item_selection_changed()


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
