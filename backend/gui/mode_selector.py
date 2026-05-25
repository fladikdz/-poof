"""Top-of-sidebar mode picker: Teleport / Route."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QButtonGroup, QHBoxLayout, QPushButton, QWidget


class ModeSelector(QWidget):
    mode_changed = Signal(str)  # 'teleport' | 'route'

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self._buttons = QButtonGroup(self)
        self._buttons.setExclusive(True)

        for mode in ("teleport", "route"):
            btn = QPushButton(mode.capitalize())
            btn.setCheckable(True)
            btn.setProperty("mode", mode)
            self._buttons.addButton(btn)
            layout.addWidget(btn, 1)
        self._buttons.buttons()[0].setChecked(True)
        self._buttons.buttonToggled.connect(self._on_toggled)

    def _on_toggled(self, button, checked: bool) -> None:
        if not checked:
            return
        self.mode_changed.emit(button.property("mode"))

    def current_mode(self) -> str:
        return self._buttons.checkedButton().property("mode")

    def set_mode(self, mode: str) -> None:
        for btn in self._buttons.buttons():
            if btn.property("mode") == mode and not btn.isChecked():
                btn.setChecked(True)
                return
