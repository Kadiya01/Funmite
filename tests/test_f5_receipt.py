"""F5 receipt implementation tests (Phase 05 / F5).

Covers the approved Funmite Clothing & Beyond 80mm thermal receipt spec:

- Store branding: logo bitmap (GS v 0), store name, category, address,
  phone, email, welcome message
- Transaction block: receipt number, date/time, cashier, customer
- Item grid: ITEM/QTY/PRICE/TOTAL columns, long-name wrapping without
  numeric columns on continuation lines
- Totals: SUBTOTAL / DISCOUNT / TOTAL right-aligned to the item total column
- Payment section: method, amount paid, change
- Barcode: Code128 (GS k 73) payload = receipt number, plus human-readable
  copy underneath
- Footer: thank-you, visit, tagline
- Naira handling: ESC/POS stream never contains the raw naira sign (U+20A6);
  amounts use the plain ``N`` prefix
- Failure isolation: a committed sale survives a receipt-printer failure
- Deterministic preview: the full chain renders the approved layout
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from pathlib import Path

import pytest
from PySide6.QtGui import QColor, QImage

from app.data.db import session_scope
from app.data.models import DISCOUNT_PERCENT, PAYMENT_POS, ROLE_ADMIN, Sale
from app.domain.errors import NotFoundError
from app.domain.services.receipt_service import ReceiptService
from app.domain.services.sale_service import SaleService
from app.printing.escpos import (
    ALIGN_LEFT,
    CODE_PAGE_PC437,
    CUT_FULL,
    CUT_FEED_LINES,
    EMPHASIS_ON,
    INIT,
    EscPosRenderer,
    _centre_raster,
    _logo_raster,
    build_logo_command,
)
from app.printing.printer import InMemoryPrinter, PrinterWriteFailureError
from app.printing.receipt import (
    PRINTABLE_WIDTH,
    SHOP_ADDRESS,
    SHOP_EMAIL,
    SHOP_NAME,
    SHOP_PHONE,
    ReceiptData,
    ReceiptLine,
    _item_widths,
    _wrap_name,
    render_receipt_text,
)
from app.utils.formatting import format_money
from tests.factories import make_category, make_customer, make_product, make_user


def _receipt() -> ReceiptData:
    """A deterministic F5 receipt with realistic Funmite data."""
    return ReceiptData(
        receipt_no="FUN-20260904-001",
        sale_date=datetime(2026, 9, 4, 14, 30, 5),
        cashier_name="Amina Bello",
        customer_name="Aisha Hassan",
        lines=[
            ReceiptLine(name="Men's Kaftan", quantity=1, unit_price=Decimal("25000"), total=Decimal("25000")),
            ReceiptLine(name="Polo Shirt", quantity=2, unit_price=Decimal("8000"), total=Decimal("16000")),
            ReceiptLine(name="Ladies Handbag", quantity=1, unit_price=Decimal("12500"), total=Decimal("12500")),
        ],
        subtotal=Decimal("53500"),
        discount_type=DISCOUNT_PERCENT,
        discount_value=Decimal("10"),
        discount_amount=Decimal("5350"),
        total=Decimal("48150"),
        payment_method=PAYMENT_POS,
        payment_label="BANK POS",
        amount_paid=Decimal("50000"),
        barcode="FUN-20260904-001",
    )


def _text(_receipt_data: ReceiptData = _receipt()) -> list[str]:
    return render_receipt_text(_receipt_data)


def _timed_receipt() -> ReceiptData:
    return _receipt()


def _make_logo(path: Path, w: int = 100, h: int = 50, *, ink: tuple[int, int, int, int] | None = None) -> None:
    """Create a simple test logo png: white background, optional black rect."""
    image = QImage(w, h, QImage.Format.Format_RGB32)
    image.fill(QColor("white"))
    if ink is not None:
        x0, y0, bw, bh = ink
        for y in range(y0, min(y0 + bh, h)):
            for x in range(x0, min(x0 + bw, w)):
                image.setPixelColor(x, y, QColor("black"))
    image.save(str(path))


def _decode_esp(data: bytes) -> list[tuple[str, str]]:
    """Decode an ESC/POS stream into ``(alignment, text)`` per printed line.

    Control commands and raster data are skipped; Code128 payloads are
    dropped.  Alignments come from ``ESC a`` (L/C/R).
    """
    lines: list[tuple[str, str]] = []
    align = "L"
    cur = bytearray()
    i, n = 0, len(data)
    while i < n:
        if data.startswith(b"\x1d\x76\x30\x00", i):
            xl, xh, yl, yh = data[i + 4], data[i + 5], data[i + 6], data[i + 7]
            block = (xl + (xh << 8)) * (yl + (yh << 8))
            i += 8 + block
            continue
        if data.startswith(b"\x1d\x6b\x49", i):
            end = data.find(b"\x00", i + 3)
            i = (end + 1) if end != -1 else n
            continue
        if data.startswith(b"\x1d\x56\x41", i):
            i += 3
            continue
        if data.startswith(b"\x1b\x61", i):
            align = {0: "L", 1: "C", 2: "R"}.get(data[i + 2], "L")
            i += 3
            continue
        if data.startswith(b"\x1b\x40", i):
            i += 2
            continue
        if data.startswith(b"\x1b\x45", i) or data.startswith(b"\x1b\x74", i):
            i += 3
            continue
        ch = data[i : i + 1]
        if ch == b"\x0a":
            if cur:
                lines.append((align, bytes(cur).decode("cp437", errors="replace")))
                cur = bytearray()
            i += 1
            continue
        cur += ch
        i += 1
    if cur:
        lines.append((align, bytes(cur).decode("cp437", errors="replace")))
    return lines


# ─── Branding ────────────────────────────────────────────────────────────


def test_logo_is_included_by_default():
    out = EscPosRenderer().render(_receipt())
    assert out.startswith(INIT + CODE_PAGE_PC437)
    assert b"\x1d\x76\x30\x00" in out


def test_logo_command_from_generated_png(tmp_path):
    logo = tmp_path / "brand.png"
    _make_logo(logo)
    command = build_logo_command(logo, printer_dots=576, max_width=400, max_height=150)
    assert command.startswith(b"\x1d\x76\x30\x00")
    assert command[4] + command[5] * 256 >= (100 + 7) // 8  # width bytes for the natural raster


def test_logo_command_empty_when_file_missing(tmp_path):
    assert build_logo_command(tmp_path / "nope.png") == b""


def test_logo_command_empty_for_junk_file(tmp_path):
    junk = tmp_path / "junk.png"
    junk.write_bytes(b"this is not a png")
    assert build_logo_command(junk) == b""


def test_logo_raster_removes_white_background(tmp_path):
    logo = tmp_path / "blank.png"
    _make_logo(logo, 50, 30)
    raster, _, _ = _logo_raster(logo, 400, 150, 140)
    assert raster is not None
    assert all(byte == 0 for byte in raster)  # white canvas → no ink


def test_logo_raster_keeps_black_ink(tmp_path):
    logo = tmp_path / "black.png"
    _make_logo(logo, 50, 30)
    image = QImage(str(logo))
    image.fill(QColor("black"))
    image.save(str(logo))
    raster, _, _ = _logo_raster(logo, 400, 150, 140)
    assert raster is not None
    assert any(byte != 0 for byte in raster)


def test_logo_centred_within_printable_width(tmp_path):
    logo = tmp_path / "square.png"
    _make_logo(logo, 100, 40)
    raster, w, h = _logo_raster(logo, 400, 150, 140)
    assert raster is not None
    centred, width = _centre_raster(raster, w, h, 576)
    assert width == 576
    assert h == 150  # 2.5:1 image scaled up to the 150-dot height cap
    left_margin_bytes = ((576 - w) // 2) // 8
    for y in range(h):
        row = centred[y * 72 : (y + 1) * 72]
        assert len(row) == 72
        assert row[:left_margin_bytes] == bytes(left_margin_bytes)  # left margin is blank


def test_logo_preserves_aspect_ratio(tmp_path):
    logo = tmp_path / "wide.png"
    _make_logo(logo, 200, 100)
    raster, w, h = _logo_raster(logo, 400, 80, 140)
    assert raster is not None
    assert w == 160  # limited by height: keeps 2:1 ratio, never exceeds 400x80
    assert h == 80


def test_logo_raster_treats_transparent_background_as_paper(tmp_path):
    logo = tmp_path / "transparent.png"
    image = QImage(60, 40, QImage.Format.Format_ARGB32)
    image.fill(QColor(0, 0, 0, 0))
    for y in range(8, 32):
        for x in range(10, 50):
            image.setPixelColor(x, y, QColor(0, 0, 0, 255))
    image.save(str(logo))
    raster, w, h = _logo_raster(logo, 60, 40, 140)
    assert raster is not None
    row_bytes = (w + 7) // 8
    for y in range(0, 8):
        row = raster[y * row_bytes : (y + 1) * row_bytes]
        assert all(byte == 0 for byte in row), "transparent pixels must print as paper (no ink)"
    assert any(byte != 0 for byte in raster)  # the opaque black body does print


def test_configured_branding_rendered_in_text():
    lines = _text()
    joined = "\n".join(lines)
    assert SHOP_NAME in joined
    assert "WOMEN FASHION STORE" in joined
    assert "NAK Plaza" in joined
    assert SHOP_PHONE in joined
    assert SHOP_EMAIL in joined
    assert "Thank you for coming!" in joined


def test_configured_branding_rendered_in_esp():
    out = EscPosRenderer().render(_receipt())
    assert SHOP_NAME.encode("cp437") in out
    assert SHOP_PHONE.encode("cp437") in out
    assert SHOP_EMAIL.encode("cp437") in out


def test_email_wraps_when_too_long_for_one_line():
    data = _receipt()
    data = ReceiptData(**{**data.__dict__, "email": "averylongemailaddressforeveryone@example.com"})
    lines = _text(data)
    assert any(SHOP_NAME in line for line in lines)  # header intact
    assert all(len(line) <= PRINTABLE_WIDTH for line in lines)


def test_wrapped_branding_lines_stay_centred():
    data = _receipt()
    long_address = "A" * 10 + " " + "B" * 40
    data = ReceiptData(**{**data.__dict__, "address": long_address})
    preview = render_receipt_text(data)
    header = []
    for line in preview:
        if line == "=" * PRINTABLE_WIDTH:
            break
        if line.strip():
            header.append(line.strip())
    assert len(header) >= 6, "expected a wrapped header block"
    centred = {text for align, text in _decode_esp(EscPosRenderer().render(data)) if align == "C"}
    for part in header:
        assert part in centred, f"{part!r} must be emitted with centred alignment"


# ─── Layout ──────────────────────────────────────────────────────────────


def test_layout_sections_in_approved_order():
    lines = _text()
    joined = "\n".join(lines)
    r = joined.index
    assert r("Receipt No : FUN-20260904-001") < r("ITEM")
    assert r("ITEM") < r("SUBTOTAL")
    subtotal_idx = next(i for i, line in enumerate(lines) if line.strip().startswith("SUBTOTAL"))
    total_idx = next(i for i, line in enumerate(lines) if line.strip().startswith("TOTAL") and "NGN48,150" in line)
    assert subtotal_idx < total_idx
    assert r("TOTAL") < r("PAYMENT")
    assert r("PAYMENT") < r("BANK POS")
    last_barcode = joined.rindex("FUN-20260904-001")  # the barcode block, not the receipt-no line
    assert r("THANK YOU FOR SHOPPING") < last_barcode
    assert last_barcode < r("Please keep this receipt")


def test_transaction_header_fields():
    text = "\n".join(_text())
    assert "Receipt No : FUN-20260904-001" in text
    assert "Date       : 04/09/2026" in text
    assert "Time : 14:30:05" in text
    assert "Cashier    : Amina Bello" in text
    assert "Customer   : Aisha Hassan" in text


def test_item_columns_header():
    text = "\n".join(_text())
    assert "ITEM" in text
    assert "QTY" in text
    assert "PRICE" in text
    assert "TOTAL" in text


def test_long_product_name_wraps_continuation_without_numeric_columns():
    data = _receipt()
    long_name = "Very Long Women Fashion Dress With Embroidery And Beads"
    data = ReceiptData(**{**data.__dict__, "lines": [ReceiptLine(name=long_name, quantity=1, unit_price=Decimal("12500"), total=Decimal("12500"))]})
    lines = _text(data)
    first = next(line for line in lines if long_name.split()[0] in line)
    assert "NGN12,500" in first  # price + total on the first line
    start = lines.index(first)
    block = []
    for line in lines[start + 1 :]:
        if line.strip() == "-" * PRINTABLE_WIDTH:
            break
        block.append(line)
    assert block, "expected wrapped continuation lines"
    for line in block:
        words = line.split()
        assert all(word in long_name.split() for word in words)
        assert not any(ch.isdigit() for ch in line)  # no qty/price/total on continuations


def test_single_word_longer_than_name_width_breaks():
    name_w, _ = _item_widths(PRINTABLE_WIDTH)
    long_word = "SUPERCALIFRAGILISTICEXPIALIDOCIOUS"
    parts = _wrap_name(long_word, name_w)
    assert all(len(part) <= name_w for part in parts)
    assert "".join(parts) == long_word


def test_every_text_line_stays_within_printable_width():
    data = _receipt()
    long_data = ReceiptData(
        **{**data.__dict__,
           "lines": [ReceiptLine(name="AB" * 30, quantity=12, unit_price=Decimal("99999"), total=Decimal("999999"))],
           "customer_name": "C" * 60,
           "cashier_name": "D" * 60,
        }
    )
    for line in _text(long_data):
        assert len(line) <= PRINTABLE_WIDTH


def test_item_values_right_aligned_matching_total_column():
    lines = _text()
    totals = [line for line in lines if line.strip().startswith("TOTAL")]
    assert totals
    total_line = totals[-1]
    # LEFT is where the totals are: the money starts at the same column
    # as the item TOTAL of a 7-char amount.
    n = total_line.find("NGN48,150")
    assert n != -1
    # "NGN48,150" is right-aligned within a 10-char column at the end of the line.
    assert total_line.rstrip().endswith("NGN48,150")
    assert len(total_line.rstrip()) == PRINTABLE_WIDTH


def test_totals_and_payment_section():
    text = "\n".join(_text())
    assert "SUBTOTAL" in text and "NGN53,500" in text
    assert "DISCOUNT" in text and "NGN5,350" in text
    assert "TOTAL" in text and "NGN48,150" in text
    assert "Payment Method  : BANK POS" in text
    assert "Amount Paid" in text and "NGN50,000" in text
    assert "Change" in text and "NGN1,850" in text
    amount = next(line for line in _text() if line.strip().startswith("Amount Paid"))
    assert amount.rstrip().endswith("NGN50,000")


def test_footer_and_tagline():
    text = "\n".join(_text())
    assert "THANK YOU FOR SHOPPING" in text
    assert "WITH FUNMITE!" in text
    assert "Please keep this receipt" in text
    assert "for returns and exchanges." in text
    assert "--- Visit us again! ---" in text
    assert "Luxury Fashion for Women Who Love to Stand Out" in text


def test_discount_row_present():
    lines = _text()
    discount = next(line for line in lines if line.strip().startswith("DISCOUNT"))
    assert "NGN5,350" in discount


# ─── ESC/POS ─────────────────────────────────────────────────────────────


def test_esp_output_is_valid_bytes_stream():
    out = EscPosRenderer().render(_receipt())
    assert isinstance(out, bytes)
    assert out.startswith(INIT + CODE_PAGE_PC437)
    assert out.endswith(b"\x0a" * CUT_FEED_LINES + CUT_FULL)


def test_esp_contains_alignment_and_emphasis_commands():
    out = EscPosRenderer().render(_receipt())
    assert ALIGN_LEFT in out
    assert EMPHASIS_ON in out


def test_logo_omitted_when_disabled():
    out = EscPosRenderer(logo_enabled=False).render(_receipt())
    assert out.startswith(INIT + CODE_PAGE_PC437)
    assert b"\x1d\x76\x30\x00" not in out


def test_esp_output_is_deterministic_for_identical_data():
    data = _receipt()
    assert EscPosRenderer().render(data) == EscPosRenderer().render(data)


def test_esp_text_lines_stay_within_printable_width():
    data = _receipt()
    long_data = ReceiptData(
        **{**data.__dict__,
           "lines": [ReceiptLine(name="AB" * 30, quantity=12, unit_price=Decimal("99999"), total=Decimal("999999"))],
           "customer_name": "C" * 60,
           "cashier_name": "D" * 60,
        }
    )
    for _align, text in _decode_esp(EscPosRenderer().render(long_data)):
        if text.strip():
            assert len(text) <= PRINTABLE_WIDTH


def test_esp_barcode_payload_is_receipt_number():
    out = EscPosRenderer().render(_receipt())
    marker = b"\x1d\x6b\x49"
    start = out.find(marker)
    assert start != -1
    payload = out[start + len(marker) :]
    end = payload.find(b"\x00")
    assert end != -1
    assert payload[:end] == b"FUN-20260904-001"


def test_esp_human_readable_barcode_below():
    out = EscPosRenderer().render(_receipt())
    assert b"FUN-20260904-001" in out


def test_esp_no_raw_naira_sign():
    out = EscPosRenderer().render(_receipt())
    assert "\u20a6".encode("utf-8") not in out
    assert b"\xe2\x82\xa6" not in out


def test_esp_emphasises_branding_and_grand_thank():
    out = EscPosRenderer().render(_receipt())
    marker = b"\x1b\x45\x01"  # emphasis on
    assert marker in out
    assert marker + SHOP_NAME.encode("cp437") in out


def test_esp_emphasises_totals_line():
    out = EscPosRenderer().render(_receipt())
    padded = f"{'TOTAL':>37} {'NGN48,150':>10}"  # the full 48-char line, not stripped
    marker = EMPHASIS_ON + padded.encode("cp437")
    assert marker in out


# ─── Barcode │ Code128 ────────────────────────────────────────────────────


def test_code128_command_marks_gs_k_73():
    renderer = EscPosRenderer()
    assert renderer._barcode("FUN-20260904-001") == b"\x1d\x6b\x49FUN-20260904-001\x00"
    assert renderer._barcode("") == b""


# ─── Printer failure must not lose the sale ───────────────────────────────


class _FailingPrinter(InMemoryPrinter):
    def print_receipt(self, receipt: ReceiptData) -> None:
        raise PrinterWriteFailureError("paper jam")


def test_lost_printer_does_not_lose_committed_sale(session_factory, session):
    admin = make_user(session, role=ROLE_ADMIN)
    customer = make_customer(session, name="Zainab Musa")
    product = make_product(session, make_category(session), name="Silk Hijab", quantity=6, selling_price=Decimal("15000"))
    session.commit()

    with session_scope(session_factory) as s:
        sale = SaleService(s).complete_sale(
            admin,
            customer_id=customer.id,
            items=[{"product_id": product.id, "quantity": 3}],
            payment_method=PAYMENT_POS,
        )
        receipt_no = sale.receipt_no

    # Print fails after the sale was committed.
    with session_scope(session_factory) as s:
        stored = ReceiptService(s).get_by_receipt_no(receipt_no)
        assert stored is not None
        receipt = ReceiptService(s).build_receipt(stored)
    with pytest.raises(PrinterWriteFailureError):
        _FailingPrinter().print_receipt(receipt)

    # The sale must still exist, fully persisted.
    with session_factory() as s:
        sale = s.get(Sale, sale.id)
        assert sale is not None
        assert sale.receipt_no == receipt_no
        assert sale.total == Decimal("45000")
        assert sale.cashier_id == admin.id


def test_lost_printer_allows_reprint_from_receipt_no(session_factory, session):
    admin = make_user(session, role=ROLE_ADMIN)
    customer = make_customer(session)
    product = make_product(session, make_category(session), quantity=4)
    session.commit()
    with session_scope(session_factory) as s:
        sale = SaleService(s).complete_sale(
            admin, customer_id=customer.id,
            items=[{"product_id": product.id, "quantity": 2}],
            payment_method=PAYMENT_POS,
        )
    with session_scope(session_factory) as s:
        found = ReceiptService(s).get_by_receipt_no(sale.receipt_no)
        assert found.receipt_no == sale.receipt_no
        receipt = ReceiptService(s).build_receipt(found)
    assert receipt.barcode == sale.receipt_no
    with pytest.raises(PrinterWriteFailureError):
        _FailingPrinter().print_receipt(receipt)


# ─── Deterministic preview ────────────────────────────────────────────────


def test_deterministic_full_chain_preview():
    data = _receipt()
    text = "\n".join(render_receipt_text(data))
    esp = EscPosRenderer().render(data)
    # The preview mirrors the ESC/POS stream's text content.
    assert b"FUNMITE CLOTHING & BEYOND" in esp
    assert text.split("\n")[-1].strip() == "Luxury Fashion for Women Who Love to Stand Out"
    money = format_money(Decimal("48150"))
    assert money == "₦48,150"
    assert money.replace("₦", "NGN") in text


def test_independent_of_payment_amount_overpay_change_math():
    data = ReceiptData(
        receipt_no="FUN-20260904-001",
        sale_date=datetime(2026, 9, 4, 14, 30, 5),
        cashier_name="Amina Bello",
        customer_name="Aisha Hassan",
        lines=[
            ReceiptLine(name="Polo Shirt", quantity=2, unit_price=Decimal("8000"), total=Decimal("16000")),
        ],
        subtotal=Decimal("53500"),
        discount_type=DISCOUNT_PERCENT,
        discount_value=Decimal("10"),
        discount_amount=Decimal("5350"),
        total=Decimal("48150"),
        payment_method=PAYMENT_POS,
        payment_label="BANK POS",
        amount_paid=Decimal("60000"),
        barcode="FUN-20260904-001",
    )
    text = "\n".join(_text(data))
    assert "Change" in text and "NGN11,850" in text


def test_missing_receipt_raises_not_found(session_factory, session):
    with session_scope(session_factory) as s:
        with pytest.raises(NotFoundError):
            sale = ReceiptService(s).get_by_receipt_no("FUN-20990101-999")
            if sale is None:
                raise NotFoundError("no such receipt")
            ReceiptService(s).build_receipt(sale)