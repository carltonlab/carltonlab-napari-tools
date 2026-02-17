from typing import TYPE_CHECKING, Literal, cast

from napari.layers import Image, Shapes
from napari.layers.shapes._shapes_models import Shape
from napari.utils.notifications import show_info
from qtpy.QtCore import Qt
from qtpy.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from carltonlab_napari_count_tool._protocols import (
    CToolButton,
    MainWidgetCallBacks,
)
from carltonlab_napari_count_tool._regions_widget_model import (
    EDITED_REGIONS_FILE_NAME,
    REGIONS_FILE_NAME,
    SPLINE_FILE_NAME,
    create_edited_regions_layer,
    create_regions_layer,
    display_splines,
    expand_shape,
    get_spline_equal_segments,
    load_project_files,
    open_project,
    save_expansion_spinbox_values,
    save_shapes_layer,
    verify_spline_interpolation,
)

if TYPE_CHECKING:
    from napari.components import ViewerModel

GOOD_LABEL_COLOR_CSS = "rgb(60,255,60)"
BAD_LABEL_COLOR_CSS = "rgb(255,60,60)"
SPLINE_SAVED_TEXT = "Spline saved"
SPLINE_NOT_SAVED_TEXT = "Spline not saved"
SPLINE_EDGE_COLOR = "eb3434"
REGION_COLOR = "#27adf5"
REGIONS_CREATED_TEXT = "Regions created"
REGIONS_NOT_CREATED_TEXT = "Regions not created"
REGIONS_EDITED_TEXT = "Regions edited and saved"
REGIONS_NOT_EDITED_TEXT = "Edited regions not saved"


class RegionWidget(QWidget):
    def __init__(
        self,
        napari_viewer: "ViewerModel",
        parent_widget: MainWidgetCallBacks,
        images: tuple[Image, ...] | None = None,
        image_path: str | None = None,
        ct_button: CToolButton | None = None,
    ):
        parent_q_widget = cast(QWidget, parent_widget)
        super().__init__(parent_q_widget)
        self._napari_viewer = napari_viewer
        self._parent_widget = parent_widget
        self._images: tuple[Image, ...] | None = images
        self._image_path: str | None = image_path
        self._ct_button: CToolButton | None = ct_button

        self._image_layer: Image | None = None
        self._spline_layer: Shapes | None = None
        self._regions_layer: Shapes | None = None

        self._image_directory: str | None = None
        self._regions_path: str | None = None

        self._initialize_gui()

    def _initialize_gui(self):
        self._layout: QVBoxLayout = QVBoxLayout()
        self.setLayout(self._layout)

        self._main_scroll_area: QScrollArea = QScrollArea()
        self._main_scroll_area.setWidgetResizable(True)
        self._layout.addWidget(self._main_scroll_area)

        self._main_container: QWidget = QWidget()
        self._main_scroll_area.setWidget(self._main_container)
        self._main_layout: QVBoxLayout = QVBoxLayout()
        self._main_container.setLayout(self._main_layout)

        self._no_image_open_container: QWidget = QWidget()
        self._no_image_open_container_layout = QVBoxLayout()
        self._no_image_open_container.setLayout(
            self._no_image_open_container_layout
        )
        self._main_layout.addWidget(self._no_image_open_container)

        self._no_image_open_title_label: QLabel = QLabel("No image open")
        self._no_image_open_title_label.setAlignment(
            Qt.AlignmentFlag.AlignCenter
        )

        self._no_image_open_title_label.setStyleSheet(
            "font-weight: bold; color: red;"
        )
        self._no_image_open_container_layout.addWidget(
            self._no_image_open_title_label
        )

        self._spline_container: QWidget = QWidget()
        self._spline_container_layout = QVBoxLayout()
        self._spline_container.setLayout(self._spline_container_layout)
        self._main_layout.addWidget(self._spline_container)

        self._spline_layer_title: QLabel = QLabel("Spline layer")
        self._spline_layer_title.setStyleSheet("font-weight: bold")
        self._spline_container_layout.addWidget(self._spline_layer_title)

        self._spline_layer_line_edit: QLineEdit = QLineEdit("")
        self._spline_layer_line_edit.setDisabled(True)
        self._spline_container_layout.addWidget(self._spline_layer_line_edit)

        self._interpolation_order_container: QWidget = QWidget()
        self._interpolation_order_container_layout = QHBoxLayout()
        self._interpolation_order_container.setLayout(
            self._interpolation_order_container_layout
        )
        self._interpolation_order_label = QLabel("Interpolation order")
        self._interpolation_order_container_layout.addWidget(
            self._interpolation_order_label
        )
        self._interpolation_order_spin_box = QSpinBox()
        self._interpolation_order_spin_box.setValue(3)
        self._interpolation_order_spin_box.setSingleStep(1)
        self._interpolation_order_spin_box.setMinimum(1)
        self._interpolation_order_spin_box.valueChanged.connect(
            self._display_spline_button_pressed
        )
        self._interpolation_order_container_layout.addWidget(
            self._interpolation_order_spin_box
        )

        self._spline_container_layout.addWidget(
            self._interpolation_order_container
        )

        self._display_spline_button = QPushButton("Display spline")
        self._display_spline_button.clicked.connect(
            self._display_spline_button_pressed
        )
        self._spline_container_layout.addWidget(self._display_spline_button)

        self._save_spline_button: QPushButton = QPushButton("Save")
        self._save_spline_button.clicked.connect(
            self._save_spline_button_pressed
        )
        self._spline_container_layout.addWidget(self._save_spline_button)

        self._spline_saved_label: QLabel = QLabel()
        self._spline_container_layout.addWidget(self._spline_saved_label)
        self._set_spline_saved_state(False)

        self._number_of_regions_container: QWidget = QWidget()
        self._number_of_regions_container_layout = QVBoxLayout()
        self._number_of_regions_container.setLayout(
            self._number_of_regions_container_layout
        )
        self._main_layout.addWidget(self._number_of_regions_container)

        self._regions_title_label: QLabel = QLabel("Regions layer")
        self._regions_title_label.setStyleSheet("font-weight: bold")
        self._number_of_regions_container_layout.addWidget(
            self._regions_title_label
        )

        self._regions_line_edit: QLineEdit = QLineEdit("")
        self._regions_line_edit.setDisabled(True)
        self._number_of_regions_container_layout.addWidget(
            self._regions_line_edit
        )

        self._numbers_region_label: QLabel = QLabel("Number of regions")
        self._numbers_region_label.setStyleSheet("font-weight: bold")
        self._number_of_regions_container_layout.addWidget(
            self._numbers_region_label
        )

        self._number_regions_spinner: QSpinBox = QSpinBox()
        self._number_regions_spinner.setMinimum(1)
        self._number_regions_spinner.setMaximum(100)
        self._number_regions_spinner.setValue(7)
        self._number_regions_spinner.setSingleStep(1)
        self._number_of_regions_container_layout.addWidget(
            self._number_regions_spinner
        )

        self._create_regions_button: QPushButton = QPushButton(
            "Create regions"
        )
        self._create_regions_button.clicked.connect(
            self._create_regions_button_pressed
        )  # type: ignore
        self._number_of_regions_container_layout.addWidget(
            self._create_regions_button
        )

        self._regions_created_label: QLabel = QLabel()
        self._number_of_regions_container_layout.addWidget(
            self._regions_created_label
        )
        self._set_regions_created_state(False)

        self._edit_regions_container: QWidget = QWidget()
        self._edit_regions_container_layout = QVBoxLayout()
        self._edit_regions_container.setLayout(
            self._edit_regions_container_layout
        )

        self._main_layout.addWidget(self._edit_regions_container)

        self._edit_regions_title_label: QLabel = QLabel("Edit regions")
        self._edit_regions_title_label.setStyleSheet("font-weight: bold")
        self._edit_regions_container_layout.addWidget(
            self._edit_regions_title_label
        )

        self._individual_regions_container: QWidget = QWidget()
        self._individual_regions_container_layout = QVBoxLayout()
        self._individual_regions_container.setLayout(
            self._individual_regions_container_layout
        )
        self._edit_regions_container_layout.addWidget(
            self._individual_regions_container
        )

        self._individual_regions_widgets_list: list[IndividualRegionWidget] = (
            []
        )

        self._save_individual_regions_button: QPushButton = QPushButton(
            "Save edited regions"
        )
        self._save_individual_regions_button.clicked.connect(
            self._save_edited_regions_button_pressed
        )
        self._edit_regions_container_layout.addWidget(
            self._save_individual_regions_button
        )

        self._edited_regions_label: QLabel = QLabel()
        self._edit_regions_container_layout.addWidget(
            self._edited_regions_label
        )
        self._set_edited_regions_state(False)

        self._main_layout.addStretch(1)

        self._spline_container.setVisible(False)
        self._number_of_regions_container.setVisible(False)
        self._edit_regions_container.setVisible(False)

        if self._image_path is not None and self._images is not None:
            self.open_image_button_pressed()

    def _reset_gui(self) -> None:
        self._images = None
        self._image_path = None
        self._image_layer = None
        self._spline_layer = None
        self._regions_layer = None
        self._edited_regions_layer = None
        self._image_directory = None
        self._regions_path = None
        self._individual_regions_widgets_list = []

        self._spline_layer_line_edit.setText("")
        self._regions_line_edit.setText("")
        self._number_regions_spinner.setValue(7)

        while self._individual_regions_container_layout.count():
            q_item = self._individual_regions_container_layout.takeAt(0)
            q_widget = q_item.widget()
            if q_widget is not None:
                q_widget.setParent(None)
                q_widget.deleteLater()
                continue

        self._no_image_open_container.setVisible(True)
        self._spline_container.setVisible(False)
        self._number_of_regions_container.setVisible(False)
        self._edit_regions_container.setVisible(False)

        self._set_spline_saved_state(False)
        self._set_regions_created_state(False)
        self._set_edited_regions_state(False)

    def new_image_open(
        self, image_tuple: tuple[Image, ...] | None, image_path: str | None
    ) -> None:
        self._reset_gui()
        self._images = image_tuple
        self._image_path = image_path
        self.open_image_button_pressed()

    def open_image_button_pressed(self) -> None:
        if self._image_path is None:
            return
        image_path: str = self._image_path
        open_answer: Literal["load", "failed"] | tuple[str, Shapes] = (
            open_project(self._napari_viewer, image_path)
        )
        if open_answer == "failed":
            show_info("Failed to open project")
            return
        self._no_image_open_container.setVisible(False)
        if open_answer == "load":
            self._load_project(image_path)
            return
        self._regions_path = open_answer[0]
        self._spline_layer = open_answer[1]

        self._update_layers_labels()
        self._set_spline_saved_state(False)
        self._spline_container.setVisible(True)

    def _load_project(self, image_path) -> None:
        returning_tuple: (
            tuple[
                str,
                Shapes,
                Shapes | None,
                tuple[Shapes, tuple[int, ...]] | None,
            ]
            | None
        ) = load_project_files(self._napari_viewer, image_path)
        if returning_tuple is None:
            show_info("Couldn't load project. ERROR")
            return
        self._regions_path = returning_tuple[0]
        self._spline_layer = returning_tuple[1]
        if len(self._spline_layer._data_view.shapes) < 1:
            self._set_spline_saved_state(False)
            self._number_of_regions_container.setVisible(False)
        else:
            self._display_spline_button_pressed()
            self._set_spline_saved_state(True)
            self._number_of_regions_container.setVisible(True)
        self._spline_container.setVisible(True)
        if returning_tuple[2] is not None:
            self._regions_layer = returning_tuple[2]
            self._number_of_regions_container.setVisible(True)
            self._set_regions_created_state(True)
        else:
            self._set_regions_created_state(False)
        if returning_tuple[3] is not None:
            self._edited_regions_layer = returning_tuple[3][0]
            expanded_values: tuple[int, ...] = returning_tuple[3][1]
            self._edit_regions_container.setVisible(True)
            self._update_edited_regions_widget(expanded_values)
            self._set_edited_regions_state(True)
        else:
            self._set_edited_regions_state(False)
        self._update_layers_labels()
        self._parent_widget.set_image_path(image_path, self._image_layer)  # type: ignore

    def _update_displayed_vertices(self, update_shape_index: int) -> None:
        if self._spline_layer is None:
            show_info("The spline layer is not set.")
            return
        spline_layer: Shapes = self._spline_layer
        shape_data = spline_layer._data_view.shapes[update_shape_index].data
        spline_layer._data_view.edit(update_shape_index, shape_data)
        spline_layer._data_view.shapes[
            update_shape_index
        ]._update_displayed_data()
        spline_layer.edge_width = 5
        spline_layer.refresh()

    def _update_layers_labels(self) -> None:
        if self._spline_layer is not None:
            self._spline_layer_line_edit.setText(self._spline_layer.name)
            self._spline_layer.edge_color = SPLINE_EDGE_COLOR
            self._spline_layer.refresh()
        if self._regions_layer is not None:
            self._regions_line_edit.setText(self._regions_layer.name)

    def _save_spline_button_pressed(self) -> None:
        if self._spline_layer is None:
            show_info("No spline layer to save")
            return
        shapes_list = self._spline_layer._data_view
        if not shapes_list:
            show_info("No shapes list in the spline layer")
            return
        if not len(shapes_list.shapes):
            show_info("No spline created in the spline layer")
            return
        if len(shapes_list.shapes) > 1:
            show_info(
                "Only one spline(shape) should be saved in the spline layer"
            )
            return
        if self._regions_path is None:
            show_info("No regions path set")
            return
        saved_state = save_shapes_layer(
            self._napari_viewer,
            self._spline_layer,
            self._regions_path,
            SPLINE_FILE_NAME,
        )
        if not saved_state:
            show_info("Spline layer not saved")
            return
        self._set_spline_saved_state(True)
        self._number_of_regions_container.setVisible(True)

    def _display_spline_button_pressed(self) -> None:
        if self._spline_layer is None:
            show_info("No spline layer detected")
            return
        spline_layer: Shapes = cast(Shapes, self._spline_layer)
        display_splines(
            spline_layer,
            self._interpolation_order_spin_box.value(),
            (0,),
        )

    def _set_spline_saved_state(self, saved_state: bool) -> None:
        if saved_state:
            self._spline_saved_label.setText(SPLINE_SAVED_TEXT)
            self._spline_saved_label.setStyleSheet(
                f"color:{GOOD_LABEL_COLOR_CSS}"
            )
        else:
            self._spline_saved_label.setText(SPLINE_NOT_SAVED_TEXT)
            self._spline_saved_label.setStyleSheet(
                f"color:{BAD_LABEL_COLOR_CSS}"
            )

    def _set_regions_created_state(self, regions_created_state: bool) -> None:
        if regions_created_state:
            self._regions_created_label.setText(REGIONS_CREATED_TEXT)
            self._regions_created_label.setStyleSheet(
                f"color:{GOOD_LABEL_COLOR_CSS}"
            )
        else:
            self._regions_created_label.setText(REGIONS_NOT_CREATED_TEXT)
            self._regions_created_label.setStyleSheet(
                f"color:{BAD_LABEL_COLOR_CSS}"
            )

    def _set_edited_regions_state(self, edited_regions_state: bool) -> None:
        if edited_regions_state:
            self._edited_regions_label.setText(REGIONS_EDITED_TEXT)
            self._edited_regions_label.setStyleSheet(
                f"color:{GOOD_LABEL_COLOR_CSS}"
            )
        else:
            self._edited_regions_label.setText(REGIONS_NOT_EDITED_TEXT)
            self._edited_regions_label.setStyleSheet(
                f"color:{BAD_LABEL_COLOR_CSS}"
            )
        return

    def _create_regions_button_pressed(self) -> None:
        if self._regions_layer is not None:
            show_info("Regions already created")
            return
        if self._spline_layer is None or self._images is None:
            show_info("Please set both spline and image layers")
            return
        if self._regions_path is None:
            show_info("The regions path is not set. ERROR")
            return
        regions_path: str = self._regions_path
        spline_layer: Shapes = cast(Shapes, self._spline_layer)
        if len(spline_layer._data_view.shapes) != 1:
            show_info("Please draw a single polyline as a shape")
            return
        shape_obj = spline_layer._data_view.shapes[0]
        if shape_obj.interpolation_order < 2:  # type: ignore
            show_info(
                "Please make the polyline a spline and make sure the interpolation order is setup correctly"
            )
            return
        if not verify_spline_interpolation(
            spline_layer, self._interpolation_order_spin_box.value()
        ):
            return
        spline_paths = get_spline_equal_segments(
            shape_obj,
            self._number_regions_spinner.value(),
            points_per_segment=10,
        )
        self._regions_layer = create_regions_layer(
            self._napari_viewer, spline_paths, 2
        )
        self._spline_layer.visible = False
        save_shapes_layer(
            self._napari_viewer,
            self._regions_layer,
            regions_path,
            REGIONS_FILE_NAME,
        )
        self._set_regions_created_state(True)
        self._update_layers_labels()
        self._edited_regions_layer = create_edited_regions_layer(
            self._napari_viewer, self._regions_layer, 2
        )
        self._update_edited_regions_widget()
        self._regions_layer.visible = False
        self._edit_regions_container.setVisible(True)

    def _update_edited_regions_widget(
        self, expansion_tuple: tuple[int, ...] | None = None
    ) -> None:
        if self._regions_layer is None:
            return
        if self._edited_regions_layer is None:
            return
        number_of_shapes = len(self._regions_layer._data_view.shapes)
        for shape_index in range(number_of_shapes):
            expansion_value = 0
            if expansion_tuple is not None:
                expansion_value = expansion_tuple[shape_index]
            self._add_individual_widget_to_list(
                self._napari_viewer,
                self._regions_layer,
                self._edited_regions_layer,
                shape_index,
                expansion_value,
            )

    def _add_individual_widget_to_list(
        self,
        napari_viewer: "ViewerModel",
        spline_layer: Shapes,
        expanded_shapes_layer: Shapes,
        region_index: int,
        expansion_value: int,
    ) -> None:
        individual_region_widget: IndividualRegionWidget = (
            IndividualRegionWidget(
                napari_viewer,
                spline_layer,
                expanded_shapes_layer,
                region_index,
                expanded_value=expansion_value,
            )
        )
        self._individual_regions_widgets_list.append(individual_region_widget)
        self._individual_regions_container_layout.addWidget(
            individual_region_widget
        )

    def _save_edited_regions_button_pressed(self) -> None:
        if self._edited_regions_layer is None:
            show_info("No edited regions layer to save")
            return
        shapes_list = self._edited_regions_layer._data_view
        if not shapes_list:
            show_info("No shapes list in the edited regions layer")
        if not len(shapes_list.shapes):
            show_info("No edited regions created in the edited regions layer")
        if self._regions_path is None:
            show_info("No regions path set")
            return
        saved_state = save_shapes_layer(
            self._napari_viewer,
            self._edited_regions_layer,
            self._regions_path,
            EDITED_REGIONS_FILE_NAME,
        )
        if not saved_state:
            show_info("Edited regions layer not saved")
            return
        expansion_values = []
        for individual_widget in self._individual_regions_widgets_list:
            expansion_values.append(
                individual_widget.get_expansion_spinbox_value()
            )
        save_expansion_spinbox_values(expansion_values, self._regions_path)
        self._set_edited_regions_state(True)
        if self._ct_button is not None and self._image_path is not None:
            self._ct_button.validate_property(self._image_path)
        return


class IndividualRegionWidget(QWidget):
    def __init__(
        self,
        napari_viewer,
        spline_layer: Shapes,
        expanded_shapes_layer: Shapes,
        region_index: int,
        expanded_value: int = 0,
    ):
        super().__init__()
        self._napari_viewer = napari_viewer
        self._extended_shape_object: Shape | None = None
        self._expanded_shapes_layer = expanded_shapes_layer
        self._spline_layer: Shapes = spline_layer
        self._region_name = "region-"
        self._region_index = region_index
        region_number = region_index + 1

        self._layout = QHBoxLayout()
        self.setLayout(self._layout)

        if region_number is not None:
            self._region_name = self._region_name + str(region_number)
        self._region_label: QLabel = QLabel(self._region_name)
        self._layout.addWidget(self._region_label)

        self._region_edit_spinbox: QSpinBox = QSpinBox()
        self._region_edit_spinbox.setRange(0, 1000000)
        self._region_edit_spinbox.setValue(expanded_value)
        self._region_edit_spinbox.valueChanged.connect(
            self._on_spinbox_value_changed
        )
        self._layout.addWidget(self._region_edit_spinbox)

    def set_region_name(self, setting_number: int | None) -> None:
        self._region_name = "region-" + str(setting_number)

    def get_region_name(self) -> str:
        return self._region_name

    def _on_spinbox_value_changed(self) -> None:
        expand_shape(
            self._spline_layer,
            self._expanded_shapes_layer,
            self._region_index,
            self._region_edit_spinbox.value(),
        )

    def get_expansion_spinbox_value(self) -> int:
        return self._region_edit_spinbox.value()
