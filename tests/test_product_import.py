"""Product bulk import service tests (Phase 03).

Covers the acceptance point: the import validates every row first, rejects bad
rows without corrupting data, creates categories and products, generates codes
and barcodes when absent, and reports per-row errors.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.data.models import ROLE_ADMIN, ROLE_CASHIER, Product
from app.domain.errors import AuthorizationError
from app.domain.services.product_import import (
    DEFAULT_TEMPLATE_HEADER,
    ProductImportService,
)
from tests.factories import make_category, make_product, make_user

VALID_CSV = (
    "Name,Category,Brand,Size,Color,Cost Price,Selling Price,Quantity,Minimum Stock,Product Code,Barcode\n"
    "Ankara Dress,Dresses,Verity,L,Red,1500,2500,10,3,PRD-001,1234567890128\n"
    "Kaftan,Kaftan,,XL,,1000,2000,5,2,, \n"
    "Agbada,Agbada,,XXL,Blue,5000,8000,2,1,PRD-003,\n"
)


def _admin(session):
    return make_user(session, role=ROLE_ADMIN)


def _created_products(session) -> list[Product]:
    return list(session.scalars(select(Product).order_by(Product.name)))


def test_import_creates_products_and_categories(session):
    result = ProductImportService(session).import_csv(_admin(session), VALID_CSV)
    assert result.total == 3
    assert result.created == 3
    assert result.errors == []
    assert result.fatal_error is None

    products = _created_products(session)
    assert len(products) == 3
    names = {product.name for product in products}
    assert names == {"Ankara Dress", "Kaftan", "Agbada"}
    assert {product.category.name for product in products} == {"Dresses", "Kaftan", "Agbada"}


def test_import_keeps_explicit_values(session):
    result = ProductImportService(session).import_csv(_admin(session), VALID_CSV)
    assert result.created == 3
    ankara = next(p for p in _created_products(session) if p.name == "Ankara Dress")
    assert ankara.product_code == "PRD-001"
    assert ankara.barcode == "1234567890128"
    assert ankara.cost_price == Decimal("1500")
    assert ankara.selling_price == Decimal("2500")
    assert ankara.quantity == 10
    assert ankara.minimum_stock == 3
    assert ankara.brand == "Verity"
    assert ankara.size == "L"
    assert ankara.color == "Red"


def test_import_generates_codes_and_barcodes(session):
    result = ProductImportService(session).import_csv(_admin(session), VALID_CSV)
    assert result.created == 3
    kaftan = next(p for p in _created_products(session) if p.name == "Kaftan")
    assert kaftan.product_code == "PRD-000001"
    assert kaftan.barcode.isdigit() and len(kaftan.barcode) == 13
    codes = [p.product_code for p in _created_products(session)]
    assert len(set(codes)) == 3


def test_import_reports_bad_rows_and_imports_valid_ones(session):
    csv_text = (
        "Name,Category,Cost Price,Selling Price\n"
        "Good Product,Dresses,1000,2000\n"
        ",Dresses,1000,2000\n"
        "Bad Price,Dresses,abc,2000\n"
    )
    result = ProductImportService(session).import_csv(_admin(session), csv_text)
    assert result.total == 3
    assert result.created == 1
    assert len(result.errors) == 2
    assert {error.row_number for error in result.errors} == {3, 4}
    assert [p.name for p in _created_products(session)] == ["Good Product"]


def test_import_rejects_duplicate_code_within_file(session):
    csv_text = (
        "Name,Category,Cost Price,Selling Price,Product Code\n"
        "One,Dresses,1000,2000,PRD-X\n"
        "Two,Dresses,1000,2000,PRD-X\n"
    )
    result = ProductImportService(session).import_csv(_admin(session), csv_text)
    assert result.created == 1
    assert any("appears twice" in error.message for error in result.errors)


def test_import_rejects_duplicate_barcode_within_file(session):
    csv_text = (
        "Name,Category,Cost Price,Selling Price,Barcode\n"
        "One,Dresses,1000,2000,1234567890128\n"
        "Two,Dresses,1000,2000,1234567890128\n"
    )
    result = ProductImportService(session).import_csv(_admin(session), csv_text)
    assert result.created == 1
    assert any("appears twice" in error.message for error in result.errors)


def test_import_rejects_duplicate_code_against_database(session):
    category = make_category(session)
    existing = make_product(session, category, name="Existing")
    existing.product_code = "PRD-EXIST"
    session.flush()

    csv_text = "Name,Category,Cost Price,Selling Price,Product Code\nNew,Dresses,1000,2000,PRD-EXIST\n"
    result = ProductImportService(session).import_csv(_admin(session), csv_text)
    assert result.created == 0
    assert any("already exists" in error.message for error in result.errors)


def test_import_rejects_duplicate_barcode_against_database(session):
    category = make_category(session)
    existing = make_product(session, category, name="Existing")
    existing.barcode = "1234567890128"
    session.flush()

    csv_text = "Name,Category,Cost Price,Selling Price,Barcode\nNew,Dresses,1000,2000,1234567890128\n"
    result = ProductImportService(session).import_csv(_admin(session), csv_text)
    assert result.created == 0
    assert any("already exists" in error.message for error in result.errors)


def test_import_missing_required_columns_rejected(session):
    csv_text = "Name,Category\nOnly Name,Dresses\n"
    result = ProductImportService(session).import_csv(_admin(session), csv_text)
    assert result.created == 0
    assert len(result.errors) == 1


def test_import_empty_file_fails(session):
    result = ProductImportService(session).import_csv(_admin(session), " \n")
    assert result.fatal_error is not None
    assert result.created == 0


def test_import_accepts_header_aliases(session):
    csv_text = (
        "Product Name,Category Name,Cost,Selling Price,Qty,Min Stock\n"
        "Trousers,Trousers,1200,2000,4,2\n"
    )
    result = ProductImportService(session).import_csv(_admin(session), csv_text)
    assert result.created == 1
    assert _created_products(session)[0].name == "Trousers"


def test_import_rolls_back_on_integrity_error(session, monkeypatch):
    def explode(self, user, records):
        raise IntegrityError("boom", {}, Exception("boom"))

    monkeypatch.setattr(ProductImportService, "_write_rows", explode)
    result = ProductImportService(session).import_csv(_admin(session), VALID_CSV)
    assert result.has_fatal_error is True
    assert result.created == 0
    assert _created_products(session) == []


def test_import_requires_admin_permission(session):
    cashier = make_user(session, role=ROLE_CASHIER)
    with pytest.raises(AuthorizationError):
        ProductImportService(session).import_csv(cashier, VALID_CSV)


def test_sample_template_documented(session):
    assert ProductImportService.sample_template() == DEFAULT_TEMPLATE_HEADER
