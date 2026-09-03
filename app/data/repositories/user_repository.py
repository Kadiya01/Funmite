"""User repository."""

from __future__ import annotations

from sqlalchemy import select

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
