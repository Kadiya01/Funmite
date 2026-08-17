"""Receipt printer abstraction (Phase 05).

POS business logic must not depend on printer code, so every printer in this
package implements ``ReceiptPrinter.print_receipt`` and nothing else. Phase 11
adds the physical ESC/POS USB transport for the Xprinter; until then the
default is ``NullPrinter`` (a sale is never lost because printing fails).

A successful sale is stored first and printed afterwards; if printing raises,
the caller shows a reprint option instead of touching the sale record.
"""

from __future__ import annotations

from pathlib import Path

from app.printing.escpos import EscPosRenderer
from app.printing.receipt import ReceiptData


class ReceiptPrinter:
    """Interface for anything that can print a receipt."""

    def print_receipt(self, receipt: ReceiptData) -> None:
        raise NotImplementedError


class NullPrinter(ReceiptPrinter):
    """No-op printer used until hardware is configured (Phase 11)."""

    def print_receipt(self, receipt: ReceiptData) -> None:
        return None


class InMemoryPrinter(ReceiptPrinter):
    """Records printed receipts in memory (testing / diagnostics)."""

    def __init__(self) -> None:
        self.receipts: list[ReceiptData] = []

    def print_receipt(self, receipt: ReceiptData) -> None:
        self.receipts.append(receipt)


class EscPosFilePrinter(ReceiptPrinter):
    """Renders ESC/POS bytes and writes them to a file or binary stream.

    Useful for development and for producing a printable file without a
    connected device. The physical USB device writer lands in Phase 11.
    """

    def __init__(self, path: Path | str, *, renderer: EscPosRenderer | None = None) -> None:
        self.path = Path(path)
        self.renderer = renderer or EscPosRenderer()

    def print_receipt(self, receipt: ReceiptData) -> None:
        self.path.write_bytes(self.renderer.render(receipt))
