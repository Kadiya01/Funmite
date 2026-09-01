"""POS screen tests (Phase 05).

Qt-level coverage of the cashier screen: scanning, search, cart behaviour,
customer filtering and quick registration, the Admin-only discount and reprint
controls, POS/Transfer-only payment buttons and the complete-sale flow
including receipt printing and the insufficient-stock recovery path.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select

from app.data.db import session_scope
from app.data.models import (
    DISCOUNT_PERCENT,
    PAYMENT_POS,
    PAYMENT_TRANSFER,
    ROLE_ADMIN,
    ROLE_CASHIER,
    Sale,
)
from app.domain.services.sale_service import SaleService
from app.domain.session import CurrentUser
from app.printing.printer import InMemoryPrinter
from app.ui.pos.pos_page import OFFLINE_STATUS, PosPage
from tests.factories import make_category, make_customer, make_product, make_user


def _current(user) -> CurrentUser:
    return CurrentUser(
        user_id=user.id,
        username=user.username,
        full_name=user.full_name,
        role=user.role,
    )


def _page(session_factory, user, **kwargs) -> PosPage:
    return PosPage(session_factory, _current(user), **kwargs)


def _select_customer(page: PosPage, customer) -> None:
    index = page.customer_combo.findData(customer.id)
    assert index >= 0
    page.customer_combo.setCurrentIndex(index)


def _scan(page: PosPage, barcode: str) -> None:
    page.scan_input.barcode_scanned.emit(barcode)


def _popup_new(*_args, **_kwargs):
    return "new"


def _popup_print(*_args, **_kwargs):
    return "print"


# --- construction ---------------------------------------------------------- #


def test_pos_page_shows_offline_status(qtbot, session_factory, session):
    admin = make_user(session, role=ROLE_ADMIN)
    session.commit()
    page = _page(session_factory, admin)
    qtbot.addWidget(page)
    assert page.status_label.text() == OFFLINE_STATUS


def test_admin_sees_discount_and_reprint(qtbot, session_factory, session):
    admin = make_user(session, role=ROLE_ADMIN)
    session.commit()
    page = _page(session_factory, admin)
    qtbot.addWidget(page)
    assert not page.discount_group.isHidden()
    assert hasattr(page, "reprint_button")


def test_cashier_hides_discount_and_reprint(qtbot, session_factory, session):
    cashier = make_user(session, role=ROLE_CASHIER)
    session.commit()
    page = _page(session_factory, cashier)
    qtbot.addWidget(page)
    assert page.discount_group.isHidden()
    assert not hasattr(page, "reprint_button")


def test_only_pos_and_transfer_payment_buttons(qtbot, session_factory, session):
    admin = make_user(session, role=ROLE_ADMIN)
    session.commit()
    page = _page(session_factory, admin)
    qtbot.addWidget(page)
    assert page.pos_button.text() == "BANK POS"
    assert page.transfer_button.text() == "BANK TRANSFER"
    buttons = [button.text() for button in page.payment_group.buttons()]
    assert buttons == ["BANK POS", "BANK TRANSFER"]


# --- scanning -------------------------------------------------------------- #


def test_scan_adds_product_to_cart(qtbot, session_factory, session):
    admin = make_user(session, role=ROLE_ADMIN)
    product = make_product(session, make_category(session), name="Ladies Gown", quantity=5)
    product.barcode = "1001"
    session.commit()

    page = _page(session_factory, admin, sale_complete_popup=_popup_new)
    qtbot.addWidget(page)
    _scan(page, "1001")

    assert page.cart_table.rowCount() == 1
    assert page.cart_table.item(0, 0).text() == "Ladies Gown"
    assert "₦2,500" in page.total_label.text()


def test_scanning_twice_increments_quantity(qtbot, session_factory, session):
    admin = make_user(session, role=ROLE_ADMIN)
    product = make_product(session, make_category(session), selling_price="1000", quantity=5)
    product.barcode = "1002"
    session.commit()

    page = _page(session_factory, admin)
    qtbot.addWidget(page)
    _scan(page, "1002")
    _scan(page, "1002")

    assert page.cart_table.rowCount() == 1
    assert page._cart[0]["quantity"] == 2
    assert "₦2,000" in page.total_label.text()


def test_scan_unknown_barcode_offers_add_product(qtbot, session_factory, session):
    admin = make_user(session, role=ROLE_ADMIN)
    session.commit()

    captured = []
    page = PosPage(
        session_factory,
        _current(admin),
        barcode_not_found_popup=lambda _parent, barcode, can_add: captured.append((barcode, can_add))
        or "add",
    )
    qtbot.addWidget(page)
    with qtbot.waitSignal(page.add_product_requested, timeout=1000):
        _scan(page, "NOPE")

    assert captured == [("NOPE", True)]
    assert page.cart_table.rowCount() == 0


def test_scan_unknown_barcode_dismiss_does_not_emit(qtbot, session_factory, session):
    admin = make_user(session, role=ROLE_ADMIN)
    session.commit()
    page = PosPage(
        session_factory,
        _current(admin),
        barcode_not_found_popup=lambda *_a, **_k: "dismiss",
    )
    qtbot.addWidget(page)
    _scan(page, "NOPE")
    assert page.cart_table.rowCount() == 0


def test_out_of_stock_product_cannot_be_added(qtbot, session_factory, session):
    admin = make_user(session, role=ROLE_ADMIN)
    product = make_product(session, make_category(session), quantity=0)
    product.barcode = "1003"
    session.commit()

    page = _page(session_factory, admin)
    qtbot.addWidget(page)
    _scan(page, "1003")

    assert page.cart_table.rowCount() == 0
    assert not page.error_label.isHidden()
    assert "out of stock" in page.error_label.text()


# --- search ----------------------------------------------------------------- #


def test_search_adds_product_to_cart(qtbot, session_factory, session):
    admin = make_user(session, role=ROLE_ADMIN)
    product = make_product(session, make_category(session), name="Agbada Special")
    session.commit()

    page = _page(session_factory, admin)
    qtbot.addWidget(page)
    page.search_input.setText("Agbada")
    assert page.search_list.count() == 1
    page.search_list.setCurrentRow(0)
    page.search_add_button.click()

    assert page.cart_table.rowCount() == 1
    assert page._cart[0]["product_id"] == product.id
    assert page.search_list.count() == 0


def test_cashier_can_search_products(qtbot, session_factory, session):
    cashier = make_user(session, role=ROLE_CASHIER)
    make_product(session, make_category(session), name="Buba")
    session.commit()

    page = _page(session_factory, cashier)
    qtbot.addWidget(page)
    page.search_input.setText("Buba")
    assert page.search_list.count() == 1


# --- cart operations -------------------------------------------------------- #


def test_remove_row_clears_cart(qtbot, session_factory, session):
    admin = make_user(session, role=ROLE_ADMIN)
    product = make_product(session, make_category(session), quantity=5)
    product.barcode = "1004"
    session.commit()

    page = _page(session_factory, admin)
    qtbot.addWidget(page)
    _scan(page, "1004")
    assert page.cart_table.rowCount() == 1

    page.cart_table.cellWidget(0, 4).click()
    assert page.cart_table.rowCount() == 0
    assert page.total_label.text().endswith("₦0")


def test_quantity_spin_updates_total(qtbot, session_factory, session):
    admin = make_user(session, role=ROLE_ADMIN)
    product = make_product(session, make_category(session), selling_price="1000", quantity=5)
    product.barcode = "1005"
    session.commit()

    page = _page(session_factory, admin)
    qtbot.addWidget(page)
    _scan(page, "1005")
    spin = page.cart_table.cellWidget(0, 1)
    spin.setValue(3)

    assert page._cart[0]["quantity"] == 3
    assert "₦3,000" in page.total_label.text()


def test_new_sale_resets_cart(qtbot, session_factory, session):
    admin = make_user(session, role=ROLE_ADMIN)
    product = make_product(session, make_category(session), quantity=5)
    product.barcode = "1006"
    session.commit()

    page = _page(session_factory, admin)
    qtbot.addWidget(page)
    _scan(page, "1006")
    page.new_sale_button.click()

    assert page.cart_table.rowCount() == 0
    assert page._cart == []
    assert page.pos_button.isChecked()


# --- customer --------------------------------------------------------------- #


def test_customer_filter_limits_combo(qtbot, session_factory, session):
    admin = make_user(session, role=ROLE_ADMIN)
    amina = make_customer(session, name="Amina Yusuf")
    make_customer(session, name="Fatima Sani")
    session.commit()

    page = _page(session_factory, admin)
    qtbot.addWidget(page)
    assert page.customer_combo.count() == 3  # placeholder + two customers

    page.customer_filter.setText("amina")
    assert page.customer_combo.count() == 1
    assert page.customer_combo.itemData(0) == amina.id
    assert page.customer_combo.currentData() == amina.id


def test_new_customer_creates_and_selects(qtbot, session_factory, session):
    admin = make_user(session, role=ROLE_ADMIN)
    session.commit()

    saved = {"customer": None}

    class StubDialog:
        def __init__(self, **kwargs):
            pass

        def exec(self):
            return True

    stub = StubDialog()
    page = PosPage(
        session_factory,
        _current(admin),
        quick_customer_dialog=lambda **kwargs: stub,
    )
    qtbot.addWidget(page)

    stub.saved = page._quick_customer_save_handler()({"name": "Walk-in Buyer"})
    page._new_customer()

    assert page.customer_combo.currentData() == stub.saved.id
    assert page.customer_filter.text() == ""


# --- discount --------------------------------------------------------------- #


def test_admin_applies_percent_discount(qtbot, session_factory, session):
    admin = make_user(session, role=ROLE_ADMIN)
    customer = make_customer(session, name="Amina")
    product = make_product(session, make_category(session), name="Gown", selling_price="10000", quantity=5)
    product.barcode = "2001"
    session.commit()

    page = _page(session_factory, admin, sale_complete_popup=_popup_new)
    qtbot.addWidget(page)
    _scan(page, "2001")
    page.discount_type_combo.setCurrentIndex(1)  # Percent
    page.discount_value_input.setText("10")
    _select_customer(page, customer)

    assert "TOTAL: ₦9,000" in page.total_label.text()

    with qtbot.waitSignal(page.sale_completed, timeout=1000):
        page.complete_button.click()

    with session_factory() as check:
        sale = check.scalar(select(Sale).order_by(Sale.id.desc()))
        assert sale.discount_type == DISCOUNT_PERCENT
        assert sale.discount_amount == Decimal("1000")
        assert sale.total == Decimal("9000")


# --- completion ------------------------------------------------------------- #


def test_complete_sale_flow(qtbot, session_factory, session):
    admin = make_user(session, role=ROLE_ADMIN)
    customer = make_customer(session, name="Amina")
    product = make_product(session, make_category(session), name="Gown", selling_price="35000", quantity=5)
    product.barcode = "3001"
    session.commit()

    printer = InMemoryPrinter()
    page = _page(
        session_factory,
        admin,
        printer=printer,
        sale_complete_popup=_popup_new,
    )
    qtbot.addWidget(page)
    _scan(page, "3001")
    _select_customer(page, customer)

    with qtbot.waitSignal(page.sale_completed, timeout=1000):
        page.complete_button.click()

    receipt_no = page.last_receipt.receipt_no
    assert receipt_no
    assert len(printer.receipts) == 1
    assert printer.receipts[0].receipt_no == receipt_no

    with session_factory() as check:
        sale = check.scalar(select(Sale).where(Sale.receipt_no == receipt_no))
        assert sale is not None
        assert sale.payment_method == PAYMENT_POS
        assert sale.total == Decimal("35000")
        assert check.get(type(product), product.id).quantity == 4

    assert page.cart_table.rowCount() == 0  # New Sale chosen after completion


def test_transfer_payment_selected(qtbot, session_factory, session):
    admin = make_user(session, role=ROLE_ADMIN)
    customer = make_customer(session)
    product = make_product(session, make_category(session), quantity=5)
    product.barcode = "3002"
    session.commit()

    page = _page(session_factory, admin, sale_complete_popup=_popup_new)
    qtbot.addWidget(page)
    _scan(page, "3002")
    _select_customer(page, customer)
    page.transfer_button.setChecked(True)
    page.payment_reference_input.setText("TRF-999")

    with qtbot.waitSignal(page.sale_completed, timeout=1000):
        page.complete_button.click()

    with session_factory() as check:
        sale = check.scalar(select(Sale).order_by(Sale.id.desc()))
        assert sale.payment_method == PAYMENT_TRANSFER
        assert sale.amount_paid == Decimal(product.selling_price)


def test_complete_sale_requires_customer(qtbot, session_factory, session):
    admin = make_user(session, role=ROLE_ADMIN)
    product = make_product(session, make_category(session), quantity=5)
    product.barcode = "3003"
    session.commit()

    page = _page(session_factory, admin)
    qtbot.addWidget(page)
    _scan(page, "3003")
    page.complete_button.click()

    assert not page.error_label.isHidden()
    assert "Select a customer" in page.error_label.text()
    with session_factory() as check:
        assert check.scalar(select(Sale)) is None


def test_complete_sale_requires_cart(qtbot, session_factory, session):
    admin = make_user(session, role=ROLE_ADMIN)
    customer = make_customer(session)
    session.commit()

    page = _page(session_factory, admin)
    qtbot.addWidget(page)
    _select_customer(page, customer)

    assert not page.complete_button.isEnabled()
    assert "ADD A PRODUCT" in page.complete_button.text()

    page.complete_button.click()

    assert page.error_label.isHidden()
    with session_factory() as check:
        assert check.scalar(select(Sale)) is None


def test_insufficient_stock_offers_clamp(qtbot, session_factory, session):
    admin = make_user(session, role=ROLE_ADMIN)
    customer = make_customer(session)
    product = make_product(session, make_category(session), quantity=1)
    product.barcode = "3004"
    session.commit()

    page = _page(
        session_factory,
        admin,
        insufficient_popup=lambda *_a, **_k: True,
        sale_complete_popup=_popup_new,
    )
    qtbot.addWidget(page)
    _scan(page, "3004")
    _select_customer(page, customer)

    page._cart[0]["quantity"] = 2
    page._refresh_summary()
    page.complete_button.click()

    assert page._cart[0]["quantity"] == 1
    with session_factory() as check:
        assert check.scalar(select(Sale)) is None


def test_print_failure_keeps_sale(qtbot, session_factory, session):
    admin = make_user(session, role=ROLE_ADMIN)
    customer = make_customer(session)
    product = make_product(session, make_category(session), quantity=5)
    product.barcode = "3005"
    session.commit()

    class BrokenPrinter:
        def print_receipt(self, receipt):
            raise OSError("no printer")

    page = _page(session_factory, admin, printer=BrokenPrinter(), sale_complete_popup=_popup_new)
    qtbot.addWidget(page)
    _scan(page, "3005")
    _select_customer(page, customer)

    with qtbot.waitSignal(page.sale_completed, timeout=1000):
        page.complete_button.click()

    with session_factory() as check:
        assert check.scalar(select(Sale)) is not None
    assert page.last_receipt is not None


# --- reprint ---------------------------------------------------------------- #


def test_admin_reprints_receipt(qtbot, session_factory, session):
    admin = make_user(session, role=ROLE_ADMIN)
    customer = make_customer(session)
    product = make_product(session, make_category(session), quantity=5)
    session.commit()
    with session_scope(session_factory) as session:
        sale = SaleService(session).complete_sale(
            admin,
            customer_id=customer.id,
            items=[{"product_id": product.id, "quantity": 1}],
            payment_method=PAYMENT_POS,
        )

    printer = InMemoryPrinter()
    page = _page(session_factory, admin, printer=printer)
    qtbot.addWidget(page)
    page.reprint_receipt(sale.receipt_no)

    assert len(printer.receipts) == 1
    assert printer.receipts[0].receipt_no == sale.receipt_no


def test_cashier_reprint_blocked(qtbot, session_factory, session):
    cashier = make_user(session, role=ROLE_CASHIER)
    session.commit()

    page = _page(session_factory, cashier)
    qtbot.addWidget(page)
    page.reprint_receipt("FUN-20260101-001")

    assert not page.error_label.isHidden()
    assert "Could not reprint" in page.error_label.text()
