"""Generic data-access helpers shared by all repositories."""

from __future__ import annotations

from typing import Generic, TypeVar

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.data.models import Base

ModelT = TypeVar("ModelT", bound=Base)


class BaseRepository(Generic[ModelT]):
    """Thin read/write helpers over a single model type.

    Repositories sit between services and the ORM session. They never contain
    business rules; validation and authorization live in the service layer.
    """

    model: type[ModelT]

    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, record_id: int) -> ModelT | None:
        return self.session.get(self.model, record_id)

    def get_by(self, **filters) -> ModelT | None:
        statement = select(self.model).filter_by(**filters).limit(1)
        return self.session.scalar(statement)

    def list_all(self, *, order_by=None) -> list[ModelT]:
        statement = select(self.model)
        if order_by is not None:
            statement = statement.order_by(order_by)
        return list(self.session.scalars(statement))

    def count(self) -> int:
        statement = select(func.count()).select_from(self.model)
        return int(self.session.scalar(statement) or 0)

    def add(self, instance: ModelT) -> ModelT:
        self.session.add(instance)
        return instance
