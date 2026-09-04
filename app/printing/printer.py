"""Receipt printer abstraction (Phase 05 / Phase 12-F5).

POS business logic must not depend on printer code, so every printer in this
package implements ``ReceiptPrinter.print_receipt`` and nothing else.

A successful sale is stored (committed) first and printed afterwards; if
printing raises, the caller shows a reprint option instead of touching the
sale record — a printer failure never loses or rolls back a completed sale.

Phase 12-F5 adds the physical Windows printer transport (``WindowsPrinter``)
which sends the rendered ESC/POS bytes to a configured printer through the
Windows print spooler (``win32print``). ``win32print`` is imported lazily so
that non-Windows development and automated tests never need it installed.
Until a printer is configured the safe default is ``NullPrinter``.

Each printer exposes a :class:`PrinterState` describing the last print attempt
so the UI can distinguish "printed", "not configured", "printer unavailable"
and "printing failed" — it must never report success falsely.
"""

from __future__ import annotations

import json
from enum import Enum, auto
from pathlib import Path
from typing import Any

from app.printing.escpos import EscPosRenderer
from app.printing.receipt import ReceiptData


class PrinterState(Enum):
    """Outcome of a print attempt, used by the UI for accurate feedback."""

    NOT_CONFIGURED = auto()
    AVAILABLE = auto()
    UNAVAILABLE = auto()
    FAILED = auto()


class ReceiptPrintError(Exception):
    """Base class for receipt printing errors."""


class PrinterNotConfiguredError(ReceiptPrintError):
    """No printer is configured; printing is a safe no-op (never claim success)."""


class PrinterUnavailableError(ReceiptPrintError):
    """The configured printer could not be opened (off, disconnected, missing)."""


class PrinterWriteFailureError(ReceiptPrintError):
    """The printer accepted the job but writing the bytes failed."""


class ReceiptPrinter:
    """Interface for anything that can print a receipt."""

    state: PrinterState = PrinterState.NOT_CONFIGURED

    def print_receipt(self, receipt: ReceiptData) -> None:
        raise NotImplementedError


class NullPrinter(ReceiptPrinter):
    """Safe fallback used when no printer is configured (Phase 11 default).

    Printing is a no-op and is reported as *not configured* so the caller never
    shows a false "receipt printed" message. It raises :class:`PrinterNotConfiguredError`
    so the POS can tell the difference between "no printer" and a real failure.
    """

    state: PrinterState = PrinterState.NOT_CONFIGURED

    def print_receipt(self, receipt: ReceiptData) -> None:
        self.state = PrinterState.NOT_CONFIGURED
        raise PrinterNotConfiguredError("No printer is configured.")


class InMemoryPrinter(ReceiptPrinter):
    """Records printed receipts in memory (testing / diagnostics)."""

    state: PrinterState = PrinterState.NOT_CONFIGURED

    def __init__(self) -> None:
        self.receipts: list[ReceiptData] = []

    def print_receipt(self, receipt: ReceiptData) -> None:
        self.receipts.append(receipt)
        self.state = PrinterState.AVAILABLE


class EscPosFilePrinter(ReceiptPrinter):
    """Renders ESC/POS bytes and writes them to a file or binary stream.

    Useful for development and for producing a printable file without a
    connected device.
    """

    state: PrinterState = PrinterState.NOT_CONFIGURED

    def __init__(self, path: Path | str, *, renderer: EscPosRenderer | None = None) -> None:
        self.path = Path(path)
        self.renderer = renderer or EscPosRenderer()

    def print_receipt(self, receipt: ReceiptData) -> None:
        self.path.write_bytes(self.renderer.render(receipt))
        self.state = PrinterState.AVAILABLE


class WindowsPrinter(ReceiptPrinter):
    """Sends already-rendered ESC/POS bytes to a Windows thermal printer.

    Uses the Windows print spooler (``win32print``) over a RAW data type so the
    exact ESC/POS bytes reach the printer. ``win32print`` is imported lazily on
    first use so non-Windows environments and tests (which inject a fake
    spooler) never require the dependency to be installed.

    Printing state is recorded in ``self.state`` and failures are surfaced as
    specific :class:`ReceiptPrintError` subclasses so the caller can keep the
    completed sale and report accurately. Any spooler exception is caught and
    re-raised; it never crashes the application or loses a sale.
    """

    state: PrinterState = PrinterState.NOT_CONFIGURED

    def __init__(
        self,
        printer_name: str,
        *,
        renderer: EscPosRenderer | None = None,
        win32print: Any | None = None,
    ) -> None:
        self.printer_name = printer_name
        self.renderer = renderer or EscPosRenderer()
        self._win32print = win32print

    def _spooler(self):
        if self._win32print is None:
            import win32print

            self._win32print = win32print
        return self._win32print

    def print_receipt(self, receipt: ReceiptData) -> None:
        data = self.renderer.render(receipt)
        spooler = self._spooler()

        try:
            handle = spooler.OpenPrinter(self.printer_name)
        except Exception as exc:  # noqa: BLE001 - spooler raises arbitrary exceptions
            self.state = PrinterState.UNAVAILABLE
            raise PrinterUnavailableError(
                f"Printer '{self.printer_name}' is unavailable: {exc}"
            ) from exc

        try:
            try:
                spooler.StartDocPrinter(handle, 1, ("Receipt", None, "RAW"))
            except Exception as exc:  # noqa: BLE001
                self.state = PrinterState.UNAVAILABLE
                raise PrinterUnavailableError(
                    f"Printer '{self.printer_name}' could not accept the print job: {exc}"
                ) from exc
            try:
                spooler.StartPagePrinter(handle)
            except Exception as exc:  # noqa: BLE001
                self.state = PrinterState.UNAVAILABLE
                raise PrinterUnavailableError(
                    f"Printer '{self.printer_name}' could not accept the print job: {exc}"
                ) from exc
            try:
                written = spooler.WritePrinter(handle, data)
                if written != len(data):
                    self.state = PrinterState.FAILED
                    raise PrinterWriteFailureError(
                        f"Printer '{self.printer_name}' wrote {written} of {len(data)} bytes."
                    )
                spooler.EndPagePrinter(handle)
                spooler.EndDocPrinter(handle)
            except PrinterWriteFailureError:
                raise
            except Exception as exc:  # noqa: BLE001
                self.state = PrinterState.FAILED
                raise PrinterWriteFailureError(
                    f"Writing to printer '{self.printer_name}' failed: {exc}"
                ) from exc
        finally:
            try:
                spooler.ClosePrinter(handle)
            except Exception as exc:  # noqa: BLE001
                self.state = PrinterState.FAILED
                raise PrinterWriteFailureError(
                    f"Closing printer '{self.printer_name}' failed: {exc}"
                ) from exc

        self.state = PrinterState.AVAILABLE


PRINTER_CONFIG_FILE = "printer_config.json"


class PrinterConfigStore:
    """Persists the printer name chosen through the Settings UI.

    The Settings-UI choice is the *primary* printer configuration; it wins over
    the ``FUNMITE_PRINTER_NAME`` environment fallback. The stored file lives in
    the application data directory (next to the database) so it survives runs
    and is fully local / offline.
    """

    def __init__(self, data_dir: Path | str) -> None:
        self.path = Path(data_dir) / PRINTER_CONFIG_FILE

    def load(self) -> str:
        if not self.path.exists():
            return ""
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            return str(raw.get("printer_name", "") or "")
        except (json.JSONDecodeError, OSError, ValueError):
            return ""

    def save(self, printer_name: str) -> None:
        self.path.write_text(
            json.dumps({"printer_name": printer_name or ""}),
            encoding="utf-8",
        )

    def clear(self) -> None:
        if self.path.exists():
            self.path.unlink()


def resolve_printer_name(
    settings: Any, store: PrinterConfigStore | None = None
) -> str:
    """Resolve the effective printer name (Settings UI over env fallback)."""
    store = store or PrinterConfigStore(settings.data_dir)
    ui_name = store.load().strip()
    if ui_name:
        return ui_name
    return (getattr(settings, "printer_name", "") or "").strip()


def create_printer(
    settings: Any, store: PrinterConfigStore | None = None
) -> ReceiptPrinter:
    """Create the production printer for the given settings.

    Returns ``NullPrinter`` (safe fallback, never falsely prints) when no
    printer is configured, otherwise a ``WindowsPrinter`` for the resolved name.
    """
    name = resolve_printer_name(settings, store)
    if not name:
        return NullPrinter()
    return WindowsPrinter(name)
