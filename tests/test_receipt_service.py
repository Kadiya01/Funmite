"""Receipt service tests (Phase 05).

Covers building detached receipt data from a completed sale, the approved
discount label format, printing through the printer abstraction, and the
Admin-only reprint flow (UC-06).
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.data.db import session_scope
from app.data.models import DISCOUNT_PERCENT, PAYMENT_POS, PAYMENT_TRANSFER, ROLE_ADMIN, ROLE_CASHIER, Sale
from app.domain.errors import AuthorizationError, NotFoundError
from app.domain.services.receipt_service import ReceiptService
from app.domain.services.sale_service import SaleService
from app.printing.printer import EscPosFilePrinter, InMemoryPrinter
from app.printing.receipt import ReceiptBuilder, discount_label, render_receipt_text
from app.utils.formatting import NAIRA
from tests.factories import make_category, make_customer, make_product, make_user


def _complete_sale(session_factory, session, *, discount=None):
    admin = make_user(session, role=ROLE_ADMIN)
    customer = make_customer(session, name="Amina Yusuf")
    category = make_category(session)
    product = make_product(session, category, name="Ladies Gown", quantity=5, selling_price=Decimal("35000"))
    session.commit()
    items = [{"product_id": product.id, "quantity": 2}]
    with session_scope(session_factory) as session:
        return SaleService(session).complete_sale(
            admin,
            customer_id=customer.id,
            items=items,
            payment_method=PAYMENT_POS,
            discount=discount,
        )


def _receipt(session_factory, sale_id: int) -> ReceiptData:
    """Build detached receipt data while the sale's session is still open."""
    with session_factory() as session:
        sale = session.get(Sale, sale_id)
        return ReceiptBuilder().from_sale(sale)


def test_build_receipt_contains_expected_content(session_factory, session):
    sale = _complete_sale(session_factory, session)
    receipt = _receipt(session_factory, sale.id)

    assert receipt.receipt_no == sale.receipt_no
    assert receipt.barcode == sale.receipt_no
    assert receipt.cashier_name
    assert receipt.customer_name == "Amina Yusuf"
    assert len(receipt.lines) == 1
    line = receipt.lines[0]
    assert line.name == "Ladies Gown"
    assert line.quantity == 2
    assert line.unit_price == Decimal("35000")
    assert line.total == Decimal("70000")
    assert receipt.subtotal == Decimal("70000")
    assert receipt.total == Decimal("70000")
    assert receipt.payment_method == PAYMENT_POS
    assert receipt.payment_label == "BANK POS"
    assert receipt.shop_name
    assert receipt.address
    assert receipt.phone


def test_build_receipt_maps_transfer_payment_label(session_factory, session):
    admin = make_user(session, role=ROLE_ADMIN)
    customer = make_customer(session)
    product = make_product(session, make_category(session), quantity=5)
    session.commit()
    with session_scope(session_factory) as session:
        sale = SaleService(session).complete_sale(
            admin,
            customer_id=customer.id,
            items=[{"product_id": product.id, "quantity": 1}],
            payment_method=PAYMENT_TRANSFER,
        )
    receipt = _receipt(session_factory, sale.id)
    assert receipt.payment_label == "BANK TRANSFER"


def test_build_receipt_includes_discount(session_factory, session):
    sale = _complete_sale(
        session_factory,
        session,
        discount={"type": DISCOUNT_PERCENT, "value": 10},
    )
    receipt = _receipt(session_factory, sale.id)
    assert receipt.discount_type == DISCOUNT_PERCENT
    assert receipt.discount_value == Decimal("10")
    assert receipt.discount_amount == Decimal("7000")
    assert receipt.total == Decimal("63000")
    assert receipt.payment_label == "BANK POS"


def test_discount_label_format(session_factory, session):
    sale = _complete_sale(
        session_factory,
        session,
        discount={"type": DISCOUNT_PERCENT, "value": 10},
    )
    receipt = _receipt(session_factory, sale.id)
    assert discount_label(receipt) == f"Discount (10%): {NAIRA}7,000"


def test_render_receipt_text_has_wireframe_sections(session_factory, session):
    sale = _complete_sale(session_factory, session)
    receipt = _receipt(session_factory, sale.id)
    lines = render_receipt_text(receipt)
    text = "\n".join(lines)
    assert receipt.shop_name in text
    assert f"RECEIPT: {receipt.receipt_no}" in text
    assert "Cashier:" in text
    assert "Customer: Amina Yusuf" in text
    assert "TOTAL:" in text
    assert "Payment: BANK POS" in text
    assert f"Receipt barcode: {receipt.receipt_no}" in text
    assert "Thank you for shopping" in text


def test_print_receipt_via_in_memory_printer(session_factory, session):
    sale = _complete_sale(session_factory, session)
    receipt = _receipt(session_factory, sale.id)
    printer = InMemoryPrinter()
    ReceiptService(session).print_receipt(receipt, printer)
    assert len(printer.receipts) == 1
    assert printer.receipts[0].receipt_no == receipt.receipt_no


def test_esc_pos_file_printer_writes_bytes(session_factory, session, tmp_path):
    sale = _complete_sale(session_factory, session)
    receipt = _receipt(session_factory, sale.id)
    target = tmp_path / "receipt.bin"
    EscPosFilePrinter(target).print_receipt(receipt)
    assert target.exists()
    assert target.read_bytes().startswith(b"\x1b\x40")


# --- reprint (UC-06) ------------------------------------------------------- #


def test_admin_can_reprint(session_factory, session):
    admin = make_user(session, role=ROLE_ADMIN)
    sale = _complete_sale(session_factory, session)
    printer = InMemoryPrinter()
    with session_scope(session_factory) as session:
        receipt = ReceiptService(session).reprint(admin, sale.receipt_no, printer)
    assert receipt.receipt_no == sale.receipt_no
    assert len(printer.receipts) == 1


def test_cashier_cannot_reprint(session_factory, session):
    cashier = make_user(session, role=ROLE_CASHIER)
    sale = _complete_sale(session_factory, session)
    with pytest.raises(AuthorizationError):
        with session_scope(session_factory) as session:
            ReceiptService(session).reprint(cashier, sale.receipt_no, InMemoryPrinter())


def test_reprint_unknown_receipt_raises_not_found(session_factory, session):
    admin = make_user(session, role=ROLE_ADMIN)
    with pytest.raises(NotFoundError, match="No sale found"):
        with session_scope(session_factory) as session:
            ReceiptService(session).reprint(admin, "FUN-99999999-999", InMemoryPrinter())
