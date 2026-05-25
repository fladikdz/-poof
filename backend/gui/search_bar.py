"""Top-of-sidebar address search + result list."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class SearchBar(QWidget):
    """Address search via Nominatim. Emits chosen result coordinates."""

    search_submitted = Signal(str)             # query string
    result_chosen = Signal(float, float, str)  # lat, lon, name
    route_here_chosen = Signal(float, float, str)  # lat, lon, name -- "route from current spoof to here"

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        row = QHBoxLayout()
        row.setSpacing(4)
        self._input = QLineEdit()
        self._input.setPlaceholderText("Search address or place name...")
        self._input.returnPressed.connect(self._on_submit)
        self._btn = QPushButton("Go")
        self._btn.setMaximumWidth(48)
        self._btn.clicked.connect(self._on_submit)
        row.addWidget(self._input, 1)
        row.addWidget(self._btn)
        layout.addLayout(row)

        self._results = QListWidget()
        self._results.setMaximumHeight(120)
        self._results.setVisible(False)
        self._results.itemDoubleClicked.connect(self._on_double_click)
        layout.addWidget(self._results)

        # Per-result actions row (visible only when something selected).
        actions = QHBoxLayout()
        actions.setSpacing(4)
        self._go_btn = QPushButton("Teleport here")
        self._go_btn.setEnabled(False)
        self._go_btn.clicked.connect(self._on_teleport_clicked)
        self._route_btn = QPushButton("Route from here →")
        self._route_btn.setEnabled(False)
        self._route_btn.setToolTip("Build a road route from your current spoof position to this place.")
        self._route_btn.clicked.connect(self._on_route_clicked)
        actions.addWidget(self._go_btn, 1)
        actions.addWidget(self._route_btn, 1)
        layout.addLayout(actions)

        self._results.itemSelectionChanged.connect(self._on_selection_changed)

    # ---- inbound ------------------------------------------------------

    def set_results(self, results) -> None:
        """Receive a list[GeocodeResult] from the session."""
        self._results.clear()
        for r in results:
            item = QListWidgetItem(r.name)
            item.setToolTip(r.name)
            item.setData(0x100, (r.latitude, r.longitude, r.name))
            self._results.addItem(item)
        self._results.setVisible(bool(results))
        if not results:
            placeholder = QLabel("No results.")
            placeholder.setStyleSheet("color: #888;")
        self._go_btn.setEnabled(False)
        self._route_btn.setEnabled(False)

    # ---- handlers -----------------------------------------------------

    def _on_submit(self) -> None:
        query = self._input.text().strip()
        if query:
            self.search_submitted.emit(query)

    def _on_selection_changed(self) -> None:
        has = self._results.currentItem() is not None
        self._go_btn.setEnabled(has)
        self._route_btn.setEnabled(has)

    def _on_double_click(self, item: QListWidgetItem) -> None:
        lat, lon, name = item.data(0x100)
        self.result_chosen.emit(lat, lon, name)

    def _on_teleport_clicked(self) -> None:
        item = self._results.currentItem()
        if item is None:
            return
        lat, lon, name = item.data(0x100)
        self.result_chosen.emit(lat, lon, name)

    def _on_route_clicked(self) -> None:
        item = self._results.currentItem()
        if item is None:
            return
        lat, lon, name = item.data(0x100)
        self.route_here_chosen.emit(lat, lon, name)
