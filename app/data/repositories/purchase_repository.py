"""Purchase data access."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.data.models import Purchase
from app.data.repositories.base import BaseRepository


class PurchaseRepository(BaseRepository[Purchase]):
    model = Purchase

    def list_purchases(
        self,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
        supplier_id: int | None = None,
        limit: int = 200,
    ) -> list[Purchase]:
        stmt = select(Purchase).options(
            joinedload(Purchase.supplier),
            joinedload(Purchase.created_by_user),
            joinedload(Purchase.items),
        )
        if start is not None:
            stmt = stmt.where(Purchase.purchase_date >= start)
        if end is not None:
            stmt = stmt.where(Purchase.purchase_date <= end)
        if supplier_id is not None:
            stmt = stmt.where(Purchase.supplier_id == supplier_id)
        stmt = stmt.order_by(Purchase.purchase_date.desc(), Purchase.id.desc()).limit(limit)
        return list(self.session.scalars(stmt).unique())

    def get_with_details(self, purchase_id: int) -> Purchase | None:
        stmt = (
            select(Purchase)
            .options(
                joinedload(Purchase.supplier),
                joinedload(Purchase.created_by_user),
                joinedload(Purchase.items),
            )
            .where(Purchase.id == purchase_id)
        )
        return self.session.scalars(stmt).unique().one_or_none()
