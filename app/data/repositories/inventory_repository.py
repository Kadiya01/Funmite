"""Inventory log repository."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.data.models import InventoryLog
from app.data.repositories.base import BaseRepository


class InventoryLogRepository(BaseRepository[InventoryLog]):
    """Data access for the stock-movement audit trail."""

    model = InventoryLog

    def list_by_product(self, product_id: int) -> list[InventoryLog]:
        statement = (
            select(InventoryLog)
            .where(InventoryLog.product_id == product_id)
            .order_by(InventoryLog.created_at)
        )
        return list(self.session.scalars(statement))

    def list_between(self, start: datetime, end: datetime) -> list[InventoryLog]:
        statement = (
            select(InventoryLog)
            .where(InventoryLog.created_at >= start, InventoryLog.created_at <= end)
            .order_by(InventoryLog.created_at)
        )
        return list(self.session.scalars(statement))

    def list_recent(
        self,
        *,
        product_id: int | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = 200,
    ) -> list[InventoryLog]:
        """Newest-first movement history with the product and user eager-loaded.

        ``product_id`` filters to one product; ``start``/``end`` filter by
        ``created_at``; ``limit`` caps the returned rows (newest first).
        """
        conditions = []
        if product_id is not None:
            conditions.append(InventoryLog.product_id == product_id)
        if start is not None:
            conditions.append(InventoryLog.created_at >= start)
        if end is not None:
            conditions.append(InventoryLog.created_at <= end)

        statement = (
            select(InventoryLog)
            .options(selectinload(InventoryLog.product), selectinload(InventoryLog.user))
            .where(*conditions)
            .order_by(InventoryLog.created_at.desc(), InventoryLog.id.desc())
            .limit(limit)
        )
        return list(self.session.scalars(statement))
