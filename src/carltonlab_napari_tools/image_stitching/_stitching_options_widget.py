from __future__ import annotations

from collections.abc import Callable

from qtpy.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)


class CLTStitchingOptionsWidget(QWidget):
    """Widget containing the shared stitching configuration controls."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self._main_layout = QVBoxLayout()
        self._main_layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(self._main_layout)

        self._registration_container = QWidget(parent=self)
        self._registration_layout = QFormLayout()
        self._registration_layout.setContentsMargins(0, 0, 0, 0)
        self._registration_container.setLayout(self._registration_layout)

        self._registration_channel_spinbox = QSpinBox(
            parent=self._registration_container
        )
        self._registration_channel_spinbox.setRange(1, 9999)
        self._registration_channel_spinbox.setValue(1)

        registration_channel_widget = QWidget(
            parent=self._registration_container
        )
        registration_channel_layout = QHBoxLayout()
        registration_channel_layout.setContentsMargins(0, 0, 0, 0)
        registration_channel_widget.setLayout(registration_channel_layout)
        registration_channel_layout.addWidget(
            self._registration_channel_spinbox
        )

        registration_channel_help = QLabel(
            "?",
            parent=registration_channel_widget,
        )
        registration_channel_help.setToolTip("Channel number is 1-based.")
        registration_channel_layout.addWidget(registration_channel_help)

        self._registration_layout.addRow(
            "Registration channel",
            registration_channel_widget,
        )

        self._registration_scale_spinbox = QSpinBox(
            parent=self._registration_container
        )
        self._registration_scale_spinbox.setRange(-1, 9999)
        self._registration_scale_spinbox.setValue(-1)
        self._registration_scale_spinbox.setSpecialValueText("Automatic")
        self._registration_layout.addRow(
            "Registration scale",
            self._registration_scale_spinbox,
        )

        self._main_layout.addWidget(self._registration_container)

        self._fusion_container = QWidget(parent=self)
        self._fusion_layout = QFormLayout()
        self._fusion_layout.setContentsMargins(0, 0, 0, 0)
        self._fusion_container.setLayout(self._fusion_layout)

        self._use_gpu_checkbox = QCheckBox(
            "Use GPU",
            parent=self._fusion_container,
        )
        self._fusion_layout.addRow(self._use_gpu_checkbox)

        self._num_workers_spinbox = QSpinBox(parent=self._fusion_container)
        self._num_workers_spinbox.setRange(0, 9999)
        self._num_workers_spinbox.setValue(0)
        self._num_workers_spinbox.setSpecialValueText("Automatic")
        self._fusion_layout.addRow(
            "Number of workers",
            self._num_workers_spinbox,
        )

        self._n_batch_spinbox = QSpinBox(parent=self._fusion_container)
        self._n_batch_spinbox.setRange(0, 9999)
        self._n_batch_spinbox.setValue(0)
        self._n_batch_spinbox.setSpecialValueText("Automatic")
        self._fusion_layout.addRow(
            "Batch count",
            self._n_batch_spinbox,
        )

        self._main_layout.addWidget(self._fusion_container)

    def set_gpu_enabled(self, enabled: bool) -> None:
        self._use_gpu_checkbox.setChecked(enabled)

    def is_gpu_enabled(self) -> bool:
        return self._use_gpu_checkbox.isChecked()

    def connect_gpu_toggle(self, callback: Callable[[], None]) -> None:
        self._use_gpu_checkbox.clicked.connect(lambda _checked: callback())

    def get_stitching_options(self) -> dict[str, int | bool | None]:
        registration_scale = self._registration_scale_spinbox.value()
        num_workers = self._num_workers_spinbox.value()
        n_batch = self._n_batch_spinbox.value()

        return {
            "registration_channel": (
                self._registration_channel_spinbox.value() - 1
            ),
            "registration_scale": (
                None if registration_scale < 0 else registration_scale
            ),
            "num_workers": None if num_workers == 0 else num_workers,
            "n_batch": None if n_batch == 0 else n_batch,
            "use_gpu": self._use_gpu_checkbox.isChecked(),
        }
