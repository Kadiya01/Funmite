"""Exchange repository."""

from __future__ import annotations

from sqlalchemy import func, select

from app.data.models import EXCHANGE_COMPLETED, Exchange, ExchangeItem
from app.data.repositories.base import BaseRepository


class ExchangeRepository(BaseRepository[Exchange]):
    """Data access for exchange headers and their item lines."""

    model = Exchange

    def list_for_sale(self, sale_id: int) -> list[Exchange]:
        statement = (
            select(Exchange)
            .where(Exchange.original_sale_id == sale_id)
            .order_by(Exchange.exchange_date)
        )
        return list(self.session.scalars(statement))

    def exchanged_quantities_for_sale(self, sale_id: int) -> dict[int, int]:
        """Total quantity already returned per product across completed
        exchanges of ``sale_id``.

        Used to stop a product from being returned more times than it was sold
        on the original receipt (duplicate/over-exchange protection).
        """
        statement = (
            select(ExchangeItem.original_product_id, func.sum(ExchangeItem.original_quantity))
            .join(Exchange, Exchange.id == ExchangeItem.exchange_id)
            .where(
                Exchange.original_sale_id == sale_id,
                Exchange.status == EXCHANGE_COMPLETED,
            )
            .group_by(ExchangeItem.original_product_id)
        )
        return {
            product_id: int(total)
            for product_id, total in self.session.execute(statement)
        }
