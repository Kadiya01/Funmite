"""Unique product barcode generation.

The shop's products have no barcodes, so the system generates one per product
(confirmed requirement). The generator produces 13-digit numeric values — a
12-digit sequence plus a Luhn check digit for scan-error detection. The exact
label symbology/format is a pending client decision (see ``OPEN_DECISIONS.md``);
until it is confirmed we render these values as Code128, which a generic
scanner reads back as the same plain digits.

Uniqueness is guaranteed in three layers:

1. the candidate counter starts above the largest existing numeric barcode,
2. values handed out within one batch are remembered so they are never repeated,
3. the database ``UNIQUE`` constraint on ``products.barcode`` is the final guard.
"""

from __future__ import annotations

from app.data.repositories.product_repository import ProductRepository

BARCODE_DIGIT_COUNT = 12
DEFAULT_BARCODE_SEED = 100_000_000_000


class Luhn:
    """Modulo-10 (Luhn) check digit for scan-error detection.

    This is a generic check digit; it does not claim GS1/EAN semantics.
    """

    @staticmethod
    def check_digit(value: str) -> str:
        """Return the single check digit that makes ``value`` Luhn-valid."""
        total = 0
        for index, digit in enumerate(reversed(value)):
            digit = int(digit)
            doubled = digit * 2 if index % 2 == 0 else digit
            total += doubled - 9 if doubled > 9 else doubled
        return str((10 - total % 10) % 10)

    @staticmethod
    def is_valid(value: str) -> bool:
        """Whether ``value`` (body + check digit) passes the Luhn check."""
        if not value.isdigit() or len(value) < 2:
            return False
        return Luhn.check_digit(value[:-1]) == value[-1]


class NumericBarcodeGenerator:
    """Generates unique 13-digit barcode values for new products.

    ``repository`` is injectable for testing; when omitted a
    ``ProductRepository`` is built from the session passed to the methods.
    """

    def __init__(self, *, seed: int | None = None, repository=None) -> None:
        self._seed = seed or DEFAULT_BARCODE_SEED
        self._repository = repository
        self._next: int | None = None
        self._used: set[str] = set()

    def reserve(self, value: str) -> None:
        """Block ``value`` from being generated (e.g. barcodes from an import)."""
        if value:
            self._used.add(value)

    def generate(self, session) -> str:
        """Generate one unique barcode value for a new product."""
        return self.generate_many(session, 1)[0]

    def generate_many(self, session, count: int) -> list[str]:
        """Generate ``count`` unique barcode values in one pass.

        Designed for bulk import: the database maximum is read once and the
        candidates are produced strictly above it, so no per-row query is
        needed.
        """
        repository = self._repository or ProductRepository(session)
        if self._next is None:
            existing = repository.max_numeric_barcode()
            self._next = max(self._seed, (existing or 0) + 1)

        values: list[str] = []
        for _ in range(count):
            candidate = self._candidate()
            while candidate in self._used:
                candidate = self._candidate()
            self._used.add(candidate)
            values.append(candidate)
        return values

    def _candidate(self) -> str:
        body = str(self._next)
        self._next += 1
        return body + Luhn.check_digit(body)
