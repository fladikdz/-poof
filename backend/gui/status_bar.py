"""Bottom status bar — current spoof coords + Clear button + last log line."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QWidget,
)

from core.session import SpoofState


class StatusBar(QWidget):
    clear_requested = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)

        self._spoof_label = QLabel("No active spoof.")
        self._spoof_label.setStyleSheet("font-weight: bold;")
        layout.addWidget(self._spoof_label, 1)

        self._log_label = QLabel("")
        self._log_label.setStyleSheet("color: #888;")
        self._log_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        layout.addWidget(self._log_label, 2)

        self._clear_btn = QPushButton("Clear")
        self._clear_btn.setEnabled(False)
        self._clear_btn.clicked.connect(self.clear_requested)
        layout.addWidget(self._clear_btn)

    def set_spoof_state(self, state: Optional[SpoofState]) -> None:
        if state is None:
            self._spoof_label.setText("No active spoof.")
            self._clear_btn.setEnabled(False)
        else:
            self._spoof_label.setText(
                f"Spoofing {state.udid}: {state.latitude:.6f}, {state.longitude:.6f}"
            )
            self._clear_btn.setEnabled(True)

    def set_log_message(self, text: str) -> None:
        self._log_label.setText(text)
