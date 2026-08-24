"""ESC/POS rendering tests (Phase 05).

Covers the raw bytes a thermal printer receives: initialisation, code page,
alignment, the Code128 barcode command and the partial cut, plus the approved
decision to render the naira sign as a plain ``N`` (PC437 has no naira glyph).
"""

from __future__ import annotations

from decimal import Decimal

from app.printing.escpos import (
    ALIGN_CENTRE,
    ALIGN_LEFT,
    CODE_PAGE_PC437,
    CUT_PARTIAL,
    EMPHASIS_OFF,
    EMPHASIS_ON,
    INIT,
    EscPosRenderer,
    _encode_text,
)
from app.printing.receipt import ReceiptData, ReceiptLine
from app.utils.formatting import NAIRA


def _receipt(**overrides) -> ReceiptData:
    defaults = dict(
        receipt_no="FUN-20260101-001",
        sale_date=__import__("datetime").datetime(2026, 1, 1, 12, 0),
        cashier_name="Admin User",
        customer_name="Amina Yusuf",
        lines=[ReceiptLine(name="Ladies Gown", quantity=1, unit_price=Decimal("35000"), total=Decimal("35000"))],
        subtotal=Decimal("35000"),
        discount_type=None,
        discount_value=Decimal("0"),
        discount_amount=Decimal("0"),
        total=Decimal("35000"),
        payment_method="POS",
        payment_label="BANK POS",
        amount_paid=Decimal("35000"),
        barcode="FUN-20260101-001",
        shop_name="FUNMITE CLOTHING & BEYOND",
        address="No. 79 NAK Plaza, Kano",
        phone="Tel: 07079517584",
        footer="Thank you for shopping with us.",
        tagline="Luxury fashion",
    )
    defaults.update(overrides)
    return ReceiptData(**defaults)


def test_render_starts_with_init_and_code_page():
    data = _receipt()
    out = EscPosRenderer().render(data)
    assert out.startswith(INIT + CODE_PAGE_PC437)


def test_render_uses_centre_and_left_alignment():
    data = _receipt()
    out = EscPosRenderer().render(data)
    assert ALIGN_CENTRE in out
    assert ALIGN_LEFT in out
    assert EMPHASIS_ON not in out
    assert EMPHASIS_OFF not in out


def test_render_ends_with_partial_cut():
    data = _receipt()
    out = EscPosRenderer().render(data)
    assert out.endswith(CUT_PARTIAL)


def test_render_contains_code128_barcode_command():
    data = _receipt(barcode="FUN-20260101-001")
    out = EscPosRenderer().render(data)
    assert b"\x1d\x6b\x49" + b"FUN-20260101-001" + b"\x00" in out


def test_render_skips_barcode_for_empty_value():
    data = _receipt(barcode="")
    out = EscPosRenderer().render(data)
    assert b"\x1d\x6b\x49" not in out


def test_render_replaces_naira_sign_with_n():
    data = _receipt()
    out = EscPosRenderer().render(data)
    assert b"N35,000" in out
    assert NAIRA.encode("utf-8") not in out


def test_encode_text_replaces_naira_on_cp437():
    assert _encode_text(f"{NAIRA}5,500") == b"N5,500"


def test_render_includes_receipt_number_and_shop():
    data = _receipt()
    out = EscPosRenderer().render(data)
    assert b"RECEIPT: FUN-20260101-001" in out
    assert b"FUNMITE CLOTHING & BEYOND" in out


def test_render_barcode_with_long_receipt_number():
    data = _receipt(barcode="FUN-20261231-999")
    out = EscPosRenderer().render(data)
    assert b"\x1d\x6b\x49" + b"FUN-20261231-999" + b"\x00" in out


def test_render_barcode_with_single_digit_sequence():
    data = _receipt(barcode="FUN-20260101-001")
    out = EscPosRenderer().render(data)
    assert b"FUN-20260101-001" in out


def test_render_barcode_preserves_receipt_format():
    """Receipt barcode must encode the full receipt number with FUN- prefix."""
    receipt_no = "FUN-20260615-042"
    data = _receipt(barcode=receipt_no)
    out = EscPosRenderer().render(data)
    assert receipt_no.encode("ascii") in out
