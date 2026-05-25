"""Left-side device list. Shows USB + tunneled iPhones, refreshes every 2 s."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.session import DeviceInfo


class DevicePanel(QWidget):
    """Periodically asks the session to refresh devices; lets user pick one."""

    device_selected = Signal(str)  # udid; emits "" when 'auto' is chosen

    REFRESH_INTERVAL_MS = 2000

    def __init__(self, session, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._session = session
        self._devices: list[DeviceInfo] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        title = QLabel("Devices")
        title.setStyleSheet("font-weight: bold;")
        layout.addWidget(title)

        self._list = QListWidget()
        self._list.itemSelectionChanged.connect(self._on_selection_changed)
        layout.addWidget(self._list, 1)

        self._refresh_btn = QPushButton("Refresh now")
        self._refresh_btn.clicked.connect(self._session.refresh_devices)
        layout.addWidget(self._refresh_btn)

        self._session.devices_changed.connect(self._on_devices_changed)

        # First refresh immediately + periodic afterwards.
        self._session.refresh_devices()
        self._timer = QTimer(self)
        self._timer.setInterval(self.REFRESH_INTERVAL_MS)
        self._timer.timeout.connect(self._session.refresh_devices)
        self._timer.start()

    def stop_polling(self) -> None:
        """Halt the periodic refresh — call from main-window closeEvent before
        the session is shut down so no late timeouts hit a dead asyncio loop."""
        self._timer.stop()

    def _on_devices_changed(self, devices: list[DeviceInfo]) -> None:
        # Preserve selection across refreshes.
        prev_udid = self.selected_udid()
        self._devices = list(devices)
        self._list.clear()

        if not devices:
            placeholder = QListWidgetItem("(no devices detected)")
            placeholder.setForeground(QColor("#888"))
            placeholder.setFlags(Qt.ItemFlag.NoItemFlags)
            self._list.addItem(placeholder)
            return

        for d in devices:
            text = f"{d.label}\n  {d.connection}{'  -  ready for DVT' if d.tunneled else ''}"
            item = QListWidgetItem(text)
            item.setData(0x100, d.udid)  # Qt.UserRole = 0x100
            if not d.tunneled:
                item.setForeground(QColor("#aaa"))
            self._list.addItem(item)

        # Restore selection (or select first by default).
        for i in range(self._list.count()):
            item = self._list.item(i)
            if item.data(0x100) == prev_udid:
                self._list.setCurrentItem(item)
                return
        self._list.setCurrentRow(0)

    def _on_selection_changed(self) -> None:
        self.device_selected.emit(self.selected_udid())

    def selected_udid(self) -> str:
        item = self._list.currentItem()
        if item is None:
            return ""
        udid = item.data(0x100)
        return udid or ""
