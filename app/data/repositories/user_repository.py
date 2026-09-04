"""User repository."""

from __future__ import annotations

from sqlalchemy import or_, select

from app.data.models import User
from app.data.repositories.base import BaseRepository


class UserRepository(BaseRepository[User]):
    """Data access for authentication accounts."""

    model = User

    def get_by_username(self, username: str) -> User | None:
        return self.get_by(username=username)

    def list_active(self) -> list[User]:
        statement = select(User).where(User.is_active.is_(True)).order_by(User.full_name)
        return list(self.session.scalars(statement))

    def list_all_ordered(self) -> list[User]:
        statement = select(User).order_by(User.is_active, User.full_name)
        return list(self.session.scalars(statement))

    def search(self, query: str, *, limit: int = 200) -> list[User]:
        cleaned = (query or "").strip()
        statement = select(User)
        if cleaned:
            like = f"%{cleaned}%"
            statement = statement.where(
                or_(User.username.ilike(like), User.full_name.ilike(like))
            )
        statement = statement.order_by(User.is_active, User.full_name).limit(limit)
        return list(self.session.scalars(statement))
