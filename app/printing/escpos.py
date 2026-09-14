"""ESC/POS command rendering for an 80mm thermal receipt printer (Phase 05 / F5).

This module produces the raw bytes a thermal printer understands; it has no
dependency on the printer hardware. Sending the bytes to the physical USB
Xprinter is a Phase 11 hardware concern (the printer abstraction lives in
``app/printing/printer.py``).

Commands used:

- ``ESC @``        initialize the printer
- ``ESC t n``      select code page PC437 (``n=0``)
- ``ESC a n``      alignment: 0 left, 1 centre, 2 right
- ``ESC E n``      emphasise on/off
- ``GS v 0``       raster (bit) image — used for the Funmite logo
- ``GS k 73``      print a Code128 barcode followed by data and NUL
- ``GS V A``       partial cut
The naira sign (U+20A6) is not part of PC437, so the ESC/POS stream always

renders amounts with a plain ``NGN``; the human-readable text layout uses the

same ``NGN`` so the preview matches the printed receipt exactly.
F5 branding (approved): the receipt header, contact block, transaction block,
item columns, emphasised totals, payment section, Code128 barcode and footer
are produced by ``render_receipt_text`` in ``app/printing/receipt.py``; this
renderer emits the logo first (as a centred monochrome bitmap) and then the
canonical text lines with per-line alignment and emphasis.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage

from app.printing.receipt import (
    PRINTABLE_WIDTH,
    ReceiptData,
    _centered_lines,
    _wrap_name,
    render_receipt_text,
)

INIT = b"\x1b\x40"
CODE_PAGE_PC437 = b"\x1b\x74\x00"
ALIGN_CENTRE = b"\x1b\x61\x01"
ALIGN_LEFT = b"\x1b\x61\x00"
ALIGN_RIGHT = b"\x1b\x61\x02"
EMPHASIS_ON = b"\x1b\x45\x01"
EMPHASIS_OFF = b"\x1b\x45\x00"
CUT_FULL = b"\x1d\x56\x00"
CUT_PARTIAL = b"\x1d\x56\x41"
CUT_FEED_LINES = 5

# ── Logo defaults ─────────────────────────────────────────────────────────
DEFAULT_LOGO_PATH = Path(__file__).resolve().parent.parent / "assets" / "logo.png"
PRINTABLE_DOTS = 576          # 80mm at 8 dots/mm, printable ~72mm
LOGO_MAX_WIDTH = 520          # dots (kept subordinate to the receipt)
LOGO_MAX_HEIGHT = 300         # dots (~37mm tall at 203dpi; prominent header)
LOGO_THRESHOLD = 140          # luminance < threshold → printed (ink)
LOGO_ALPHA_THRESHOLD = 128    # alpha < threshold → treated as paper (no ink)

_LOGO_CACHE: dict[tuple, bytes] = {}


def _encode_text(text: str) -> bytes:
    """Encode one receipt line for PC437, replacing ₦ with ``N``."""
    return text.replace("\u20a6", "NGN").encode("cp437", errors="replace")


# ── Logo → monochrome raster (GS v 0) ────────────────────────────────────


def _logo_raster(
    path: Path,
    max_width: int,
    max_height: int,
    threshold: int,
) -> tuple[bytes | None, int, int]:
    """Rasterise *path* into 1-bit-per-pixel row data.

    Pixels with luminance below *threshold* are printed as ink, except
    pixels whose alpha is below ``LOGO_ALPHA_THRESHOLD`` (transparent areas
    become paper).  Returns ``(None, 0, 0)`` when the file cannot be loaded.
    The returned bytes are the natural raster (MSB-first per row, no
    horizontal margin).
    """
    image = QImage(str(path))
    if image.isNull():
        return None, 0, 0
    scaled = image.scaled(
        max_width,
        max_height,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )
    rgb = scaled.convertToFormat(QImage.Format.Format_ARGB32)
    w, h = rgb.width(), rgb.height()
    raw = bytes(rgb.constBits())
    stride = rgb.bytesPerLine()

    out = bytearray()
    for y in range(h):
        row = raw[y * stride : (y + 1) * stride]
        byte = 0
        bit = 0
        for x in range(w):
            offset = x * 4
            b = row[offset]
            g = row[offset + 1]
            r = row[offset + 2]
            a = row[offset + 3]
            lum = 0.299 * r + 0.587 * g + 0.114 * b
            byte = (byte << 1) | (1 if a >= LOGO_ALPHA_THRESHOLD and lum < threshold else 0)
            bit += 1
            if bit == 8:
                out.append(byte)
                byte = 0
                bit = 0
        if bit:
            out.append(byte << (8 - bit))
    return bytes(out), w, h


def _centre_raster(raster: bytes, w: int, h: int, printer_dots: int) -> tuple[bytes, int]:
    """Pad *raster* so it is horizontally centred within ``printer_dots``.

    Left-padding inside the raster data makes the logo centred on every
    printer without relying on alignment commands for raster images.
    """
    left = max(0, (printer_dots - w) // 2)

    def _pad_row(row_bytes: bytes, row_w: int) -> bytearray:
        bits: list[int] = [0] * left
        for byte in row_bytes:
            for i in range(8):
                bits.append((byte >> (7 - i)) & 1)
        bits = bits[: printer_dots]
        bits.extend([0] * max(0, printer_dots - len(bits)))
        width_bits = len(bits)
        padded = bytearray()
        byte = 0
        for i, ink in enumerate(bits):
            byte = (byte << 1) | ink
            if (i + 1) % 8 == 0:
                padded.append(byte)
                byte = 0
        if width_bits % 8:
            padded.append(byte << (8 - (width_bits % 8)))
        return padded

    row_bytes = (w + 7) // 8
    out = bytearray()
    for y in range(h):
        out += _pad_row(raster[y * row_bytes : (y + 1) * row_bytes], w)
    return bytes(out), printer_dots


def _raster_command(raster: bytes, width_dots: int, height_dots: int) -> bytes:
    """Build the ``GS v 0`` raster image command for the given data."""
    x_bytes = (width_dots + 7) // 8
    return (
        b"\x1d\x76\x30\x00"
        + bytes(
            (
                x_bytes & 0xFF,
                (x_bytes >> 8) & 0xFF,
                height_dots & 0xFF,
                (height_dots >> 8) & 0xFF,
            )
        )
        + raster
    )


def build_logo_command(
    path=None,
    *,
    printer_dots: int = PRINTABLE_DOTS,
    max_width: int = LOGO_MAX_WIDTH,
    max_height: int = LOGO_MAX_HEIGHT,
    threshold: int = LOGO_THRESHOLD,
) -> bytes:
    """Return the centred raster command for the Funmite logo.

    Returns ``b""`` when the logo cannot be loaded (printing continues without
    a logo).  The result is cached keyed on the build parameters.
    """
    logo_path = Path(path) if path else DEFAULT_LOGO_PATH
    key = (str(logo_path), printer_dots, max_width, max_height, threshold)
    if key in _LOGO_CACHE:
        return _LOGO_CACHE[key]
    raster, w, h = _logo_raster(logo_path, max_width, max_height, threshold)
    if raster is None:
        _LOGO_CACHE[key] = b""
        return b""
    centred, width = _centre_raster(raster, w, h, printer_dots)
    command = _raster_command(centred, width, h)
    _LOGO_CACHE[key] = command
    return command


class EscPosRenderer:
    """Renders a ``ReceiptData`` into ESC/POS bytes for an 80mm printer."""

    def __init__(
        self,
        *,
        logo_path=None,
        logo_max_width: int = LOGO_MAX_WIDTH,
        logo_max_height: int = LOGO_MAX_HEIGHT,
        logo_threshold: int = LOGO_THRESHOLD,
        printer_dots: int = PRINTABLE_DOTS,
        width: int = PRINTABLE_WIDTH,
        logo_enabled: bool = True,
    ) -> None:
        self.width = width
        self.printer_dots = printer_dots
        self.logo_enabled = logo_enabled
        self._logo = None
        if logo_enabled:
            self._logo = build_logo_command(
                logo_path,
                printer_dots=printer_dots,
                max_width=logo_max_width,
                max_height=logo_max_height,
                threshold=logo_threshold,
            )

    def render(self, receipt: ReceiptData) -> bytes:
        out = bytearray(INIT)
        out += CODE_PAGE_PC437

        if self._logo:
            out += ALIGN_CENTRE
            out += self._logo
            out += ALIGN_LEFT

        lines = render_receipt_text(receipt, self.width)
        out += self._render_lines(receipt, lines)

        out += b"\x0a" * CUT_FEED_LINES
        out += CUT_FULL
        return bytes(out)

    # ── internal helpers ──────────────────────────────────────────────────

    def _centred(self, receipt: ReceiptData) -> set[str]:
        texts = {
            receipt.shop_name,
            receipt.shop_category,
            receipt.address,
            receipt.phone,
            receipt.email,
            receipt.thank_you,
            receipt.payment_header,
            receipt.barcode,
            *receipt.grand_thank.split("\n"),
            *receipt.footer.split("\n"),
            receipt.visit,
            receipt.tagline,
        }
        for field in (
            receipt.shop_name,
            receipt.shop_category,
            receipt.address,
            receipt.phone,
            receipt.email,
            receipt.thank_you,
        ):
            texts.update(_centered_lines(field, self.width))
            for part in _wrap_name(field, max(1, self.width - 8)):
                texts.add(part)
        return texts

    def _emphasised(self, receipt: ReceiptData) -> set[str]:
        return {receipt.shop_name, *receipt.grand_thank.split("\n")}

    def _render_lines(self, receipt: ReceiptData, lines: list[str]) -> bytes:
        out = bytearray()
        centred_texts = self._centred(receipt)
        emphasised = self._emphasised(receipt)
        current_align: bytes | None = None

        for line in lines:
            stripped = line.strip()
            if not stripped:
                if current_align != ALIGN_LEFT:
                    out += ALIGN_LEFT
                    current_align = ALIGN_LEFT
                out += b"\x0a"
                continue

            if stripped == receipt.barcode:
                if current_align != ALIGN_CENTRE:
                    out += ALIGN_CENTRE
                    current_align = ALIGN_CENTRE
                out += EMPHASIS_OFF
                out += self._barcode(receipt.barcode)
                out += _encode_text(receipt.barcode)
                out += b"\x0a"
                continue

            centre = stripped in centred_texts
            bold = stripped in emphasised or stripped.startswith("TOTAL")
            align = ALIGN_CENTRE if centre else ALIGN_LEFT
            if current_align != align:
                out += align
                current_align = align
            out += EMPHASIS_ON if bold else EMPHASIS_OFF
            text = stripped if centre else line.rstrip()
            out += _encode_text(text)
            out += b"\x0a"

        return bytes(out)

    @staticmethod
    def _barcode(value: str) -> bytes:
        """Code128 barcode command (``GS k 73``) for ``value``."""
        if not value:
            return b""
        data = value.encode("ascii", errors="ignore")
        return b"\x1d\x6b\x49" + data + b"\x00"
