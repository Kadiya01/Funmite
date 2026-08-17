"""Input validation helpers shared by the application services.

Money and quantity values come from the UI/import as untrusted text; these
helpers turn them into typed values and raise ``ValidationError`` with a
user-facing message instead of letting a ``ValueError``/``TypeError`` escape.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from app.domain.errors import ValidationError


def parse_decimal(value, label: str, *, minimum: Decimal | None = None) -> Decimal:
    """Parse ``value`` as a non-negative Decimal for a money field."""
    try:
        number = Decimal(str(value).strip())
    except (InvalidOperation, ValueError, TypeError):
        raise ValidationError(f"{label} must be a valid number.") from None
    if not number.is_finite():
        raise ValidationError(f"{label} must be a valid number.")
    if number < 0:
        raise ValidationError(f"{label} cannot be negative.")
    if minimum is not None and number < minimum:
        raise ValidationError(f"{label} cannot be less than {minimum}.")
    return number


def parse_quantity(value, label: str = "quantity", *, minimum: int = 0) -> int:
    """Parse ``value`` as an integer quantity at least ``minimum``."""
    if isinstance(value, bool):
        raise ValidationError(f"{label} must be a whole number.")
    if isinstance(value, float) and not value.is_integer():
        raise ValidationError(f"{label} must be a whole number.")
    try:
        number = int(str(value).strip())
    except (TypeError, ValueError):
        raise ValidationError(f"{label} must be a whole number.") from None
    if number < minimum:
        raise ValidationError(f"{label} cannot be less than {minimum}.")
    return number


def parse_signed_quantity(value, label: str = "stock change") -> int:
    """Parse ``value`` as any whole number (positive, zero or negative).

    Used for the signed change of a stock movement: a sale deducts, stock-in
    adds, and an adjustment may do either.
    """
    if isinstance(value, bool):
        raise ValidationError(f"{label} must be a whole number.")
    if isinstance(value, float) and not value.is_integer():
        raise ValidationError(f"{label} must be a whole number.")
    try:
        number = int(str(value).strip())
    except (TypeError, ValueError):
        raise ValidationError(f"{label} must be a whole number.") from None
    return number
