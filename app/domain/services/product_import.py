"""Bulk product import for the large catalogue (Phase 03).

The exact import columns are a pending client decision (see
``OPEN_DECISIONS.md``); until confirmed this service implements a documented
default CSV template and maps column headers flexibly by name. Behavior:

- the whole import runs in one transaction,
- every row is validated BEFORE anything is written,
- invalid rows are reported per-row and are never written,
- valid rows are imported atomically (a fatal error rolls back everything),
- existing ``product_code``/``barcode`` values (in the file or the database)
  are reported as duplicates and never overwritten.

Importing updates existing records is intentionally NOT implemented; that
behavior needs an explicit client decision.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.barcode.codes import NumericBarcodeGenerator
from app.data.models import DEFAULT_MINIMUM_STOCK, Category, Product
from app.domain.errors import ValidationError
from app.domain.permissions import CAP_CREATE_PRODUCT, require_permission
from app.domain.rules.validation import parse_decimal, parse_quantity
from app.domain.services.category_service import CategoryService
from app.domain.services.product_service import PRODUCT_CODE_PREFIX, ProductService

DEFAULT_TEMPLATE_HEADER = (
    "Name,Category,Brand,Size,Color,Cost Price,Selling Price,"
    "Quantity,Minimum Stock,Product Code,Barcode"
)

_COLUMN_ALIASES = {
    "name": ("name", "product name"),
    "category": ("category", "category name"),
    "brand": ("brand",),
    "size": ("size",),
    "color": ("color", "colour"),
    "cost_price": ("cost price", "cost", "cost_price"),
    "selling_price": ("selling price", "selling", "price", "selling_price"),
    "quantity": ("quantity", "qty", "stock"),
    "minimum_stock": ("minimum stock", "min stock", "min", "minimum_stock"),
    "product_code": ("product code", "code", "product_code"),
    "barcode": ("barcode",),
}

DEFAULT_COLUMN_ORDER = (
    "name",
    "category",
    "brand",
    "size",
    "color",
    "cost_price",
    "selling_price",
    "quantity",
    "minimum_stock",
    "product_code",
    "barcode",
)


def _normalize_header(value: str) -> str:
    return " ".join(value.strip().lower().split())


def _header_to_field(cell: str) -> str | None:
    normalized = _normalize_header(cell)
    for field_name, aliases in _COLUMN_ALIASES.items():
        if normalized in aliases or normalized == field_name:
            return field_name
    return None


@dataclass(frozen=True)
class RowError:
    """A single rejected import row."""

    row_number: int
    message: str


@dataclass
class ImportResult:
    """Outcome of an import run."""

    total: int = 0
    created: int = 0
    errors: list[RowError] = field(default_factory=list)
    fatal_error: str | None = None

    @property
    def skipped(self) -> int:
        return self.total - self.created

    @property
    def has_fatal_error(self) -> bool:
        return self.fatal_error is not None

    def summary(self) -> str:
        lines = [
            f"{self.total} row(s) read, {self.created} product(s) created.",
        ]
        if self.skipped:
            lines.append(f"{self.skipped} row(s) skipped.")
        if self.fatal_error:
            lines.append(f"Import failed: {self.fatal_error}")
        if self.errors:
            lines.append(f"{len(self.errors)} error(s):")
            for error in self.errors[:5]:
                lines.append(f"  Row {error.row_number}: {error.message}")
            if len(self.errors) > 5:
                lines.append(f"  ... and {len(self.errors) - 5} more.")
        return "\n".join(lines)


class ProductImportService:
    """Validates and imports product rows from a CSV document."""

    def __init__(
        self,
        session: Session,
        *,
        barcode_generator: NumericBarcodeGenerator | None = None,
    ) -> None:
        self.session = session
        self.products = ProductService(session, barcode_generator=barcode_generator)
        self.categories = CategoryService(session)
        self.barcodes = self.products.barcodes

    @staticmethod
    def sample_template() -> str:
        """A ready-to-fill CSV header for the Admin (documentation/help)."""
        return DEFAULT_TEMPLATE_HEADER

    def import_file(self, user, path: str | Path) -> ImportResult:
        """Read a CSV file and import it. Encoding is UTF-8 (BOM tolerated)."""
        data = Path(path).read_bytes()
        text = data.decode("utf-8-sig")
        return self.import_csv(user, text)

    def import_csv(self, user, csv_text: str, *, has_header: bool = True) -> ImportResult:
        require_permission(user, CAP_CREATE_PRODUCT)

        reader = csv.reader(io.StringIO(csv_text))
        rows = [row for row in reader if any(cell.strip() for cell in row)]

        if not rows:
            return ImportResult(fatal_error="The file contains no rows.")

        if has_header:
            header = rows[0]
            columns = [_header_to_field(cell) for cell in header]
            data_rows = rows[1:]
        else:
            columns = list(DEFAULT_COLUMN_ORDER)
            data_rows = rows

        if not data_rows:
            return ImportResult(total=0, errors=[])

        result = ImportResult(total=len(data_rows))
        valid_rows: list[dict] = []
        seen_codes: set[str] = set()
        seen_barcodes: set[str] = set()

        for index, cells in enumerate(data_rows):
            row_number = index + (2 if has_header else 1)
            record, message = self._validate_row(columns, cells, seen_codes, seen_barcodes)
            if record is None:
                result.errors.append(RowError(row_number=row_number, message=message))
                continue
            valid_rows.append(record)

        if result.errors and not valid_rows:
            return result

        try:
            self._write_rows(user, valid_rows)
        except IntegrityError:
            self.session.rollback()
            result.fatal_error = (
                "A duplicate slipped through validation; the import was rolled "
                "back and nothing was written."
            )
            result.created = 0
            result.errors = []
            return result
        except Exception:
            self.session.rollback()
            result.fatal_error = "Unexpected error; the import was rolled back."
            result.created = 0
            result.errors = []
            return result

        result.created = len(valid_rows)
        return result

    # --- validation ------------------------------------------------------- #

    def _validate_row(
        self,
        columns: list[str | None],
        cells: list[str],
        seen_codes: set[str],
        seen_barcodes: set[str],
    ) -> tuple[dict | None, str]:
        values = {field_name: "" for field_name in _COLUMN_ALIASES}
        for position, cell in enumerate(cells):
            if position >= len(columns) or columns[position] is None:
                continue
            values[columns[position]] = cell.strip()

        try:
            name = values["name"].strip()
            if not name:
                raise ValidationError("Name is required.")

            category = values["category"].strip()
            if not category:
                raise ValidationError("Category is required.")

            cost = parse_decimal(values["cost_price"], "cost price")
            selling = parse_decimal(values["selling_price"], "selling price")
            quantity = parse_quantity(values["quantity"] or "0", "quantity", minimum=0)
            minimum = (
                parse_quantity(values["minimum_stock"], "minimum stock", minimum=0)
                if values["minimum_stock"]
                else DEFAULT_MINIMUM_STOCK
            )

            product_code = values["product_code"].strip()
            if product_code:
                if product_code in seen_codes:
                    raise ValidationError(f"Product code '{product_code}' appears twice in the file.")
                if self.products.products.get_by_product_code(product_code) is not None:
                    raise ValidationError(f"Product code '{product_code}' already exists.")
                seen_codes.add(product_code)

            barcode = values["barcode"].strip()
            if barcode:
                if barcode in seen_barcodes:
                    raise ValidationError(f"Barcode '{barcode}' appears twice in the file.")
                if self.products.products.get_by_barcode(barcode) is not None:
                    raise ValidationError(f"Barcode '{barcode}' already exists.")
                self.barcodes.reserve(barcode)
            seen_barcodes.add(barcode)
        except ValidationError as exc:
            return None, str(exc)

        return {
            "name": name,
            "category": category,
            "brand": values["brand"].strip() or None,
            "size": values["size"].strip() or None,
            "color": values["color"].strip() or None,
            "cost_price": cost,
            "selling_price": selling,
            "quantity": quantity,
            "minimum_stock": minimum,
            "product_code": product_code,
            "barcode": barcode,
        }, ""

    # --- writing ---------------------------------------------------------- #

    def _write_rows(self, user, records: list[dict]) -> None:
        categories = self._resolve_categories(user, [record["category"] for record in records])

        self._file_codes = {record["product_code"] for record in records if record["product_code"]}
        missing_codes = [record for record in records if not record["product_code"]]
        generated_codes = self._next_codes(len(missing_codes))
        for record, code in zip(missing_codes, generated_codes):
            record["product_code"] = code

        missing_barcodes = [record for record in records if not record["barcode"]]
        generated_barcodes = self.barcodes.generate_many(self.session, len(missing_barcodes))
        for record, value in zip(missing_barcodes, generated_barcodes):
            record["barcode"] = value

        for record in records:
            category = categories[_normalize_header(record["category"])]
            self.session.add(
                Product(
                    product_code=record["product_code"],
                    name=record["name"],
                    category_id=category.id,
                    brand=record["brand"],
                    size=record["size"],
                    color=record["color"],
                    cost_price=Decimal(record["cost_price"]),
                    selling_price=Decimal(record["selling_price"]),
                    quantity=record["quantity"],
                    minimum_stock=record["minimum_stock"],
                    barcode=record["barcode"],
                    is_active=True,
                )
            )
        self.session.flush()

    def _resolve_categories(self, user, names: list[str]) -> dict[str, Category]:
        categories = {}
        for name in names:
            key = _normalize_header(name)
            if key not in categories:
                categories[key] = self.categories.get_or_create(user, name)
        return categories

    def _next_codes(self, count: int) -> list[str]:
        current = self.products.products.max_code_number(PRODUCT_CODE_PREFIX)
        codes: list[str] = []
        for _ in range(count):
            current += 1
            code = f"{PRODUCT_CODE_PREFIX}-{current:06d}"
            while code in self._file_codes:
                current += 1
                code = f"{PRODUCT_CODE_PREFIX}-{current:06d}"
            codes.append(code)
        return codes
