"""Products page UI tests (Phase 03)."""

from __future__ import annotations

from PySide6.QtWidgets import QTableWidget

from app.data.db import session_scope
from app.data.models import ROLE_ADMIN
from app.domain.services.product_service import ProductService
from app.domain.session import CurrentUser
from app.ui.products import ProductsPage
from tests.factories import make_user


def _admin_user(session) -> CurrentUser:
    user = make_user(session, username="admin", role=ROLE_ADMIN)
    session.commit()
    return CurrentUser(
        user_id=user.id,
        username=user.username,
        full_name=user.full_name,
        role=user.role,
    )


def _create_product(session_factory, user: CurrentUser, **kwargs) -> None:
    with session_scope(session_factory) as session:
        ProductService(session).create(
            user,
            name=kwargs.get("name", "Product"),
            category=kwargs.get("category", "Cat"),
            cost_price=kwargs.get("cost_price", "1000"),
            selling_price=kwargs.get("selling_price", "2000"),
            barcode=kwargs.get("barcode"),
        )


def _build_page(qtbot, session_factory, session, **product_kwargs):
    current_user = _admin_user(session)
    if product_kwargs:
        _create_product(session_factory, current_user, **product_kwargs)
    page = ProductsPage(session_factory, current_user)
    qtbot.addWidget(page)
    return page


def test_page_lists_products(qtbot, session_factory, session):
    current_user = _admin_user(session)
    _create_product(session_factory, current_user, name="Ankara", barcode="1234567890128")
    _create_product(session_factory, current_user, name="Kaftan", barcode="1000000000009")

    page = ProductsPage(session_factory, current_user)
    qtbot.addWidget(page)

    table = page.table
    assert isinstance(table, QTableWidget)
    assert table.rowCount() == 2
    assert page.count_label.text() == "2 product(s)"


def test_scan_finds_and_selects_product(qtbot, session_factory, session):
    page = _build_page(
        qtbot, session_factory, session, name="Ankara", barcode="1234567890128"
    )
    page.scan_input.setText("1234567890128")
    page.scan_input.returnPressed.emit()
    assert page.table.selectionModel().hasSelection() is True


def test_search_filters_rows(qtbot, session_factory, session):
    page = _build_page(qtbot, session_factory, session, name="Ankara", barcode="1234567890128")
    _create_product(session_factory, page.current_user, name="Shoes")

    page.search_input.setText("ankara")
    assert page.table.rowCount() == 1


def test_create_handler_creates_product(session_factory, session):
    current_user = _admin_user(session)
    page = ProductsPage(session_factory, current_user)
    page._create_handler()(
        {
            "name": "New Item",
            "category": "New Category",
            "brand": "Verity",
            "size": "L",
            "color": "Red",
            "cost_price": "1500",
            "selling_price": "2500",
            "quantity": "10",
            "minimum_stock": "3",
            "product_code": "",
        }
    )
    with session_factory() as check:
        from app.data.repositories.product_repository import ProductRepository

        products = ProductRepository(check).search("New Item")
        assert len(products) == 1
        assert products[0].barcode
        assert products[0].category.name == "New Category"


def test_category_filter_loads_categories(qtbot, session_factory, session):
    current_user = _admin_user(session)
    _create_product(session_factory, current_user, name="Ankara", category="Dresses")
    page = ProductsPage(session_factory, current_user)
    qtbot.addWidget(page)
    assert page.category_filter.count() == 2  # "All categories" + "Dresses"
