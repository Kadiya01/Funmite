"""Receipt data model and builder (Phase 05).

The receipt layout follows the approved wireframe (``03_UI_Wireframes``, section
12). The shop header/address/phone and footer text are a candidate from that
wireframe — receipt branding is an open client decision — so they are
configurable defaults in ``ReceiptBuilder`` and recorded in
``OPEN_DECISIONS.md``.

``ReceiptData`` is a plain dataclass: it contains only primitives/Decimals, so
it stays usable after the ORM session closes. Build it inside a short-lived
session (``ReceiptService.build_receipt``) and then hand it to any printer.

Receipt Barcode Specification (RESOLVED):
-----------------------------------------
The receipt barcode encodes the receipt number exactly (e.g. ``FUN-20260101-001``).
Format: ``FUN-<YYYYMMDD>-<NNN>`` where NNN is a daily sequence (001-999).

Symbology: Code128 (renders any ASCII text, universally supported by scanners).

Rationale:
- Receipt number is human-readable (can be typed manually if barcode is damaged)
- Receipt number is unique (enforced by database UNIQUE constraint on sales.receipt_no)
- Standard retail practice for transaction lookup, reprint, and exchange
- No device prefix needed for single-PC deployment; multi-PC prefix deferred
  (see OPEN_DECISIONS.md "Receipt number device prefix")

The barcode is rendered:
- On-screen: as text in the receipt preview
- On-paper: via ESC/POS ``GS k 73`` (Code128) command for thermal printer
- On-labels: via ``python-barcode`` Code128 SVG renderer
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from app.data.models import PAYMENT_POS, PAYMENT_TRANSFER, Sale
from app.utils.formatting import format_money

SHOP_NAME = "FUNMITE CLOTHING & BEYOND"
SHOP_ADDRESS = "No. 79 NAK Plaza, Nassarawa GRA, Hospital Road, Kano"
SHOP_PHONE = "Tel: 07079517584"
RECEIPT_FOOTER = "Thank you for shopping with us."
RECEIPT_TAGLINE = "Luxury fashion for woman who love to stand out"

PAYMENT_LABELS = {
    PAYMENT_POS: "BANK POS",
    PAYMENT_TRANSFER: "BANK TRANSFER",
}


@dataclass(frozen=True)
class ReceiptLine:
    """One product line shown on the receipt."""

    name: str
    quantity: int
    unit_price: Decimal
    total: Decimal


@dataclass(frozen=True)
class ReceiptData:
    """Everything a receipt needs, detached from the ORM."""

    receipt_no: str
    sale_date: datetime
    cashier_name: str
    customer_name: str
    lines: list[ReceiptLine]
    subtotal: Decimal
    discount_type: str | None
    discount_value: Decimal
    discount_amount: Decimal
    total: Decimal
    payment_method: str
    payment_label: str
    amount_paid: Decimal
    barcode: str
    shop_name: str = SHOP_NAME
    address: str = SHOP_ADDRESS
    phone: str = SHOP_PHONE
    footer: str = RECEIPT_FOOTER
    tagline: str = RECEIPT_TAGLINE


class ReceiptBuilder:
    """Builds a detached ``ReceiptData`` from an ORM ``Sale``.

    The sale must have its ``items`` (with ``product``), ``customer`` and
    ``cashier`` accessible; call within an open session.
    """

    def __init__(
        self,
        *,
        shop_name: str = SHOP_NAME,
        address: str = SHOP_ADDRESS,
        phone: str = SHOP_PHONE,
        footer: str = RECEIPT_FOOTER,
        tagline: str = RECEIPT_TAGLINE,
    ) -> None:
        self.shop_name = shop_name
        self.address = address
        self.phone = phone
        self.footer = footer
        self.tagline = tagline

    def from_sale(self, sale: Sale) -> ReceiptData:
        lines = [
            ReceiptLine(
                name=item.product.name if item.product else f"Product #{item.product_id}",
                quantity=item.quantity,
                unit_price=Decimal(item.unit_price),
                total=Decimal(item.line_total),
            )
            for item in sorted(sale.items, key=lambda item: item.id)
        ]
        customer_name = sale.customer.name if sale.customer else ""
        cashier_name = sale.cashier.full_name if sale.cashier else ""
        payment_method = str(sale.payment_method or "").upper()
        return ReceiptData(
            receipt_no=sale.receipt_no,
            sale_date=sale.sale_date,
            cashier_name=cashier_name,
            customer_name=customer_name,
            lines=lines,
            subtotal=Decimal(sale.subtotal),
            discount_type=sale.discount_type,
            discount_value=Decimal(sale.discount_value),
            discount_amount=Decimal(sale.discount_amount),
            total=Decimal(sale.total),
            payment_method=payment_method,
            payment_label=PAYMENT_LABELS.get(payment_method, payment_method),
            amount_paid=Decimal(sale.amount_paid),
            barcode=sale.receipt_no,
            shop_name=self.shop_name,
            address=self.address,
            phone=self.phone,
            footer=self.footer,
            tagline=self.tagline,
        )


def discount_label(receipt: ReceiptData) -> str:
    """Human-readable discount line, e.g. ``Discount (10%): ₦5,500``."""
    if receipt.discount_type == "PERCENT" and receipt.discount_value:
        value = f"{Decimal(receipt.discount_value).normalize():f}"
        return f"Discount ({value}%): {format_money(receipt.discount_amount)}"
    return f"Discount: {format_money(receipt.discount_amount)}"


def render_receipt_text(receipt: ReceiptData) -> list[str]:
    """Render the receipt as human-readable lines (wireframe layout)."""
    out = [
        receipt.shop_name,
        receipt.address,
        receipt.phone,
        "",
        f"RECEIPT: {receipt.receipt_no}",
        f"Date: {receipt.sale_date:%d/%m/%Y}   Time: {receipt.sale_date:%H:%M}",
        f"Cashier: {receipt.cashier_name}",
        f"Customer: {receipt.customer_name}",
        "",
        "Item                    Qty   Price       Total",
        "-" * 48,
    ]
    for line in receipt.lines:
        out.append(
            f"{line.name:<24} {line.quantity:>3}  "
            f"{format_money(line.unit_price):>10}  {format_money(line.total):>10}"
        )
    out.append("-" * 48)
    out.append(f"Subtotal: {format_money(receipt.subtotal):>34}")
    out.append(f"{discount_label(receipt):>40}")
    out.append(f"TOTAL: {format_money(receipt.total):>38}")
    out.append(f"Payment: {receipt.payment_label}")
    out.append(f"Amount Paid: {format_money(receipt.amount_paid):>32}")
    out.append("")
    out.append(f"Receipt barcode: {receipt.barcode}")
    out.append("")
    out.append(receipt.footer)
    out.append(receipt.tagline)
    return out
