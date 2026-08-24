"""Product barcode generation tests (Phase 03).

Covers the acceptance point: barcodes the system generates must be unique,
scan-safe (Luhn check digit) and deterministic above the largest existing value.
"""

from __future__ import annotations

from app.barcode.codes import (
    BARCODE_DIGIT_COUNT,
    Luhn,
    NumericBarcodeGenerator,
)
from app.data.models import Product
from app.data.repositories.product_repository import ProductRepository
from tests.factories import make_category, make_product


class _StubRepository:
    def __init__(self, maximum: int | None = None):
        self.maximum = maximum

    def max_numeric_barcode(self):
        return self.maximum


def test_luhn_check_digit_is_correct():
    # "100000000000" -> "9" (verified against the standard algorithm).
    assert Luhn.check_digit("100000000000") == "9"


def test_luhn_is_valid_accepts_correct_value():
    assert Luhn.is_valid("1000000000009") is True
    assert Luhn.is_valid("1000000000001") is False


def test_luhn_rejects_non_numeric_or_short():
    assert Luhn.is_valid("abc") is False
    assert Luhn.is_valid("1") is False
    assert Luhn.is_valid("") is False


def test_generator_emits_unique_13_digit_luhn_valid_values():
    generator = NumericBarcodeGenerator(repository=_StubRepository())
    values = generator.generate_many(None, 25)
    assert len(values) == 25
    assert len(set(values)) == 25
    for value in values:
        assert value.isdigit()
        assert len(value) == BARCODE_DIGIT_COUNT + 1
        assert Luhn.is_valid(value)


def test_generator_starts_above_existing_maximum():
    generator = NumericBarcodeGenerator(repository=_StubRepository(maximum=100_000_000_055))
    values = generator.generate_many(None, 3)
    assert all(int(value[:-1]) > 100_000_000_055 for value in values)


def test_generator_respects_seed_when_database_is_empty():
    generator = NumericBarcodeGenerator(seed=50_000_000_000, repository=_StubRepository(None))
    value = generator.generate(None)
    assert value.startswith("50000000000")


def test_reserved_values_are_never_reused():
    generator = NumericBarcodeGenerator(repository=_StubRepository())
    generator.reserve("1000000000009")
    values = generator.generate_many(None, 3)
    assert "1000000000009" not in values


def test_generated_barcodes_are_unique_in_database(session):
    category = make_category(session)
    for _ in range(5):
        product = make_product(session, category)
        session.delete(product)
        session.flush()
    session.commit()

    generator = NumericBarcodeGenerator(repository=ProductRepository(session))
    values = generator.generate_many(session, 5)
    assert len(set(values)) == 5


def test_max_numeric_barcode_ignores_non_numeric_values(session):
    category = make_category(session)
    for _ in range(2):
        product = make_product(session, category)
        session.delete(product)
        session.flush()
    session.add(
        Product(
            product_code="P-SPECIAL",
            name="Non numeric",
            category_id=category.id,
            cost_price=1,
            selling_price=2,
            quantity=1,
            barcode="ABC123",
        )
    )
    session.flush()
    assert ProductRepository(session).max_numeric_barcode() is None


def test_barcode_format_specification():
    """Product barcode must be 13-digit numeric with Luhn check (RESOLVED decision)."""
    generator = NumericBarcodeGenerator(repository=_StubRepository())
    value = generator.generate(None)
    assert len(value) == 13, "Barcode must be 13 digits"
    assert value.isdigit(), "Barcode must be numeric only"
    assert Luhn.is_valid(value), "Barcode must pass Luhn check"
    assert int(value) >= 100_000_000_000, "Barcode body must be 12 digits"
