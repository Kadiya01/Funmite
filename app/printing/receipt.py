"""Receipt data model and builder (Phase 05 / F5).

The receipt layout follows the approved F5 specification for an 80mm thermal
receipt printer.  ``ReceiptData`` is a plain dataclass: it contains only
primitives/Decimals, so it stays usable after the ORM session closes.  Build
it inside a short-lived session (``ReceiptService.build_receipt``) and then
hand it to any printer.

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
from pathlib import Path

from app.data.models import PAYMENT_POS, PAYMENT_TRANSFER, Sale
from app.utils.formatting import format_money

# ── Approved store branding (F5) ────────────────────────────────────────
SHOP_NAME = "FUNMITE CLOTHING & BEYOND"
SHOP_CATEGORY = "WOMEN FASHION STORE"
SHOP_ADDRESS = "No. 79 NAK Plaza Nassarawa GRA Hospital Road Kano"
SHOP_PHONE = "07079517584"
SHOP_EMAIL = "funmiteclothingandbeyond@gmail.com"
SHOP_THANK_YOU = "Thank you for coming!"
RECEIPT_FOOTER = "Please keep this receipt\nfor returns and exchanges."
RECEIPT_VISIT = "--- Visit us again! ---"
RECEIPT_TAGLINE = "Luxury Fashion for Women Who Love to Stand Out"
RECEIPT_GRAND_THANK = "THANK YOU FOR SHOPPING\nWITH FUNMITE!"
RECEIPT_PAYMENT_HEADER = "PAYMENT"

PAYMENT_LABELS = {
    PAYMENT_POS: "BANK POS",
    PAYMENT_TRANSFER: "BANK TRANSFER",
}

# ── Printable width (80mm thermal = 48 chars at 10 CPI) ─────────────────
PRINTABLE_WIDTH = 48


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
    shop_category: str = SHOP_CATEGORY
    address: str = SHOP_ADDRESS
    phone: str = SHOP_PHONE
    email: str = SHOP_EMAIL
    thank_you: str = SHOP_THANK_YOU
    footer: str = RECEIPT_FOOTER
    visit: str = RECEIPT_VISIT
    tagline: str = RECEIPT_TAGLINE
    grand_thank: str = RECEIPT_GRAND_THANK
    payment_header: str = RECEIPT_PAYMENT_HEADER


class ReceiptBuilder:
    """Builds a detached ``ReceiptData`` from an ORM ``Sale``.

    The sale must have its ``items`` (with ``product``), ``customer`` and
    ``cashier`` accessible; call within an open session.
    """

    def __init__(
        self,
        *,
        shop_name: str = SHOP_NAME,
        shop_category: str = SHOP_CATEGORY,
        address: str = SHOP_ADDRESS,
        phone: str = SHOP_PHONE,
        email: str = SHOP_EMAIL,
        thank_you: str = SHOP_THANK_YOU,
        footer: str = RECEIPT_FOOTER,
        visit: str = RECEIPT_VISIT,
        tagline: str = RECEIPT_TAGLINE,
    ) -> None:
        self.shop_name = shop_name
        self.shop_category = shop_category
        self.address = address
        self.phone = phone
        self.email = email
        self.thank_you = thank_you
        self.footer = footer
        self.visit = visit
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
            shop_category=self.shop_category,
            address=self.address,
            phone=self.phone,
            email=self.email,
            thank_you=self.thank_you,
            footer=self.footer,
            visit=self.visit,
            tagline=self.tagline,
        )


# ── Formatting helpers ──────────────────────────────────────────────────


def discount_label(receipt: ReceiptData) -> str:
    """Human-readable discount line, e.g. ``Discount (10%): N5,500``."""
    if receipt.discount_type == "PERCENT" and receipt.discount_value:
        value = f"{Decimal(receipt.discount_value).normalize():f}"
        return f"Discount ({value}%): {format_money(receipt.discount_amount)}"
    return f"Discount: {format_money(receipt.discount_amount)}"


def _center(text: str, width: int = PRINTABLE_WIDTH) -> str:
    """Centre *text* within *width* characters."""
    return text.center(width)


def _centered_lines(text: str, width: int = PRINTABLE_WIDTH, wrap_width: int | None = None) -> list[str]:
    """Split *text* into centred lines, wrapping over-long text.

    Header brand lines (address, email, slogan) are wrapped so they stay a
    centred block and never run edge-to-edge on the thermal paper.
    """
    wrap = wrap_width or max(1, width - 8)
    if not text:
        return []
    parts = _wrap_name(text, wrap)
    return [_center(part, width) for part in parts]


def _repeat(ch: str, width: int = PRINTABLE_WIDTH) -> str:
    """Repeat *ch* to fill *width*."""
    return ch * width


def _wrap_name(name: str, max_width: int) -> list[str]:
    """Wrap a product name into chunks of at most *max_width* chars.

    Algorithm:
    - If the name fits in one line, return ``[name]``.
    - Otherwise split on whitespace greedily, producing as few lines as
      possible while never exceeding *max_width*.
    - If a single word exceeds *max_width* hard-break it.
    """
    if len(name) <= max_width:
        return [name]
    words = name.split()
    lines: list[str] = []
    current = ""
    for word in words:
        if not current:
            if len(word) > max_width:
                while len(word) > max_width:
                    lines.append(word[:max_width])
                    word = word[max_width:]
                if word:
                    current = word
            else:
                current = word
        else:
            if len(current) + 1 + len(word) <= max_width:
                current = f"{current} {word}"
            else:
                lines.append(current)
                if len(word) > max_width:
                    while len(word) > max_width:
                        lines.append(word[:max_width])
                        word = word[max_width:]
                    current = word
                else:
                    current = word
    if current:
        lines.append(current)
    return lines or [""]


def _format_item_row(
    name: str,
    qty: int,
    price: str,
    total: str,
    name_width: int,
    qty_width: int = 3,
) -> list[str]:
    """Format one receipt item, wrapping the name as needed.

    Returns a list of strings (one per printed line).  Quantity, price, and
    total appear only on the first line.
    """
    name_parts = _wrap_name(name, name_width)
    rows: list[str] = []
    for i, part in enumerate(name_parts):
        if i == 0:
            cols = (
                f"{part:<{name_width}}"
                f" {qty:>{qty_width}}"
                f" {price:>10}"
                f" {total:>10}"
            )
        else:
            cols = f"{part:<{name_width}}"
        rows.append(cols)
    return rows


def _item_widths(width: int) -> tuple[int, int]:
    """Return (name_width, qty_width) for the item grid.

    Layout for *width* chars:  name area + gap + qty(3) + gap + price(10)
    + gap + total(10) must equal *width*, giving name_width = width - 26.
    """
    return width - 26, 3


def _totals_line(label: str, value: str, width: int) -> str:
    """Right-aligned total row that aligns with the item total column."""
    return f"{label:>{width - 11}} {value:>10}"


def _kv_rows(label: str, value: str, width: int, *, label_width: int = 11) -> list[str]:
    """One key/value row, wrapping long values to stay within *width*.

    The label is right-justified to *label_width* followed by ``: ``; any
    overflow of the value wraps onto continuation lines indented under the
    value column so the receipt stays within the printable width.
    """
    base = f"{label:<{label_width}}: "
    indent = " " * len(base)
    rows: list[str] = []
    for chunk in _wrap_name(value or "", max(1, width - len(base))):
        rows.append(f"{base}{chunk}" if not rows else f"{indent}{chunk}")
    return rows or [base]


def _payment_line(label: str, value: str, *, align_value: bool = True) -> str:
    """One payment-section row with the value column aligned."""
    if align_value:
        return f"{label:<16}: {value:>10}"
    return f"{label:<16}: {value}"


# ── Text renderer ───────────────────────────────────────────────────────


def render_receipt_text(receipt: ReceiptData, width: int = PRINTABLE_WIDTH) -> list[str]:
    """Render the receipt as human-readable lines (F5 layout).

    The output mirrors the approved physical receipt mockup exactly.  The
    logo is omitted from the text representation — it is emitted directly as
    an ESC/POS bitmap by ``EscPosRenderer``.
    """
    w = width
    sep = _repeat("=", w)
    dash = _repeat("-", w)
    name_w, qty_w = _item_widths(w)

    out: list[str] = []

    # ── Store header (centred) ──────────────────────────────────────────
    for text in (
        receipt.shop_name,
        receipt.shop_category,
        receipt.address,
        receipt.phone,
        receipt.email,
        receipt.thank_you,
    ):
        out.extend(_centered_lines(text, w))

    # ── Separator ───────────────────────────────────────────────────────
    out.append(sep)

    # ── Transaction header ──────────────────────────────────────────────
    out.append(f"Receipt No : {receipt.receipt_no}")
    out.append(
        f"Date       : {receipt.sale_date:%d/%m/%Y}"
        f"      Time : {receipt.sale_date:%H:%M:%S}"
    )
    out.extend(_kv_rows("Cashier", receipt.cashier_name, w))
    out.extend(_kv_rows("Customer", receipt.customer_name or "Walk-in Customer", w))

    # ── Separator ───────────────────────────────────────────────────────
    out.append(sep)

    # ── Item table header ───────────────────────────────────────────────
    out.append(
        f"{'ITEM':<{name_w}} {'QTY':>{qty_w}} {'PRICE':>10} {'TOTAL':>10}"
    )
    out.append(dash)

    # ── Item rows ───────────────────────────────────────────────────────
    for line in receipt.lines:
        price_str = format_money(line.unit_price).replace("₦", "N")
        total_str = format_money(line.total).replace("₦", "N")
        rows = _format_item_row(line.name, line.quantity, price_str, total_str, name_w, qty_w)
        for row in rows:
            out.append(row)

    # ── Separator ───────────────────────────────────────────────────────
    out.append(dash)

    # ── Totals ──────────────────────────────────────────────────────────
    sub_str = format_money(receipt.subtotal).replace("₦", "N")
    disc_str = format_money(receipt.discount_amount).replace("₦", "N")
    tot_str = format_money(receipt.total).replace("₦", "N")
    out.append(_totals_line("SUBTOTAL", sub_str, w))
    out.append(_totals_line("DISCOUNT", disc_str, w))
    out.append(_totals_line("TOTAL", tot_str, w))

    # ── Separator ───────────────────────────────────────────────────────
    out.append(sep)

    # ── Payment section ─────────────────────────────────────────────────
    out.append(_center(receipt.payment_header, w))
    out.append(dash)
    paid_str = format_money(receipt.amount_paid).replace("₦", "N")
    change = receipt.amount_paid - receipt.total
    change_str = format_money(change).replace("₦", "N")
    out.append(_payment_line("Payment Method", receipt.payment_label, align_value=False))
    out.append(_payment_line("Amount Paid", paid_str))
    out.append(_payment_line("Change", change_str))

    # ── Separator ───────────────────────────────────────────────────────
    out.append(sep)

    # ── Grand thank-you ─────────────────────────────────────────────────
    for line in receipt.grand_thank.split("\n"):
        out.append(_center(line, w))

    # ── Barcode (text placeholder — rendered as CODE128 by EscPos) ─────
    out.append("")  # blank line before barcode
    out.append(_center(receipt.barcode, w))
    out.append("")  # blank line after barcode

    # ── Footer ──────────────────────────────────────────────────────────
    for line in receipt.footer.split("\n"):
        out.append(_center(line, w))
    out.append(_center(receipt.visit, w))
    out.append(_center(receipt.tagline, w))

    return out
