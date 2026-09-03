"""Supplier data access."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.data.models import Supplier
from app.data.repositories.base import BaseRepository


class SupplierRepository(BaseRepository[Supplier]):
    model = Supplier

    def list_suppliers(self, *, search: str | None = None, limit: int = 200) -> list[Supplier]:
        stmt = select(Supplier)
        if search:
            pattern = f"%{search}%"
            stmt = stmt.where(
                Supplier.name.ilike(pattern)
                | Supplier.phone.ilike(pattern)
            )
        stmt = stmt.order_by(Supplier.name).limit(limit)
        return list(self.session.scalars(stmt))

    def count(self) -> int:
        return int(self.session.scalar(select(func.count()).select_from(Supplier)) or 0)
