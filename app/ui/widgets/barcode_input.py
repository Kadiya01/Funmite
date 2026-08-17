"""Scanner-friendly text input.

A USB barcode scanner behaves like a keyboard: it types the barcode and ends
with an Enter keypress. This widget captures that and emits ``barcode_scanned``
with the cleaned value, then clears and refocuses so the next scan starts clean.
Used on the POS screen (Phase 05) and wherever a scan needs to find a product.
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QLineEdit

from app.barcode.scanner import normalize_scan


class BarcodeScanInput(QLineEdit):
    """QLineEdit that emits ``barcode_scanned(str)`` when a scan completes."""

    barcode_scanned = Signal(str)

    def __init__(self, parent=None, placeholder: str = "Scan barcode...") -> None:
        super().__init__(parent)
        self.setPlaceholderText(placeholder)
        self.returnPressed.connect(self._submit_scan)

    def _submit_scan(self) -> None:
        value = normalize_scan(self.text())
        self.clear()
        self.setFocus()
        if value:
            self.barcode_scanned.emit(value)
