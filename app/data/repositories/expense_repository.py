"""Expense data access."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.data.models import Expense
from app.data.repositories.base import BaseRepository


class ExpenseRepository(BaseRepository[Expense]):
    model = Expense

    def list_expenses(
        self,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
        category: str | None = None,
        limit: int = 200,
    ) -> list[Expense]:
        stmt = select(Expense).options(
            joinedload(Expense.created_by_user),
        )
        if start is not None:
            stmt = stmt.where(Expense.expense_date >= start)
        if end is not None:
            stmt = stmt.where(Expense.expense_date <= end)
        if category is not None:
            stmt = stmt.where(Expense.category == category)
        stmt = stmt.order_by(Expense.expense_date.desc(), Expense.id.desc()).limit(limit)
        return list(self.session.scalars(stmt).unique())

    def get_with_details(self, expense_id: int) -> Expense | None:
        stmt = (
            select(Expense)
            .options(joinedload(Expense.created_by_user))
            .where(Expense.id == expense_id)
        )
        return self.session.scalars(stmt).unique().one_or_none()
