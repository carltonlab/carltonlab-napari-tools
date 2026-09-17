from __future__ import annotations

from collections.abc import Callable

from qtpy.QtWidgets import (
    QCheckBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from carltonlab_napari_tools.automatic_foci_count._auto_settings import (
    AutoFociCountSettings,
    AutoFociCountSettingsManager,
)


class CLTAutoFociCountSettingsWidget(QWidget):
    """Edit and save automatic foci-counting settings."""

    def __init__(
        self,
        parent: QWidget,
        status_update_callback: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(parent)

        self._status_update_callback = status_update_callback

        self._manager = AutoFociCountSettingsManager()
        self._settings = self._manager.load()

        self._layout = QVBoxLayout()
        self._layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(self._layout)

        self._title = QLabel("Automatic foci-count settings", parent=self)
        self._title.setStyleSheet("font-weight: bold")
        self._layout.addWidget(self._title)

        self._form = QFormLayout()
        self._form.setContentsMargins(0, 0, 0, 0)
        self._layout.addLayout(self._form)

        self._registration_channel = QSpinBox(parent=self)
        self._registration_channel.setRange(1, 9999)
        self._registration_channel.setValue(
            self._settings.registration_channel
        )
        self._form.addRow(
            "Registration channel",
            self._registration_channel,
        )

        self._registration_scale = QSpinBox(parent=self)
        self._registration_scale.setRange(-1, 9999)
        self._registration_scale.setSpecialValueText("Automatic")
        self._registration_scale.setValue(
            -1
            if self._settings.registration_scale is None
            else self._settings.registration_scale
        )
        self._form.addRow("Registration scale", self._registration_scale)

        self._use_gpu = QCheckBox("Use GPU", parent=self)
        self._use_gpu.setChecked(self._settings.use_gpu)
        self._form.addRow(self._use_gpu)

        self._num_workers = QSpinBox(parent=self)
        self._num_workers.setRange(0, 9999)
        self._num_workers.setSpecialValueText("Automatic")
        self._num_workers.setValue(self._settings.num_workers)
        self._form.addRow("Number of workers", self._num_workers)

        self._n_batch = QSpinBox(parent=self)
        self._n_batch.setRange(0, 9999)
        self._n_batch.setSpecialValueText("Automatic")
        self._n_batch.setValue(self._settings.n_batch)
        self._form.addRow("Batch count", self._n_batch)

        self._filter_channels_enabled = QCheckBox(
            "Filter channels",
            parent=self,
        )
        self._filter_channels_enabled.setChecked(
            self._settings.filter_channels_enabled
        )
        self._filter_channels_enabled.toggled.connect(
            self._on_filter_channels_toggled
        )
        self._form.addRow(self._filter_channels_enabled)

        self._filter_channels_row = QWidget(parent=self)
        self._filter_channels_layout = QHBoxLayout()
        self._filter_channels_layout.setContentsMargins(0, 0, 0, 0)
        self._filter_channels_row.setLayout(self._filter_channels_layout)

        self._filter_channels = QLineEdit(parent=self)
        self._filter_channels.setText(self._settings.filter_channels)
        self._filter_channels_layout.addWidget(self._filter_channels)
        self._filter_channels_layout.addWidget(
            QLabel("e.g. 1-2,4", parent=self._filter_channels_row)
        )
        self._form.addRow("Filter channels", self._filter_channels_row)

        self._minimum_ratio = QDoubleSpinBox(parent=self)
        self._minimum_ratio.setRange(0.0, 1.0)
        self._minimum_ratio.setSingleStep(0.05)
        self._minimum_ratio.setDecimals(2)
        self._minimum_ratio.setValue(
            self._settings.minimum_colocalization_intensity_ratio
        )
        self._form.addRow(
            "Minimum colocalization intensity ratio",
            self._minimum_ratio,
        )

        self._restore_defaults_button = QPushButton(
            "Restore to default",
            parent=self,
        )
        self._restore_defaults_button.clicked.connect(
            self._restore_default_settings
        )
        self._layout.addWidget(self._restore_defaults_button)

        self._save_button = QPushButton("Save settings", parent=self)
        self._save_button.clicked.connect(self._on_save)
        self._layout.addWidget(self._save_button)

        self._on_filter_channels_toggled(
            self._filter_channels_enabled.isChecked()
        )

    def _on_filter_channels_toggled(self, enabled: bool) -> None:
        self._filter_channels.setEnabled(enabled)
        self._minimum_ratio.setEnabled(enabled)

    def _restore_default_settings(self) -> None:
        self._settings = AutoFociCountSettings()
        self._registration_channel.setValue(
            self._settings.registration_channel
        )
        self._registration_scale.setValue(
            -1
            if self._settings.registration_scale is None
            else self._settings.registration_scale
        )
        self._use_gpu.setChecked(self._settings.use_gpu)
        self._num_workers.setValue(self._settings.num_workers)
        self._n_batch.setValue(self._settings.n_batch)
        self._filter_channels_enabled.setChecked(
            self._settings.filter_channels_enabled
        )
        self._filter_channels.setText(self._settings.filter_channels)
        self._minimum_ratio.setValue(
            self._settings.minimum_colocalization_intensity_ratio
        )

    def _on_save(self) -> None:
        self._settings = self.get_settings()
        self._manager.save(self._settings)
        if self._status_update_callback is not None:
            self._status_update_callback()

    def get_settings(self) -> AutoFociCountSettings:
        registration_scale = self._registration_scale.value()
        return AutoFociCountSettings(
            registration_channel=self._registration_channel.value(),
            registration_scale=(
                None if registration_scale < 0 else registration_scale
            ),
            use_gpu=self._use_gpu.isChecked(),
            num_workers=self._num_workers.value(),
            n_batch=self._n_batch.value(),
            filter_channels_enabled=(
                self._filter_channels_enabled.isChecked()
            ),
            filter_channels=self._filter_channels.text(),
            minimum_colocalization_intensity_ratio=self._minimum_ratio.value(),
        )
