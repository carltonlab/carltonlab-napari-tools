from typing import TYPE_CHECKING, Literal

from napari.layers import Image, Points
from napari.utils.notifications import show_info
from qtpy.QtWidgets import (
    QFileDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QVBoxLayout,
    QWidget,
    QSpinBox,
)

from carltonlab_napari_count_tool._pick_nuclei_widget_model import open_project
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
        self._pick_nuclei_directory: str | None = None

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
        self._regions_container_layout.addWidget(self._regions_qlist)

        self._nuclei_points_title_label: QLabel = QLabel("Nuclei points")
        self._regions_container_layout.addWidget(
            self._nuclei_points_title_label
        )

        self._points_qlist: QListWidget = QListWidget()
        self._regions_container_layout.addWidget(self._points_qlist)

        self._confirm_points_container: QWidget = QWidget()
        self._confirm_points_container_layout = QVBoxLayout()
        self._confirm_points_container.setLayout(
            self._confirm_points_container_layout
        )

        self._point_size_title_label: QLabel = QLabel("Point size")
        self._point_size_title_label.setStyleSheet("font-weight: bold")
        self._confirm_points_container_layout.addWidget(
            self._point_size_title_label
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
        self._layout.addWidget(self._confirm_points_container)

        self._save_squares_button: QPushButton = QPushButton("Save squares")
        self._save_squares_button.clicked.connect(
            self._save_squares_button_pressed
        )
        self._layout.addWidget(self._save_squares_button)

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
        open_answer: Literal["failed"] | tuple[str, Image, list[Points]] = (
            open_project(self._napari_viewer, file_path)
        )
        if open_answer == "failed":
            show_info("Failed to open project")
            return
        self._pick_nuclei_directory = open_answer[0]
        self._image_layer = open_answer[1]
        self._points_layers = open_answer[2]
        self._update_labels()

    def _update_labels(self) -> None:
        if self._image_layer is None:
            self._open_image_line_edit.setText("")
            self._set_open_image_label_state(False)
        else:
            self._open_image_line_edit.setText(self._image_layer.name)
            self._set_open_image_label_state(True)

    def _set_open_image_label_state(self, state: bool) -> None:
        if state:
            self._image_opened_label.setText("Image opened")
            self._image_opened_label.setStyleSheet("color: green")
        else:
            self._image_opened_label.setText("Image not opened")
            self._image_opened_label.setStyleSheet("color: red")

    def _square_size_spinbox_value_changed(self) -> None:
        return

    def _create_squares_button_pressed(self) -> None:
        return

    def _save_squares_button_pressed(self) -> None:
        return
