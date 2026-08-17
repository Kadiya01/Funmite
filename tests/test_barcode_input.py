"""Barcode scan input widget tests (Phase 03)."""

from __future__ import annotations

from PySide6.QtWidgets import QLineEdit

from app.ui.widgets import BarcodeScanInput


def test_emit_on_enter(qtbot):
    widget = BarcodeScanInput(placeholder="Scan...")
    qtbot.addWidget(widget)

    widget.setText("1234567890128")
    with qtbot.waitSignal(widget.barcode_scanned, timeout=1000) as signal:
        widget.returnPressed.emit()
    assert signal.args == ["1234567890128"]


def test_scan_trims_framing_whitespace_and_clears(qtbot):
    widget = BarcodeScanInput()
    qtbot.addWidget(widget)

    widget.setText("  1234567890128\t")
    with qtbot.waitSignal(widget.barcode_scanned, timeout=1000) as signal:
        widget.returnPressed.emit()
    assert signal.args == ["1234567890128"]
    assert widget.text() == ""


def test_empty_scan_does_not_emit(qtbot):
    widget = BarcodeScanInput()
    qtbot.addWidget(widget)
    widget.setText("   ")
    with qtbot.assertNotEmitted(widget.barcode_scanned, wait=200):
        widget.returnPressed.emit()
    assert widget.text() == ""


def test_is_a_line_edit(qtbot):
    widget = BarcodeScanInput()
    qtbot.addWidget(widget)
    assert isinstance(widget, QLineEdit)
