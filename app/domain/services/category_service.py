"""Product category service.

Categories belong to the Admin-managed product catalogue. The permission matrix
in Engineering Artifact 02 has no separate ``categories`` capability, so
creating categories is gated by ``CAP_CREATE_PRODUCT`` (Admin) — the catalogue
management capability.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.data.models import Category
from app.data.repositories.category_repository import CategoryRepository
from app.domain.errors import ValidationError
from app.domain.permissions import CAP_CREATE_PRODUCT, require_permission
from app.domain.services.sync_service import SyncService


class CategoryService:
    """Use-case service for managing product categories."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.repo = CategoryRepository(session)

    def _sync(self) -> SyncService:
        return SyncService(self.session)

    def create(self, user, name: str) -> Category:
        """Create a category with a unique name (Admin only)."""
        require_permission(user, CAP_CREATE_PRODUCT)
        name = (name or "").strip()
        if not name:
            raise ValidationError("Category name is required.")
        if self.repo.get_by_name_ci(name) is not None:
            raise ValidationError(f"Category '{name}' already exists.")
        category = Category(name=name)
        self.repo.add(category)
        self.session.flush()
        self._sync().enqueue_create("category", category.id, {
            "sync_uuid": category.sync_uuid, "name": category.name,
        })
        return category

    def get_or_create(self, user, name: str) -> Category:
        """Return the category with ``name`` (case-insensitive), creating it if needed.

        Used by product entry and bulk import so a new category name never
        fails a product save. Admin only.
        """
        require_permission(user, CAP_CREATE_PRODUCT)
        name = (name or "").strip()
        if not name:
            raise ValidationError("Category name is required.")
        existing = self.repo.get_by_name_ci(name)
        if existing is not None:
            return existing
        category = Category(name=name)
        self.repo.add(category)
        self.session.flush()
        self._sync().enqueue_create("category", category.id, {
            "sync_uuid": category.sync_uuid, "name": category.name,
        })
        return category

    def rename(self, user, category_id: int, new_name: str) -> Category:
        """Rename a category, keeping its name unique (Admin only)."""
        require_permission(user, CAP_CREATE_PRODUCT)
        new_name = (new_name or "").strip()
        if not new_name:
            raise ValidationError("Category name is required.")
        category = self.repo.get(category_id)
        if category is None:
            raise ValidationError("Category not found.")
        clash = self.repo.get_by_name_ci(new_name)
        if clash is not None and clash.id != category.id:
            raise ValidationError(f"Category '{new_name}' already exists.")
        category.name = new_name
        self.session.flush()
        self._sync().enqueue_update("category", category.id, {
            "sync_uuid": category.sync_uuid, "name": category.name,
            "version": category.version,
        })
        return category

    def list(self) -> list[Category]:
        return self.repo.list_all()
