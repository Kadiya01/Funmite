"""Barcode label generation/printing abstraction.

Phase 03 provides a pure-Python SVG renderer (Code128) so an Admin can produce
a printable label file without any printer driver. Physical label printing is
hardware-specific and arrives in Phase 11; this module deliberately keeps the
label format separate from any printer code.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

import barcode
from barcode.writer import SVGWriter

from app.data.models import Product

BARCODE_SYMBOLOGY = "code128"


@dataclass(frozen=True)
class BarcodeLabel:
    """Everything a printable product label needs."""

    product_id: int
    name: str
    selling_price: Decimal
    barcode: str
    symbology: str = BARCODE_SYMBOLOGY

    @classmethod
    def from_product(cls, product: Product) -> "BarcodeLabel":
        return cls(
            product_id=product.id,
            name=product.name,
            selling_price=Decimal(product.selling_price),
            barcode=product.barcode,
        )


class LabelRenderer:
    """Renders a barcode label. Subclass for other output formats."""

    def render(self, label: BarcodeLabel) -> bytes:
        raise NotImplementedError

    def render_product(self, product: Product) -> bytes:
        return self.render(BarcodeLabel.from_product(product))


class SvgLabelRenderer(LabelRenderer):
    """Renders a scanner-readable Code128 SVG label (printer-independent)."""

    def __init__(self, *, width_mm: int = 50, height_mm: int = 30) -> None:
        self.width_mm = width_mm
        self.height_mm = height_mm

    def render(self, label: BarcodeLabel) -> bytes:
        code = barcode.get(label.symbology, label.barcode, writer=SVGWriter())
        svg = code.render({"module_height": 12, "quiet_zone": 4})
        return self._with_text(svg, label)

    @staticmethod
    def _with_text(svg: bytes, label: BarcodeLabel) -> bytes:
        """Inject the product name and selling price above the bars.

        ``python-barcode`` already draws the barcode digits under the bars; we
        add the human-readable product details above them so the label is
        self-explanatory at the till.
        """
        text = svg.decode("utf-8")
        escaped_name = (
            label.name.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
        )
        name_node = (
            f'<text x="10" y="14" font-family="Arial" font-size="9" '
            f'font-weight="bold">{escaped_name}</text>'
        )
        price_node = (
            f'<text x="10" y="24" font-family="Arial" font-size="8">'
            f"Price: &#8358;{label.selling_price}</text>"
        )
        closing = "</svg>"
        if closing not in text:
            return svg
        rendered = text.replace(closing, f"{name_node}{price_node}{closing}")
        return rendered.encode("utf-8")
