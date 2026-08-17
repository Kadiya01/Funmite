"""Product catalogue service tests (Phase 03).

Covers the acceptance points: Admin-only product management, system-generated
product codes and barcodes, uniqueness, search/filter, and scanner lookup.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import select

from app.data.models import ROLE_ADMIN, ROLE_CASHIER, Product
from app.domain.errors import AuthorizationError, NotFoundError, ValidationError
from app.domain.services.product_service import PRODUCT_CODE_PREFIX, ProductService
from tests.factories import make_category, make_product, make_user


def _product(session, **kwargs) -> Product:
    return make_product(session, make_category(session), **kwargs)


def test_create_generates_code_and_unique_barcode(session):
    user = make_user(session, role=ROLE_ADMIN)
    product = ProductService(session).create(
        user, name="Ankara Dress", category="Dresses", cost_price="1500", selling_price="2500"
    )
    session.flush()

    assert product.product_code == f"{PRODUCT_CODE_PREFIX}-000001"
    assert product.barcode.isdigit()
    assert len(product.barcode) == 13
    assert product.category.name == "Dresses"
    assert product.cost_price == Decimal("1500")
    assert product.selling_price == Decimal("2500")
    assert product.quantity == 0
    assert product.minimum_stock == 3
    assert product.is_active is True


def test_create_with_explicit_code_and_barcode(session):
    user = make_user(session, role=ROLE_ADMIN)
    product = ProductService(session).create(
        user,
        name="Kaftan",
        category="Kaftan",
        cost_price="1000",
        selling_price="2000",
        product_code="PRD-CUSTOM",
        barcode="1234567890128",
    )
    session.flush()
    assert product.product_code == "PRD-CUSTOM"
    assert product.barcode == "1234567890128"


def test_create_requires_name(session):
    user = make_user(session, role=ROLE_ADMIN)
    with pytest.raises(ValidationError):
        ProductService(session).create(user, name=" ", category="X", cost_price="1", selling_price="2")


def test_create_duplicate_product_code_rejected(session):
    user = make_user(session, role=ROLE_ADMIN)
    existing = _product(session, name="First")
    existing.product_code = "PRD-999999"
    session.flush()
    with pytest.raises(ValidationError) as exc:
        ProductService(session).create(
            user,
            name="Second",
            category="X",
            cost_price="1",
            selling_price="2",
            product_code="PRD-999999",
        )
    assert "already exists" in str(exc.value)


def test_create_duplicate_barcode_rejected(session):
    user = make_user(session, role=ROLE_ADMIN)
    existing = _product(session, name="First")
    existing.barcode = "1234567890128"
    session.flush()
    with pytest.raises(ValidationError) as exc:
        ProductService(session).create(
            user,
            name="Second",
            category="X",
            cost_price="1",
            selling_price="2",
            barcode="1234567890128",
        )
    assert "already exists" in str(exc.value)


def test_create_negative_quantity_rejected(session):
    user = make_user(session, role=ROLE_ADMIN)
    with pytest.raises(ValidationError):
        ProductService(session).create(
            user, name="X", category="X", cost_price="1", selling_price="2", quantity="-1"
        )


def test_cashier_cannot_create_product(session):
    user = make_user(session, role=ROLE_CASHIER)
    with pytest.raises(AuthorizationError):
        ProductService(session).create(user, name="X", category="X", cost_price="1", selling_price="2")


def test_update_name_and_price(session):
    admin = make_user(session, role=ROLE_ADMIN)
    product = _product(session, name="Old", cost_price="1000", selling_price="2000")
    updated = ProductService(session).update(
        admin, product.id, name="New", selling_price="2500"
    )
    assert updated.name == "New"
    assert updated.selling_price == Decimal("2500")
    assert updated.cost_price == Decimal("1000")


def test_cashier_cannot_update_product(session):
    cashier = make_user(session, role=ROLE_CASHIER)
    product = _product(session)
    with pytest.raises(AuthorizationError):
        ProductService(session).update(cashier, product.id, name="X")


def test_update_duplicate_product_code_rejected(session):
    admin = make_user(session, role=ROLE_ADMIN)
    first = _product(session, name="First")
    second = _product(session, name="Second")
    first.product_code = "PRD-111"
    second.product_code = "PRD-222"
    session.flush()
    with pytest.raises(ValidationError):
        ProductService(session).update(admin, second.id, product_code="PRD-111")


def test_deactivate_and_activate(session):
    admin = make_user(session, role=ROLE_ADMIN)
    product = _product(session)
    assert ProductService(session).deactivate(admin, product.id).is_active is False
    assert ProductService(session).activate(admin, product.id).is_active is True


def test_get_unknown_product_raises(session):
    user = make_user(session, role=ROLE_ADMIN)
    with pytest.raises(NotFoundError):
        ProductService(session).get(999999)


def test_lookup_by_barcode(session):
    cashier = make_user(session, role=ROLE_CASHIER)
    product = _product(session, name="Ankara")
    product.barcode = "1234567890128"
    session.flush()
    found = ProductService(session).lookup_by_barcode(cashier, "1234567890128")
    assert found is not None
    assert found.name == "Ankara"
    assert ProductService(session).lookup_by_barcode(cashier, "9999999999999") is None
    assert ProductService(session).lookup_by_barcode(cashier, "") is None


def test_search_by_name_code_and_barcode(session):
    cashier = make_user(session, role=ROLE_CASHIER)
    category = make_category(session, name="Dresses")
    product = make_product(session, category, name="Ankara Dress")
    product.product_code = "PRD-SEARCH"
    product.barcode = "1234567890128"
    session.flush()
    service = ProductService(session)
    assert [p.id for p in service.search_products(cashier, "ankara")] == [product.id]
    assert [p.id for p in service.search_products(cashier, "PRD-SEARCH")] == [product.id]
    assert [p.id for p in service.search_products(cashier, "1234567890128")] == [product.id]


def test_search_category_filter_and_inactive(session):
    cashier = make_user(session, role=ROLE_CASHIER)
    dresses = make_category(session, name="Dresses")
    shoes = make_category(session, name="Shoes")
    active = make_product(session, dresses, name="Ankara Dress")
    inactive = make_product(session, shoes, name="Old Shoes")
    inactive.is_active = False
    session.flush()

    service = ProductService(session)
    results = service.search_products(cashier, "an", category_id=dresses.id)
    assert [p.id for p in results] == [active.id]

    all_results = service.search_products(cashier, "", include_inactive=True)
    assert {p.id for p in all_results} == {active.id, inactive.id}


def test_cashier_can_search_products(session):
    cashier = make_user(session, role=ROLE_CASHIER)
    product = _product(session)
    session.flush()
    assert ProductService(session).search_products(cashier, product.name) != []
