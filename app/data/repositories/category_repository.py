"""Category repository."""

from __future__ import annotations

from sqlalchemy import func, select

from app.data.models import Category
from app.data.repositories.base import BaseRepository


class CategoryRepository(BaseRepository[Category]):
    """Data access for product categories."""

    model = Category

    def get_by_name(self, name: str) -> Category | None:
        return self.get_by(name=name)

    def get_by_name_ci(self, name: str) -> Category | None:
        """Look up a category by name, ignoring case."""
        statement = select(Category).where(func.lower(Category.name) == func.lower(name)).limit(1)
        return self.session.scalar(statement)

    def list_all(self) -> list[Category]:
        statement = select(Category).order_by(Category.name)
        return list(self.session.scalars(statement))
