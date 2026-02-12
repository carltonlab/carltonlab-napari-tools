from typing import TYPE_CHECKING

from napari.layers import Image
from qtpy.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from carltonlab_napari_count_tool._model import (
    open_project_image,
    validate_closed_layers,
)
from carltonlab_napari_count_tool._multi_gonad_widget import (
    MakeMultiGonadWidget,
)
from carltonlab_napari_count_tool._pick_nuclei_widget import PickNucleiWidget
from carltonlab_napari_count_tool._regions_widget import RegionWidget
from carltonlab_napari_count_tool._score_nuclei_widget import ScoreNucleiWidget
from carltonlab_napari_count_tool._set_contrast_widget import SetContrastWidget
from carltonlab_napari_count_tool._shared_widgets import get_file

if TYPE_CHECKING:
    import napari
    from napari.components import ViewerModel

from carltonlab_napari_count_tool._main_widget_buttons import (
    BUTTONS_LIST,
    PREPARE_BUTTONS_LIST,
    RESULTS_BUTTONS_LIST,
    SCORE_BUTTONS_LIST,
)
from carltonlab_napari_count_tool._protocols import CToolButton


class GonadControlWidget(QWidget):
    def __init__(
        self, napari_viewer: "ViewerModel", main_widget: QWidget
    ) -> None:
        super().__init__(main_widget)

        self._napari_viewer = napari_viewer
        self._main_widget = main_widget

        self._image_path: str | None = None
        self._image_layers: list[Image] | None = None
        self._project_files_dir: str | None = None

        self._layout = QVBoxLayout()
        self.setLayout(self._layout)
        self._layout.setContentsMargins(0, 0, 0, 0)

        self._image_container: QWidget = QWidget()
        self._image_container_layout: QHBoxLayout = QHBoxLayout()
        self._image_container.setLayout(self._image_container_layout)
        self._layout.addWidget(self._image_container)

        self._open_image_title: QLabel = QLabel("Image")
        self._open_image_title.setStyleSheet("font-weight: bold")
        self._image_container_layout.addWidget(self._open_image_title)

        self._open_image_line_edit: QLineEdit = QLineEdit("")
        self._image_container_layout.addWidget(self._open_image_line_edit)

        self._open_image_button: QPushButton = QPushButton("Open image")
        self._open_image_button.clicked.connect(
            self._open_image_button_pressed
        )
        self._layout.addWidget(self._open_image_button)

        self._open_image_status_label: QLabel = QLabel("")
        self._layout.addWidget(self._open_image_status_label)
        self._set_open_image_status(False)

    def _open_image_button_pressed(self) -> None:
        validated_closed_layers: bool = validate_closed_layers(
            self._napari_viewer
        )
        if not validated_closed_layers:
            return
        self._image_path = None
        self._image_layers = None
        self._project_files_dir = None
        image_path: str | None = get_file(
            self, "Select the project image file"
        )
        if image_path is None:
            return
        open_answer: tuple[str, list[Image], str] | None = open_project_image(
            self._napari_viewer, image_path
        )
        if open_answer is None:
            return
        self._image_path = open_answer[0]
        self._image_layers = open_answer[1]
        self._project_files_dir = open_answer[2]
        self.update_line_edit()
        return

    def _set_open_image_status(self, status: bool) -> None:
        if status:
            self._open_image_status_label.setText("Image opened")
            self._open_image_status_label.setStyleSheet("color: green")
        else:
            self._open_image_status_label.setText("Image not opened")
            self._open_image_status_label.setStyleSheet("color: red")

    def update_line_edit(self) -> None:
        if self._image_path is None:
            self._open_image_line_edit.setText("")
            self._set_open_image_status(False)
            return
        self._open_image_line_edit.setText(self._image_path)
        self._set_open_image_status(True)

    def set_image_closed(self) -> None:
        self._image_path = None
        self._image_layers = None
        self._project_files_dir = None
        self._open_image_line_edit.setText("")
        self._set_open_image_status(False)


class CarltonLabCountTool(QWidget):
    # your QWidget.__init__ can optionally request the napari viewer instance
    # use a type annotation of 'napari.viewer.Viewer' for any parameter
    def __init__(self, viewer: "napari.viewer.Viewer"):  # type: ignore
        super().__init__()
        self._napari_viewer = viewer
        self._already_shown = False
        self._parent_widget = None

        self._initialize_gui()

    def _initialize_gui(self) -> None:
        self._main_layout = QVBoxLayout()
        self.setLayout(self._main_layout)

        self._top_container: QWidget = QWidget()
        self._top_container_layout: QVBoxLayout = QVBoxLayout()
        self._top_container.setLayout(self._top_container_layout)

        self._top_scroll_area: QScrollArea = QScrollArea()
        self._top_scroll_area.setWidgetResizable(True)
        self._main_layout.addWidget(self._top_scroll_area)
        self._top_scroll_area.setWidget(self._top_container)

        self._prepare_container: QWidget = QWidget()
        self._prepare_container_layout: QVBoxLayout = QVBoxLayout()
        self._prepare_container.setLayout(self._prepare_container_layout)

        self._prepare_container_title: QLabel = QLabel("Prepare images")
        self._prepare_container_title.setStyleSheet("font-weight: bold")
        self._prepare_container_layout.addWidget(self._prepare_container_title)

        self._top_container_layout.addWidget(self._prepare_container)

        self._prepare_buttons_instances_dict: dict[str, CToolButton] = {}
        for class_name, class_ref in PREPARE_BUTTONS_LIST.items():
            self._prepare_buttons_instances_dict[class_name] = class_ref(
                self._napari_viewer, self
            )

        for class_instance in self._prepare_buttons_instances_dict.values():
            self._prepare_container_layout.addWidget(
                class_instance.get_button()
            )

        first_section_separator: QFrame = QFrame(self)
        first_section_separator.setFrameShape(QFrame.Shape.HLine)
        first_section_separator.setFrameShadow(QFrame.Shadow.Sunken)
        first_section_separator.setStyleSheet("background-color: gray;")
        first_section_separator.setFixedHeight(2)
        self._top_container_layout.addWidget(first_section_separator)

        self._process_container: QWidget = QWidget()
        self._process_container_layout: QVBoxLayout = QVBoxLayout()
        self._process_container.setLayout(self._process_container_layout)

        self._process_container_title: QLabel = QLabel("Process gonads")
        self._process_container_title.setStyleSheet("font-weight: bold")
        self._process_container_layout.addWidget(self._process_container_title)

        self._process_gonads_widget: GonadControlWidget = GonadControlWidget(
            self._napari_viewer, self
        )

        self._process_container_layout.addWidget(self._process_gonads_widget)

        self._top_container_layout.addWidget(self._process_container)

        self._buttons_instances_dict: dict[str, CToolButton] = {}
        for class_name, class_ref in BUTTONS_LIST.items():
            self._buttons_instances_dict[class_name] = class_ref(
                self._napari_viewer, self
            )

        for class_instance in self._buttons_instances_dict.values():
            self._process_container_layout.addWidget(
                class_instance.get_button()
            )

        second_section_separator: QFrame = QFrame(self)
        second_section_separator.setFrameShape(QFrame.Shape.HLine)
        second_section_separator.setFrameShadow(QFrame.Shadow.Sunken)
        second_section_separator.setStyleSheet("background-color: gray;")
        second_section_separator.setFixedHeight(2)
        self._top_container_layout.addWidget(second_section_separator)

        self._score_container: QWidget = QWidget()
        self._score_container_layout: QVBoxLayout = QVBoxLayout()
        self._score_container.setLayout(self._score_container_layout)

        self._score_container_title: QLabel = QLabel("Score nuclei")
        self._score_container_title.setStyleSheet("font-weight: bold")
        self._score_container_layout.addWidget(self._score_container_title)

        self._top_container_layout.addWidget(self._score_container)

        self._score_buttons_instances_dict: dict[str, CToolButton] = {}
        for class_name, class_ref in SCORE_BUTTONS_LIST.items():
            self._score_buttons_instances_dict[class_name] = class_ref(
                self._napari_viewer, self
            )

        for class_instance in self._score_buttons_instances_dict.values():
            self._score_container_layout.addWidget(class_instance.get_button())

        third_section_separator: QFrame = QFrame(self)
        third_section_separator.setFrameShape(QFrame.Shape.HLine)
        third_section_separator.setFrameShadow(QFrame.Shadow.Sunken)
        third_section_separator.setStyleSheet("background-color: gray;")
        third_section_separator.setFixedHeight(2)
        self._top_container_layout.addWidget(third_section_separator)

        self._results_container: QWidget = QWidget()
        self._results_container_layout: QVBoxLayout = QVBoxLayout()
        self._results_container.setLayout(self._results_container_layout)

        self._results_container_title: QLabel = QLabel("Results")
        self._results_container_title.setStyleSheet("font-weight: bold")
        self._results_container_layout.addWidget(self._results_container_title)

        self._top_container_layout.addWidget(self._results_container)

        self._results_buttons_instances_dict: dict[str, CToolButton] = {}
        for class_name, class_ref in RESULTS_BUTTONS_LIST.items():
            self._results_buttons_instances_dict[class_name] = class_ref(
                self._napari_viewer, self
            )

        for class_instance in self._results_buttons_instances_dict.values():
            self._results_container_layout.addWidget(
                class_instance.get_button()
            )

        self._top_container_layout.addStretch()

    ##################################################################
    #   Button connections
    ##################################################################

    def _launch_extract_channels_widget(self) -> None:
        print("launching extract channels widget")

    def _launch_stitch_gonads_widget(self) -> None:
        print("launching stitch gonads widget")

    def _launch_set_contrast_widget(self) -> None:
        setting_widget: SetContrastWidget = SetContrastWidget(
            self._napari_viewer, self
        )
        self._napari_viewer.window.add_dock_widget(
            setting_widget, name="clt Set Contrast"
        )

    def _generate_projects_reports_button_pressed(self) -> None:
        print("generating project reports")

    def _launch_pick_nuclei_widget(self) -> None:
        setting_widget = PickNucleiWidget(self, self._napari_viewer)
        self._napari_viewer.window.add_dock_widget(
            setting_widget, name="clt Pick Nuclei"
        )

    def _launch_make_multi_gonad_widget(self) -> None:
        setting_widget = MakeMultiGonadWidget(self, self._napari_viewer)
        self._napari_viewer.window.add_dock_widget(
            setting_widget, name="clt Make Multi Gonad Project"
        )

    def _launch_regions_widget(self) -> None:
        setting_widget = RegionWidget(self, self._napari_viewer)
        self._napari_viewer.window.add_dock_widget(
            setting_widget, name="clt Regions"
        )

    def _launch_score_nuclei_widget(self) -> None:
        setting_widget = ScoreNucleiWidget(self, self._napari_viewer)
        self._napari_viewer.window.add_dock_widget(
            setting_widget, name="clt Score Nuclei"
        )

    def set_image_path(self, image_path: str, image_layer: Image) -> None:
        self._image_path = image_path
        self._image_layer = image_layer
        print(f"The image path is: {self._image_path}")
        print(f"The image layer is: {self._image_layer}")

    def get_image_path(self) -> tuple[str, Image] | None:
        if self._image_path is None or self._image_layer is None:
            print("Returned none")
            return None
        print("returned the image path")
        return (self._image_path, self._image_layer)
