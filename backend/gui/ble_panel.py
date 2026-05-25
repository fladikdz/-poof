"""Sidebar Bluetooth toggle — Start/Stop the PGP emulator + status display."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class BlePanel(QWidget):
    """Compact panel: shows BLE state and lets user start/stop the emulator.

    NB: BLE mode is independent of Teleport/Route — the user can have BLE
    advertising at the same time as DVT location spoofing. They're additive:
    DVT changes the iOS-reported location, BLE adds the "PGP accessory paired"
    signal that some games (Pokémon GO) weight more leniently.
    """

    start_requested = Signal()
    stop_requested = Signal()
    generate_test_key_requested = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        title = QLabel("BLE / PGP emulator")
        title.setStyleSheet("font-weight: bold;")
        layout.addWidget(title)

        self._status = QLabel("Stopped")
        self._status.setStyleSheet("color: #888;")
        self._status.setWordWrap(True)
        layout.addWidget(self._status)

        row = QHBoxLayout()
        self._start_btn = QPushButton("Start")
        self._start_btn.clicked.connect(self.start_requested)
        self._stop_btn = QPushButton("Stop")
        self._stop_btn.setEnabled(False)
        self._stop_btn.clicked.connect(self.stop_requested)
        row.addWidget(self._start_btn)
        row.addWidget(self._stop_btn)
        layout.addLayout(row)

        # Helper for when master key file is missing — generates 16 random
        # bytes as a placeholder so user can test that BLE peripheral works
        # at all on their hardware. NOT a real PGP key — Pokemon GO server
        # will still reject (see docs/anyto_pgp_key_strategy in memory).
        self._gen_key_btn = QPushButton("Generate test key (placeholder)")
        self._gen_key_btn.clicked.connect(self.generate_test_key_requested)
        self._gen_key_btn.setStyleSheet("font-size: 10pt;")
        layout.addWidget(self._gen_key_btn)

        hint = QLabel(
            "Advertises a virtual 'Pokemon GO Plus' over Bluetooth LE. "
            "Requires peripheral-capable BT adapter. Without a real PGP "
            "cert key (see docs) Pokemon GO server validation will reject; "
            "useful for testing or less strict apps."
        )
        hint.setStyleSheet("color: #888; font-size: 10pt;")
        hint.setWordWrap(True)
        layout.addWidget(hint)

    # ---- inbound -----------------------------------------------------

    def set_state(self, state: str) -> None:
        """`state` from SpoofSession.ble_state_changed signal."""
        if state == "stopped":
            self._status.setText("Stopped")
            self._status.setStyleSheet("color: #888;")
            self._start_btn.setEnabled(True)
            self._stop_btn.setEnabled(False)
        elif state == "starting":
            self._status.setText("Starting...")
            self._status.setStyleSheet("color: #d09030;")
            self._start_btn.setEnabled(False)
            self._stop_btn.setEnabled(False)
        elif state == "advertising":
            self._status.setText("Advertising as 'Pokemon GO Plus'")
            self._status.setStyleSheet("color: #4ec9b0; font-weight: bold;")
            self._start_btn.setEnabled(False)
            self._stop_btn.setEnabled(True)
        elif state.startswith("error"):
            self._status.setText(state)
            self._status.setStyleSheet("color: #d04030;")
            self._start_btn.setEnabled(True)
            self._stop_btn.setEnabled(False)
        else:
            self._status.setText(state)
            self._status.setStyleSheet("color: #888;")
