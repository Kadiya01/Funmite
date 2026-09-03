"""Sale repository."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select

from app.data.models import Sale
from app.data.repositories.base import BaseRepository


class SaleRepository(BaseRepository[Sale]):
    """Data access for sale headers."""

    model = Sale

    def get_by_receipt_no(self, receipt_no: str) -> Sale | None:
        return self.get_by(receipt_no=receipt_no)

    def max_receipt_sequence(self, prefix: str) -> int:
        """Largest numeric suffix among receipt numbers like ``<prefix>001``.

        ``prefix`` includes everything before the sequence, e.g.
        ``"FUN-20260816-"``. Receipt numbers never have a fixed width, so the
        maximum is found by scanning the matching suffix, not by string length.
        """
        offset = len(prefix)
        rows = self.session.scalars(
            select(Sale.receipt_no).where(Sale.receipt_no.like(f"{prefix}%"))
        )
        maximum = 0
        for value in rows:
            suffix = value[offset:]
            if suffix.isdigit():
                maximum = max(maximum, int(suffix))
        return maximum

    def list_between(self, start: datetime, end: datetime) -> list[Sale]:
        """Sales with ``sale_date`` within [start, end] (inclusive at the start)."""
        statement = (
            select(Sale)
            .where(Sale.sale_date >= start, Sale.sale_date <= end)
            .order_by(Sale.sale_date)
        )
        return list(self.session.scalars(statement))

    def list_by_cashier(self, cashier_id: int) -> list[Sale]:
        statement = select(Sale).where(Sale.cashier_id == cashier_id).order_by(Sale.sale_date)
        return list(self.session.scalars(statement))
