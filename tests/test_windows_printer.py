"""Windows thermal printer tests (Phase 12-F5).

``WindowsPrinter`` sends the already-rendered ESC/POS bytes to the Windows
print spooler. ``win32print`` is never required in tests — a fake spooler
records every call and can be made to fail at open/write/close. Also covers
printer configuration precedence (Settings UI over ``FUNMITE_PRINTER_NAME``
environment fallback) and the safe ``NullPrinter`` fallback.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.config import Settings
from app.printing.escpos import EscPosRenderer
from app.printing.printer import (
    NullPrinter,
    PrinterConfigStore,
    PrinterNotConfiguredError,
    PrinterState,
    PrinterUnavailableError,
    PrinterWriteFailureError,
    WindowsPrinter,
    create_printer,
    resolve_printer_name,
)
from app.printing.receipt import ReceiptData, ReceiptLine


class FakeSpooler:
    """In-memory stand-in for the ``win32print`` module."""

    def __init__(self) -> None:
        self.calls: list[tuple] = []
        self.written = b""
        self.fail_open = False
        self.fail_start_doc = False
        self.fail_write = False
        self.fail_close = False
        self.short_write = False
        self.open_exc = OSError("printer not found")
        self.write_exc = OSError("write failed")
        self.close_exc = OSError("close failed")

    def OpenPrinter(self, name):
        self.calls.append(("OpenPrinter", name))
        if self.fail_open:
            raise self.open_exc
        self._handle = object()
        return self._handle

    def StartDocPrinter(self, handle, level, docinfo):
        self.calls.append(("StartDocPrinter", level, docinfo))
        if self.fail_start_doc:
            raise OSError("spooler busy")

    def StartPagePrinter(self, handle):
        self.calls.append(("StartPagePrinter",))

    def WritePrinter(self, handle, data):
        self.calls.append(("WritePrinter",))
        if self.fail_write:
            raise self.write_exc
        if self.short_write:
            return 0
        self.written += bytes(data)
        return len(data)

    def EndPagePrinter(self, handle):
        self.calls.append(("EndPagePrinter",))

    def EndDocPrinter(self, handle):
        self.calls.append(("EndDocPrinter",))

    def ClosePrinter(self, handle):
        self.calls.append(("ClosePrinter",))
        if self.fail_close:
            raise self.close_exc


def _receipt() -> ReceiptData:
    return ReceiptData(
        receipt_no="FUN-20260101-001",
        sale_date=__import__("datetime").datetime(2026, 1, 1, 12, 0),
        cashier_name="Admin User",
        customer_name="Amina Yusuf",
        lines=[ReceiptLine(
            name="Ladies Gown", quantity=1,
            unit_price=Decimal("35000"), total=Decimal("35000"),
        )],
        subtotal=Decimal("35000"),
        discount_type=None,
        discount_value=Decimal("0"),
        discount_amount=Decimal("0"),
        total=Decimal("35000"),
        payment_method="POS",
        payment_label="BANK POS",
        amount_paid=Decimal("35000"),
        barcode="FUN-20260101-001",
    )


def _printer(name="Xprinter", spooler=None) -> WindowsPrinter:
    return WindowsPrinter(name, win32print=spooler or FakeSpooler())


# --- WindowsPrinter -------------------------------------------------------- #


def test_windows_printer_success_opens_documents_writes_closes():
    spooler = FakeSpooler()
    printer = _printer(spooler=spooler)
    renderer = EscPosRenderer()
    expected = renderer.render(_receipt())

    printer.print_receipt(_receipt())

    assert spooler.written == expected
    names = [call[0] for call in spooler.calls]
    assert names == [
        "OpenPrinter",
        "StartDocPrinter",
        "StartPagePrinter",
        "WritePrinter",
        "EndPagePrinter",
        "EndDocPrinter",
        "ClosePrinter",
    ]
    assert spooler.calls[0][1] == "Xprinter"
    assert printer.state == PrinterState.AVAILABLE


def test_windows_printer_passes_correct_spooler_bytes():
    spooler = FakeSpooler()
    printer = _printer(spooler=spooler)
    receipt = _receipt()
    rendered = EscPosRenderer().render(receipt)

    printer.print_receipt(receipt)

    assert spooler.written == rendered
    assert spooler.written.startswith(b"\x1b\x40")  # ESC @ init
    assert b"FUNMITE CLOTHING & BEYOND" in spooler.written


def test_open_failure_is_unavailable_and_raises():
    spooler = FakeSpooler()
    spooler.fail_open = True
    printer = _printer(spooler=spooler)

    with pytest.raises(PrinterUnavailableError):
        printer.print_receipt(_receipt())

    assert printer.state == PrinterState.UNAVAILABLE
    assert not any(call[0] == "ClosePrinter" for call in spooler.calls)


def test_write_failure_is_failed_and_still_closes():
    spooler = FakeSpooler()
    spooler.fail_write = True
    printer = _printer(spooler=spooler)

    with pytest.raises(PrinterWriteFailureError):
        printer.print_receipt(_receipt())

    assert printer.state == PrinterState.FAILED
    assert spooler.calls[-1][0] == "ClosePrinter"


def test_short_write_is_failed():
    spooler = FakeSpooler()
    spooler.short_write = True
    printer = _printer(spooler=spooler)

    with pytest.raises(PrinterWriteFailureError):
        printer.print_receipt(_receipt())

    assert printer.state == PrinterState.FAILED
    assert spooler.calls[-1][0] == "ClosePrinter"


def test_close_failure_is_failed():
    spooler = FakeSpooler()
    spooler.fail_close = True
    printer = _printer(spooler=spooler)

    with pytest.raises(PrinterWriteFailureError):
        printer.print_receipt(_receipt())

    assert printer.state == PrinterState.FAILED


def test_start_doc_failure_is_reported():
    spooler = FakeSpooler()
    spooler.fail_start_doc = True
    printer = _printer(spooler=spooler)

    with pytest.raises(PrinterUnavailableError):
        printer.print_receipt(_receipt())

    assert spooler.calls[-1][0] == "ClosePrinter"


def test_spooler_exceptions_do_not_crash():
    spooler = FakeSpooler()
    spooler.fail_write = True
    printer = _printer(spooler=spooler)
    try:
        printer.print_receipt(_receipt())
    except PrinterWriteFailureError:
        pass
    assert printer.state == PrinterState.FAILED


def test_null_printer_reports_not_configured():
    printer = NullPrinter()
    with pytest.raises(PrinterNotConfiguredError):
        printer.print_receipt(_receipt())
    assert printer.state == PrinterState.NOT_CONFIGURED


# --- configuration --------------------------------------------------------- #


def test_settings_printer_name_environment_fallback(monkeypatch):
    monkeypatch.setenv("FUNMITE_PRINTER_NAME", "Xprinter XP-370B")
    assert Settings().printer_name == "Xprinter XP-370B"


def test_settings_printer_name_default_empty(monkeypatch):
    monkeypatch.delenv("FUNMITE_PRINTER_NAME", raising=False)
    assert Settings().printer_name == ""


def test_resolve_uses_settings_ui_value_over_environment(monkeypatch, tmp_path):
    monkeypatch.setenv("FUNMITE_PRINTER_NAME", "Env Printer")
    store = PrinterConfigStore(tmp_path)
    store.save("UI Printer")
    settings = Settings()
    assert resolve_printer_name(settings, store) == "UI Printer"


def test_resolve_falls_back_to_environment(tmp_path):
    store = PrinterConfigStore(tmp_path)
    settings = Settings(printer_name="Env Printer")
    assert resolve_printer_name(settings, store) == "Env Printer"


def test_resolve_empty_when_nothing_configured(monkeypatch, tmp_path):
    monkeypatch.delenv("FUNMITE_PRINTER_NAME", raising=False)
    store = PrinterConfigStore(tmp_path)
    assert resolve_printer_name(Settings(), store) == ""


def test_printer_config_store_roundtrip(tmp_path):
    store = PrinterConfigStore(tmp_path)
    assert store.load() == ""
    store.save("Xprinter XP-370B")
    assert store.load() == "Xprinter XP-370B"
    store.save("")
    assert store.load() == ""


def test_printer_config_store_clear(tmp_path):
    store = PrinterConfigStore(tmp_path)
    store.save("Xprinter")
    store.clear()
    assert store.load() == ""


def test_create_printer_returns_null_when_unconfigured(monkeypatch, tmp_path):
    monkeypatch.delenv("FUNMITE_PRINTER_NAME", raising=False)
    printer = create_printer(Settings(printer_name=""), PrinterConfigStore(tmp_path))
    assert isinstance(printer, NullPrinter)


def test_create_printer_returns_windows_printer_from_ui(tmp_path):
    store = PrinterConfigStore(tmp_path)
    store.save("UI Printer")
    printer = create_printer(Settings(printer_name="Env Printer"), store)
    assert isinstance(printer, WindowsPrinter)
    assert printer.printer_name == "UI Printer"


def test_create_printer_returns_windows_printer_from_env(tmp_path):
    printer = create_printer(Settings(printer_name="Env Printer"), PrinterConfigStore(tmp_path))
    assert isinstance(printer, WindowsPrinter)
    assert printer.printer_name == "Env Printer"