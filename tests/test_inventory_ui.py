"""Inventory page UI tests (Phase 04)."""

from __future__ import annotations

from app.data.db import session_scope
from app.data.models import ROLE_ADMIN
from app.domain.session import CurrentUser
from app.ui.inventory import InventoryPage
from tests.factories import make_category, make_product, make_user


def _admin_user(session) -> CurrentUser:
    user = make_user(session, username="admin", role=ROLE_ADMIN)
    session.commit()
    return CurrentUser(
        user_id=user.id,
        username=user.username,
        full_name=user.full_name,
        role=user.role,
    )


def _product_id(session_factory, *, name="Gown", quantity=5):
    with session_factory() as session:
        product = make_product(session, make_category(session), name=name, quantity=quantity)
        session.commit()
        return product.id


def _current_quantity(session_factory, product_id) -> int:
    from app.data.models import Product

    with session_factory() as session:
        return session.get(Product, product_id).quantity


class _Recorder:
    """Stub low-stock alerter that records the calls it receives."""

    def __init__(self, *, result: bool = False) -> None:
        self.result = result
        self.calls: list[list] = []

    def __call__(self, parent, products):
        self.calls.append(list(products))
        return self.result


def _build_page(qtbot, session_factory, session, *, alerter: _Recorder | None = None):
    current_user = _admin_user(session)
    alerter = alerter or _Recorder()
    page = InventoryPage(session_factory, current_user, low_stock_alerter=alerter)
    qtbot.addWidget(page)
    return page, alerter


def _select_product(combo, product_id: int) -> None:
    index = combo.findData(product_id)
    assert index >= 0
    combo.setCurrentIndex(index)


def test_page_has_wireframe_tabs(qtbot, session_factory, session):
    page, _ = _build_page(qtbot, session_factory, session)
    assert [page.tabs.tabText(i) for i in range(page.tabs.count())] == [
        "Current Stock",
        "Stock In",
        "Adjust",
        "Movement",
        "Low Stock",
    ]


def test_current_stock_tab_lists_products_with_status(qtbot, session_factory, session):
    product_id = _product_id(session_factory, name="Gown", quantity=5)
    low_id = _product_id(session_factory, name="Top", quantity=2)

    page, _ = _build_page(qtbot, session_factory, session)

    assert page.stock_table.rowCount() == 2
    statuses = [page.stock_table.item(row, 3).text() for row in range(2)]
    assert "LOW" in statuses and "OK" in statuses
    assert page.stock_count_label.text() == "2 product(s)"
    assert product_id is not None and low_id is not None


def test_stock_in_updates_quantity_without_alert(qtbot, session_factory, session):
    product_id = _product_id(session_factory, name="Gown", quantity=5)
    page, alerter = _build_page(qtbot, session_factory, session)

    _select_product(page.stock_in_product, product_id)
    page.stock_in_quantity.setText("7")
    page.stock_in_button.click()

    assert _current_quantity(session_factory, product_id) == 12
    assert alerter.calls == []
    assert page.stock_in_quantity.text() == ""


def test_adjust_triggers_low_stock_alert(qtbot, session_factory, session):
    product_id = _product_id(session_factory, name="Gown", quantity=5)
    alerter = _Recorder(result=True)
    page, _ = _build_page(qtbot, session_factory, session, alerter=alerter)

    _select_product(page.adjust_product, product_id)
    page.adjust_new_quantity.setText("2")
    page.adjust_reason.setText("Physical count")
    page.adjust_button.click()

    assert _current_quantity(session_factory, product_id) == 2
    assert len(alerter.calls) == 1
    assert alerter.calls[0][0].id == product_id
    assert page.tabs.currentIndex() == 4  # View Stock switched to the Low Stock tab


def test_adjust_no_alert_when_stock_still_ok(qtbot, session_factory, session):
    product_id = _product_id(session_factory, name="Gown", quantity=5)
    alerter = _Recorder(result=True)
    page, _ = _build_page(qtbot, session_factory, session, alerter=alerter)

    _select_product(page.adjust_product, product_id)
    page.adjust_new_quantity.setText("4")
    page.adjust_reason.setText("Count")
    page.adjust_button.click()

    assert _current_quantity(session_factory, product_id) == 4
    assert alerter.calls == []


def test_adjust_requires_reason(qtbot, session_factory, session):
    product_id = _product_id(session_factory, name="Gown", quantity=5)
    page, _ = _build_page(qtbot, session_factory, session)

    _select_product(page.adjust_product, product_id)
    page.adjust_new_quantity.setText("2")
    page.adjust_button.click()

    assert not page.adjust_error.isHidden()
    assert _current_quantity(session_factory, product_id) == 5


def test_stock_in_shows_error_for_bad_quantity(qtbot, session_factory, session):
    product_id = _product_id(session_factory, name="Gown", quantity=5)
    page, _ = _build_page(qtbot, session_factory, session)

    _select_product(page.stock_in_product, product_id)
    page.stock_in_quantity.setText("abc")
    page.stock_in_button.click()

    assert not page.stock_in_error.isHidden()
    assert _current_quantity(session_factory, product_id) == 5


def test_low_stock_tab_lists_low_products(qtbot, session_factory, session):
    _product_id(session_factory, name="Gown", quantity=3)
    _product_id(session_factory, name="Top", quantity=8)

    page, _ = _build_page(qtbot, session_factory, session)

    assert page.low_stock_table.rowCount() == 1
    assert page.low_stock_table.item(0, 0).text() == "Gown"
    assert "1 product(s) are low" in page.low_stock_label.text()


def test_movement_tab_records_stock_actions(qtbot, session_factory, session):
    product_id = _product_id(session_factory, name="Gown", quantity=5)
    page, _ = _build_page(qtbot, session_factory, session)

    _select_product(page.stock_in_product, product_id)
    page.stock_in_quantity.setText("3")
    page.stock_in_button.click()

    assert page.movement_table.rowCount() == 1
    assert page.movement_table.item(0, 2).text() == "+3"
    assert page.movement_table.item(0, 3).text() == "5"
    assert page.movement_table.item(0, 4).text() == "8"
    assert page.movement_count_label.text() == "1 movement(s)"
