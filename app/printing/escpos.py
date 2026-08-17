"""ESC/POS command rendering for an 80mm thermal receipt printer.

This module produces the raw bytes a thermal printer understands; it has no
dependency on the printer hardware. Sending the bytes to the physical USB
Xprinter is a Phase 11 hardware concern (the printer abstraction lives in
``app/printing/printer.py``).

Commands used:

- ``ESC @``        initialize the printer
- ``ESC t n``      select code page PC437 (``n=0``)
- ``ESC a n``      alignment: 0 left, 1 centre, 2 right
- ``ESC E n``      emphasise on/off
- ``GS k 73``      print a Code128 barcode followed by data and NUL
- ``GS V A``       partial cut

The naira sign (U+20A6) is not part of PC437, so amounts are rendered with a
plain ``N`` in the ESC/POS output (receipt branding remains an open decision).
"""

from __future__ import annotations

from app.printing.receipt import ReceiptData, render_receipt_text
from app.utils.formatting import NAIRA

INIT = b"\x1b\x40"
CODE_PAGE_PC437 = b"\x1b\x74\x00"
ALIGN_CENTRE = b"\x1b\x61\x01"
ALIGN_LEFT = b"\x1b\x61\x00"
EMPHASIS_ON = b"\x1b\x45\x01"
EMPHASIS_OFF = b"\x1b\x45\x00"
CUT_PARTIAL = b"\x1d\x56\x41"


def _encode_text(text: str) -> bytes:
    """Encode one receipt line for PC437, replacing ₦ with ``N``."""
    return text.replace(NAIRA, "N").encode("cp437", errors="replace")


class EscPosRenderer:
    """Renders a ``ReceiptData`` into ESC/POS bytes for an 80mm printer."""

    def render(self, receipt: ReceiptData) -> bytes:
        out = bytearray(INIT)
        out += CODE_PAGE_PC437

        header_lines = render_receipt_text(receipt)
        first_blank = next(
            (index for index, line in enumerate(header_lines) if not line),
            len(header_lines),
        )
        body_start = min(first_blank + 1, len(header_lines))

        out += ALIGN_CENTRE
        for line in header_lines[:first_blank]:
            out += _encode_text(line)
            out += b"\x0a"
        out += ALIGN_LEFT

        for line in header_lines[body_start:]:
            out += _encode_text(line)
            out += b"\x0a"

        out += self._barcode(receipt.barcode)
        out += _encode_text(receipt.barcode)
        out += b"\x0a"
        out += b"\x0a\x0a\x0a"
        out += CUT_PARTIAL
        return bytes(out)

    @staticmethod
    def _barcode(value: str) -> bytes:
        """Code128 barcode command (``GS k 73``) for ``value``."""
        if not value:
            return b""
        data = value.encode("ascii", errors="ignore")
        return b"\x1d\x6b\x49" + data + b"\x00"
