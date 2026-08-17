"""Expense service (Phase 07).

The approved expense workflow (UC-12, Engineering Artifact 02):

    Admin records a business expense for net-profit reporting.

Confirmed rules enforced here (source-of-truth artifacts):

- Admin is the only user allowed to manage expenses (``CAP_MANAGE_EXPENSES``).
- An expense must have a non-empty category, a positive amount, and an expense
  date.
- The ``category`` field is free-text; the allowed set is an open decision
  (see ``OPEN_DECISIONS.md``).
- Expenses are deducted from gross profit to produce net profit (Phase 08
  reports). Phase 07 records the data; Phase 08 consumes it.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from app.data.models import Expense
from app.data.repositories.expense_repository import ExpenseRepository
from app.domain.errors import NotFoundError, ValidationError
from app.domain.permissions import CAP_MANAGE_EXPENSES, require_permission
from app.domain.rules.validation import parse_decimal
from app.domain.session import user_record_id
from app.domain.services.sync_service import SyncService


class ExpenseService:
    """Use-case service for recording business expenses."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.repo = ExpenseRepository(session)

    def _sync(self) -> SyncService:
        return SyncService(self.session)

    def list_expenses(
        self,
        user,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
        category: str | None = None,
    ) -> list[Expense]:
        """List expenses, newest first. Admin-only."""
        require_permission(user, CAP_MANAGE_EXPENSES)
        return self.repo.list_expenses(start=start, end=end, category=category)

    def get_expense(self, user, expense_id: int) -> Expense:
        """Get an expense by id. Admin-only."""
        require_permission(user, CAP_MANAGE_EXPENSES)
        expense = self.repo.get_with_details(expense_id)
        if expense is None:
            raise NotFoundError("Expense not found.")
        return expense

    def create_expense(
        self,
        user,
        *,
        category: str,
        amount: Decimal | str | int,
        description: str | None = None,
        expense_date: datetime | None = None,
    ) -> Expense:
        """Record a business expense. Admin-only."""
        require_permission(user, CAP_MANAGE_EXPENSES)

        category = (category or "").strip()
        if not category:
            raise ValidationError("Expense category is required.")

        amt = parse_decimal(amount, "amount", minimum=Decimal("0.01"))
        expense_date = expense_date or datetime.now()

        expense = Expense(
            category=category,
            description=description.strip() if description else None,
            amount=amt,
            expense_date=expense_date,
            created_by=user_record_id(user),
        )
        self.session.add(expense)
        self.session.flush()
        self._sync().enqueue_create("expense", expense.id, {
            "sync_uuid": expense.sync_uuid,
            "category": expense.category,
            "description": expense.description,
            "amount": str(expense.amount),
            "expense_date": str(expense.expense_date),
            "created_by": expense.created_by,
        })
        return expense

    def update_expense(
        self,
        user,
        expense_id: int,
        *,
        category: str | None = None,
        amount: Decimal | str | int | None = None,
        description: str | None = None,
    ) -> Expense:
        """Update an existing expense. Admin-only."""
        require_permission(user, CAP_MANAGE_EXPENSES)

        expense = self.repo.get_with_details(expense_id)
        if expense is None:
            raise NotFoundError("Expense not found.")

        if category is not None:
            category = category.strip()
            if not category:
                raise ValidationError("Expense category is required.")
            expense.category = category
        if amount is not None:
            expense.amount = parse_decimal(amount, "amount", minimum=Decimal("0.01"))
        if description is not None:
            expense.description = description.strip() if description else None
        self.session.flush()
        self._sync().enqueue_update("expense", expense.id, {
            "sync_uuid": expense.sync_uuid,
            "category": expense.category,
            "description": expense.description,
            "amount": str(expense.amount),
            "expense_date": str(expense.expense_date),
        })
        return expense
