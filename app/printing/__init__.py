"""Printing layer — receipts and labels."""

from __future__ import annotations

from app.printing.escpos import EscPosRenderer  # noqa: F401
from app.printing.printer import (  # noqa: F401
    EscPosFilePrinter,
    InMemoryPrinter,
    NullPrinter,
    ReceiptPrinter,
)
from app.printing.receipt import (  # noqa: F401
    PAYMENT_LABELS,
    RECEIPT_FOOTER,
    RECEIPT_TAGLINE,
    SHOP_ADDRESS,
    SHOP_NAME,
    SHOP_PHONE,
    ReceiptBuilder,
    ReceiptData,
    ReceiptLine,
    discount_label,
    render_receipt_text,
)
