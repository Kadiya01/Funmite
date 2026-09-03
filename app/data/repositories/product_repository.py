"""Product repository."""

from __future__ import annotations

from sqlalchemy import Integer, func, or_, select
from sqlalchemy.orm import selectinload

from app.data.models import LOW_STOCK_THRESHOLD, Product
from app.data.repositories.base import BaseRepository


class ProductRepository(BaseRepository[Product]):
    """Data access for the product catalogue."""

    model = Product

    def get_by_barcode(self, barcode: str) -> Product | None:
        return self.get_by(barcode=barcode)

    def get_by_product_code(self, product_code: str) -> Product | None:
        return self.get_by(product_code=product_code)

    def list_active(self) -> list[Product]:
        statement = select(Product).where(Product.is_active.is_(True)).order_by(Product.name)
        return list(self.session.scalars(statement))

    def search(
        self,
        query: str,
        *,
        category_id: int | None = None,
        include_inactive: bool = False,
        limit: int = 50,
    ) -> list[Product]:
        """Fast catalogue search across name, product code and barcode.

        Supports an optional category filter and, for the Admin catalogue
        screen, optionally including deactivated products.
        """
        term = f"%{query.strip()}%"
        conditions = [
            or_(
                Product.name.ilike(term),
                Product.product_code.ilike(term),
                Product.barcode.ilike(term),
            )
        ]
        if not include_inactive:
            conditions.append(Product.is_active.is_(True))
        if category_id is not None:
            conditions.append(Product.category_id == category_id)

        statement = (
            select(Product)
            .options(selectinload(Product.category))
            .where(*conditions)
            .order_by(Product.name)
            .limit(limit)
        )
        return list(self.session.scalars(statement))

    def max_numeric_barcode(self) -> int | None:
        """Largest numeric barcode value in the catalogue (``None`` if none).

        Only all-digit barcodes are considered; imported or legacy values that
        contain letters are ignored by the generator.
        """
        statement = select(func.max(func.cast(Product.barcode, Integer))).where(
            Product.barcode.op("GLOB")("[0-9]*")
        )
        return self.session.scalar(statement)

    def max_code_number(self, prefix: str) -> int:
        """Largest numeric suffix among codes like ``<prefix>-<digits>``."""
        like = f"{prefix}-%"
        offset = len(prefix) + 1
        rows = self.session.scalars(
            select(Product.product_code).where(Product.product_code.like(like))
        )
        maximum = 0
        for code in rows:
            suffix = code[offset:]
            if suffix.isdigit():
                maximum = max(maximum, int(suffix))
        return maximum

    def list_low_stock(self, *, threshold: int = LOW_STOCK_THRESHOLD) -> list[Product]:
        """Confirmed rule: a product is low when quantity <= 3 (threshold)."""
        statement = (
            select(Product)
            .where(Product.is_active.is_(True), Product.quantity <= threshold)
            .order_by(Product.quantity, Product.name)
        )
        return list(self.session.scalars(statement))
