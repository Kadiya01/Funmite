"""Exchange screen tests (Phase 06).

Qt-level coverage of the exchange page: finding the original receipt, selecting
the returned item from the sale, searching and selecting a replacement, the live
difference label, the Admin-only POS/Transfer payment radios, the confirm/complete
popups, the full exchange flow including stock changes, and error handling.
Also tests the Admin-only Exchange button on the PosPage title bar.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.data.db import session_scope
from app.data.models import (
    DIFFERENCE_CUSTOMER_PAYS,
    EXCHANGE_COMPLETED,
    PAYMENT_POS,
    PAYMENT_TRANSFER,
    ROLE_ADMIN,
    ROLE_CASHIER,
    Exchange,
    InventoryLog,
)
from app.domain.services.exchange_service import EXCHANGE_RETURN_REASON, REFERENCE_EXCHANGE
from app.domain.services.sale_service import SaleService
from app.domain.session import CurrentUser
from app.ui.exchanges.exchange_dialog import ExchangeDialog
from app.ui.exchanges.exchange_page import ExchangePage
from app.ui.pos.pos_page import PosPage
from tests.factories import (
    make_category,
    make_customer,
    make_product,
    make_recent_sale,
    make_user,
)

def _current(user) -> CurrentUser:
    return CurrentUser(
        user_id=user.id,
        username=user.username,
        full_name=user.full_name,
        role=user.role,
    )


def _page(session_factory, user, **kwargs) -> ExchangePage:
    return ExchangePage(session_factory, _current(user), **kwargs)


def _pos_page(session_factory, user, **kwargs) -> PosPage:
    return PosPage(session_factory, _current(user), **kwargs)


class _StubDialog:
    def __init__(self, **kwargs):
        self._kwargs = kwargs
        self.exec_called = False
        self.page = kwargs.get("page", None)

    def exec(self):
        self.exec_called = True
        return True


class _RejectDialog:
    def __init__(self, **kwargs):
        pass

    def exec(self):
        return False


def _confirm_yes(*_a, **_kw):
    return True


def _confirm_no(*_a, **_kw):
    return False


# --- construction ---------------------------------------------------------- #


def test_exchange_page_constructed(qtbot, session_factory, session):
    admin = make_user(session, role=ROLE_ADMIN)
    session.commit()
    page = _page(session_factory, admin)
    qtbot.addWidget(page)
    assert page.find_button.text() == "FIND"
    assert page.complete_button.text() == "ADMIN APPROVE & COMPLETE EXCHANGE"


# --- find sale -------------------------------------------------------------- #


def test_find_sale_populates_info_and_return_combo(qtbot, session_factory, session):
    admin = make_user(session, role=ROLE_ADMIN)
    customer = make_customer(session, name="Amina")
    gown = make_product(
        session, make_category(session), name="Gown", selling_price=Decimal("35000"), quantity=10
    )
    sale = make_recent_sale(session, customer, admin, days_old=1, items=[(gown, 1)])
    session.commit()

    page = _page(session_factory, admin)
    qtbot.addWidget(page)
    page.receipt_input.setText(sale.receipt_no)
    page.find_button.click()

    assert not page.sale_info_label.isHidden()
    assert "Amina" in page.sale_info_label.text()
    assert "Gown" in page.return_combo.currentText()
    assert page.return_combo.count() == 1


def test_find_unknown_receipt_shows_error(qtbot, session_factory, session):
    admin = make_user(session, role=ROLE_ADMIN)
    session.commit()

    page = _page(session_factory, admin)
    qtbot.addWidget(page)
    page.receipt_input.setText("FUN-NOT-FOUND")
    page.find_button.click()

    assert not page.error_label.isHidden()
    assert "No sale found" in page.error_label.text()


def test_find_empty_receipt_shows_error(qtbot, session_factory, session):
    admin = make_user(session, role=ROLE_ADMIN)
    session.commit()

    page = _page(session_factory, admin)
    qtbot.addWidget(page)
    page.find_button.click()

    assert not page.error_label.isHidden()
    assert "Enter a receipt number" in page.error_label.text()


def test_cashier_cannot_find_sale(qtbot, session_factory, session):
    cashier = make_user(session, role=ROLE_CASHIER)
    customer = make_customer(session, name="Amina")
    gown = make_product(session, make_category(session), name="Gown", quantity=10)
    sale = make_recent_sale(session, customer, cashier, days_old=1, items=[(gown, 1)])
    session.commit()

    page = _page(session_factory, cashier)
    qtbot.addWidget(page)
    page.receipt_input.setText(sale.receipt_no)
    page.find_button.click()

    assert not page.error_label.isHidden()
    assert "does not have permission" in page.error_label.text()

# --- return item ----------------------------------------------------------- #


def test_return_combo_populated_from_sale_items(qtbot, session_factory, session):
    admin = make_user(session, role=ROLE_ADMIN)
    customer = make_customer(session, name="Amina")
    gown = make_product(
        session, make_category(session), name="Gown", selling_price=Decimal("35000"), quantity=10
    )
    top = make_product(
        session, make_category(session), name="Top", selling_price=Decimal("10000"), quantity=10
    )
    sale = make_recent_sale(session, customer, admin, days_old=1, items=[(gown, 1), (top, 2)])
    session.commit()

    page = _page(session_factory, admin)
    qtbot.addWidget(page)
    page.receipt_input.setText(sale.receipt_no)
    page.find_button.click()

    assert page.return_combo.count() == 2
    texts = [page.return_combo.itemText(i) for i in range(page.return_combo.count())]
    assert any("Gown" in t for t in texts)
    assert any("Top" in t for t in texts)


def test_return_qty_spin_max_set_from_sale(qtbot, session_factory, session):
    admin = make_user(session, role=ROLE_ADMIN)
    customer = make_customer(session, name="Amina")
    gown = make_product(
        session, make_category(session), name="Gown", selling_price=Decimal("35000"), quantity=10
    )
    top = make_product(
        session, make_category(session), name="Top", selling_price=Decimal("10000"), quantity=10
    )
    sale = make_recent_sale(session, customer, admin, days_old=1, items=[(gown, 1), (top, 3)])
    session.commit()

    page = _page(session_factory, admin)
    qtbot.addWidget(page)
    page.receipt_input.setText(sale.receipt_no)
    page.find_button.click()

    # Select Top (2nd item, qty 3)
    page.return_combo.setCurrentIndex(1)
    assert page.return_qty_spin.maximum() == 3
    assert page.return_qty_spin.value() == 1


# --- replacement search ---------------------------------------------------- #


def test_replacement_search_populates_results(qtbot, session_factory, session):
    admin = make_user(session, role=ROLE_ADMIN)
    customer = make_customer(session, name="Amina")
    gown = make_product(
        session, make_category(session), name="Gown", selling_price=Decimal("35000"), quantity=10
    )
    ankara = make_product(
        session, make_category(session), name="Ankara Gown", selling_price=Decimal("40000"), quantity=6
    )
    sale = make_recent_sale(session, customer, admin, days_old=1, items=[(gown, 1)])
    session.commit()

    page = _page(session_factory, admin)
    qtbot.addWidget(page)
    page.receipt_input.setText(sale.receipt_no)
    page.find_button.click()

    page.replacement_search.setText("Ankara")
    assert page.replacement_results.count() == 1
    assert page._search_results[0].id == ankara.id


def test_add_replacement_populates_readout_and_spin(qtbot, session_factory, session):
    admin = make_user(session, role=ROLE_ADMIN)
    customer = make_customer(session, name="Amina")
    gown = make_product(
        session, make_category(session), name="Gown", selling_price=Decimal("35000"), quantity=10
    )
    ankara = make_product(
        session, make_category(session), name="Ankara", selling_price=Decimal("40000"), quantity=6
    )
    sale = make_recent_sale(session, customer, admin, days_old=1, items=[(gown, 1)])
    session.commit()

    page = _page(session_factory, admin)
    qtbot.addWidget(page)
    page.receipt_input.setText(sale.receipt_no)
    page.find_button.click()

    page.replacement_search.setText("Ankara")
    page.replacement_results.setCurrentRow(0)
    page.replacement_add.click()

    assert page._replacement_product_id == ankara.id
    assert page.replacement_qty_spin.maximum() == 6
    assert "Ankara" in page.replacement_readout.text()


def test_add_without_selecting_results_shows_error(qtbot, session_factory, session):
    admin = make_user(session, role=ROLE_ADMIN)
    customer = make_customer(session, name="Amina")
    gown = make_product(
        session, make_category(session), name="Gown", selling_price=Decimal("35000"), quantity=10
    )
    sale = make_recent_sale(session, customer, admin, days_old=1, items=[(gown, 1)])
    session.commit()

    page = _page(session_factory, admin)
    qtbot.addWidget(page)
    page.receipt_input.setText(sale.receipt_no)
    page.find_button.click()

    page.replacement_add.click()
    assert not page.error_label.isHidden()
    assert "Select a replacement product" in page.error_label.text()


# --- live difference ------------------------------------------------------- #


def test_difference_label_updates_live(qtbot, session_factory, session):
    admin = make_user(session, role=ROLE_ADMIN)
    customer = make_customer(session, name="Amina")
    gown = make_product(
        session, make_category(session), name="Gown", selling_price=Decimal("35000"), quantity=10
    )
    ankara = make_product(
        session, make_category(session), name="Ankara", selling_price=Decimal("40000"), quantity=10
    )
    sale = make_recent_sale(session, customer, admin, days_old=1, items=[(gown, 1)])
    session.commit()

    page = _page(session_factory, admin)
    qtbot.addWidget(page)
    page.receipt_input.setText(sale.receipt_no)
    page.find_button.click()

    page.replacement_search.setText("Ankara")
    page.replacement_results.setCurrentRow(0)
    page.replacement_add.click()

    # Initially 1x35000 return vs 1x40000 replacement = 5000 diff
    assert "5,000" in page.difference_label.text()
    assert page.pos_button.isEnabled()

    # Change return qty to 2 (but max is 1 for this sale)
    page.return_qty_spin.setMaximum(2)
    page.return_qty_spin.setValue(2)
    # Now 2x35000=70000 returned vs 1x40000=40000 = customer owed
    assert "refund" in page.difference_label.text().lower()
    assert not page.pos_button.isEnabled()


def test_no_difference_when_prices_equal(qtbot, session_factory, session):
    admin = make_user(session, role=ROLE_ADMIN)
    customer = make_customer(session, name="Amina")
    gown = make_product(
        session, make_category(session), name="Gown", selling_price=Decimal("35000"), quantity=10
    )
    gown2 = make_product(
        session, make_category(session), name="Gown Copy", selling_price=Decimal("35000"), quantity=10
    )
    sale = make_recent_sale(session, customer, admin, days_old=1, items=[(gown, 1)])
    session.commit()

    page = _page(session_factory, admin)
    qtbot.addWidget(page)
    page.receipt_input.setText(sale.receipt_no)
    page.find_button.click()

    page.replacement_search.setText("Gown Copy")
    page.replacement_results.setCurrentRow(0)
    page.replacement_add.click()

    assert "No difference" in page.difference_label.text()
    assert not page.pos_button.isEnabled()
    assert not page.transfer_button.isEnabled()


# --- payment radios -------------------------------------------------------- #


def test_payment_buttons_disabled_until_difference_positive(qtbot, session_factory, session):
    admin = make_user(session, role=ROLE_ADMIN)
    customer = make_customer(session, name="Amina")
    gown = make_product(
        session, make_category(session), name="Gown", selling_price=Decimal("35000"), quantity=10
    )
    sale = make_recent_sale(session, customer, admin, days_old=1, items=[(gown, 1)])
    session.commit()

    page = _page(session_factory, admin)
    qtbot.addWidget(page)
    page.receipt_input.setText(sale.receipt_no)
    page.find_button.click()

    # Before replacement: no difference label, payment disabled
    assert not page.pos_button.isEnabled()


# --- complete exchange flow ------------------------------------------------- #


def test_complete_exchange_flow(qtbot, session_factory, session):
    admin = make_user(session, role=ROLE_ADMIN)
    customer = make_customer(session, name="Amina")
    gown = make_product(
        session, make_category(session), name="Gown", selling_price=Decimal("35000"), quantity=10
    )
    ankara = make_product(
        session, make_category(session), name="Ankara", selling_price=Decimal("40000"), quantity=6
    )
    sale = make_recent_sale(session, customer, admin, days_old=1, items=[(gown, 1)])
    session.commit()

    page = _page(
        session_factory,
        admin,
        confirm_popup=_confirm_yes,
        complete_popup=lambda *_a, **_k: None,
    )
    qtbot.addWidget(page)
    page.receipt_input.setText(sale.receipt_no)
    page.find_button.click()

    page.replacement_search.setText("Ankara")
    page.replacement_results.setCurrentRow(0)
    page.replacement_add.click()

    page.complete_button.click()

    with session_factory() as check:
        exchange = check.scalar(select(Exchange).order_by(Exchange.id.desc()))
        assert exchange is not None
        assert exchange.status == EXCHANGE_COMPLETED
        assert exchange.original_sale_id == sale.id
        assert exchange.payment_method == PAYMENT_POS
        assert check.get(type(gown), gown.id).quantity == 10  # 9 restored to 10
        assert check.get(type(ankara), ankara.id).quantity == 5  # 6 - 1


def test_confirm_popup_blocks_exchange(qtbot, session_factory, session):
    admin = make_user(session, role=ROLE_ADMIN)
    customer = make_customer(session, name="Amina")
    gown = make_product(
        session, make_category(session), name="Gown", selling_price=Decimal("35000"), quantity=10
    )
    ankara = make_product(
        session, make_category(session), name="Ankara", selling_price=Decimal("40000"), quantity=6
    )
    sale = make_recent_sale(session, customer, admin, days_old=1, items=[(gown, 1)])
    session.commit()

    page = _page(
        session_factory,
        admin,
        confirm_popup=_confirm_no,
    )
    qtbot.addWidget(page)
    page.receipt_input.setText(sale.receipt_no)
    page.find_button.click()

    page.replacement_search.setText("Ankara")
    page.replacement_results.setCurrentRow(0)
    page.replacement_add.click()

    page.complete_button.click()

    with session_factory() as check:
        assert check.scalar(select(Exchange)) is None


def test_exchange_complete_emits_signal(qtbot, session_factory, session):
    admin = make_user(session, role=ROLE_ADMIN)
    customer = make_customer(session, name="Amina")
    gown = make_product(
        session, make_category(session), name="Gown", selling_price=Decimal("35000"), quantity=10
    )
    ankara = make_product(
        session, make_category(session), name="Ankara", selling_price=Decimal("40000"), quantity=6
    )
    sale = make_recent_sale(session, customer, admin, days_old=1, items=[(gown, 1)])
    session.commit()

    page = _page(
        session_factory,
        admin,
        confirm_popup=_confirm_yes,
        complete_popup=lambda *_a, **_k: None,
    )
    qtbot.addWidget(page)
    page.receipt_input.setText(sale.receipt_no)
    page.find_button.click()

    page.replacement_search.setText("Ankara")
    page.replacement_results.setCurrentRow(0)
    page.replacement_add.click()

    with qtbot.waitSignal(page.exchange_completed, timeout=1000):
        page.complete_button.click()


# --- errors / edge cases --------------------------------------------------- #


def test_complete_without_finding_sale_shows_error(qtbot, session_factory, session):
    admin = make_user(session, role=ROLE_ADMIN)
    session.commit()

    page = _page(session_factory, admin)
    qtbot.addWidget(page)
    page.complete_button.click()
    assert not page.error_label.isHidden()
    assert "Find the original receipt" in page.error_label.text()


def test_complete_without_replacement_shows_error(qtbot, session_factory, session):
    admin = make_user(session, role=ROLE_ADMIN)
    customer = make_customer(session, name="Amina")
    gown = make_product(
        session, make_category(session), name="Gown", selling_price=Decimal("35000"), quantity=10
    )
    sale = make_recent_sale(session, customer, admin, days_old=1, items=[(gown, 1)])
    session.commit()

    page = _page(session_factory, admin)
    qtbot.addWidget(page)
    page.receipt_input.setText(sale.receipt_no)
    page.find_button.click()

    page.complete_button.click()
    assert not page.error_label.isHidden()
    assert "Select a replacement product" in page.error_label.text()


def test_exchange_expired_shows_error_on_complete(qtbot, session_factory, session):
    admin = make_user(session, role=ROLE_ADMIN)
    customer = make_customer(session, name="Amina")
    gown = make_product(
        session, make_category(session), name="Gown", selling_price=Decimal("35000"), quantity=10
    )
    ankara = make_product(
        session, make_category(session), name="Ankara", selling_price=Decimal("40000"), quantity=6
    )
    sale = make_recent_sale(session, customer, admin, days_old=3, items=[(gown, 1)])
    session.commit()

    page = _page(
        session_factory,
        admin,
        confirm_popup=_confirm_yes,
    )
    qtbot.addWidget(page)
    page.receipt_input.setText(sale.receipt_no)
    page.find_button.click()

    # Select return product from combo
    page.return_combo.setCurrentIndex(0)

    page.replacement_search.setText("Ankara")
    page.replacement_results.setCurrentRow(0)
    page.replacement_add.click()

    page.complete_button.click()
    assert not page.error_label.isHidden()
    assert "window" in page.error_label.text().lower()

    with session_factory() as check:
        assert check.scalar(select(Exchange)) is None


def test_exchange_dialog_can_be_constructed(qtbot, session_factory, session):
    admin = make_user(session, role=ROLE_ADMIN)
    session.commit()
    dialog = ExchangeDialog(session_factory, _current(admin))
    qtbot.addWidget(dialog)
    assert dialog.windowTitle() == "Exchange"


# --- PosPage Exchange button ---------------------------------------------- #


def test_admin_sees_exchange_button(qtbot, session_factory, session):
    admin = make_user(session, role=ROLE_ADMIN)
    session.commit()

    page = _pos_page(session_factory, admin)
    qtbot.addWidget(page)
    assert hasattr(page, "exchange_button")
    assert not page.exchange_button.isHidden()


def test_cashier_does_not_see_exchange_button(qtbot, session_factory, session):
    cashier = make_user(session, role=ROLE_CASHIER)
    session.commit()

    page = _pos_page(session_factory, cashier)
    qtbot.addWidget(page)
    assert not hasattr(page, "exchange_button")


def test_pos_page_exchange_opens_dialog(qtbot, session_factory, session):
    admin = make_user(session, role=ROLE_ADMIN)
    session.commit()

    captured = []

    def fake_dialog(**kwargs):
        d = _StubDialog(**kwargs)
        captured.append(d)
        return d

    page = _pos_page(session_factory, admin, exchange_dialog_factory=fake_dialog)
    qtbot.addWidget(page)
    page.exchange_button.click()

    assert len(captured) == 1
    assert captured[0].exec_called
