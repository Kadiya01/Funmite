"""Current-user / session handling for a single desktop application run.

The POS is a single-user desktop application, so the "session" is the signed-in
user held in memory for the current run. Nothing sensitive is persisted here;
authentication always goes through ``AuthService``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from app.data.models import User
from app.domain.permissions import has_permission


def user_record_id(user) -> int:
    """The primary key of an ORM ``User`` or a ``CurrentUser`` snapshot.

    The UI hands services a ``CurrentUser`` (``user_id``) while repositories and
    audit rows expect the ORM ``User`` primary key (``id``); this helper bridges
    both so services accept either.
    """
    return getattr(user, "user_id", None) or user.id


@dataclass(frozen=True)
class CurrentUser:
    """Immutable snapshot of the signed-in user presented to the UI."""

    user_id: int
    username: str
    full_name: str
    role: str
    is_active: bool = True
    logged_in_at: datetime = field(default_factory=datetime.now)

    @property
    def display_label(self) -> str:
        """Short label for the title bar/status area, e.g. ``Admin: Jamilu``."""
        return f"{self.role.title()}: {self.full_name or self.username}"

    def can(self, capability: str) -> bool:
        """Shorthand for ``has_permission`` on the current user."""
        return has_permission(self, capability)


class AuthSession:
    """Holds the signed-in user for the current application run."""

    def __init__(self) -> None:
        self._user: CurrentUser | None = None

    @property
    def user(self) -> CurrentUser | None:
        return self._user

    @property
    def is_authenticated(self) -> bool:
        return self._user is not None

    def start(self, user: User) -> CurrentUser:
        """Begin a session for an authenticated ORM ``User``."""
        self._user = CurrentUser(
            user_id=user.id,
            username=user.username,
            full_name=user.full_name,
            role=user.role,
            is_active=bool(user.is_active),
        )
        return self._user

    def end(self) -> CurrentUser | None:
        """End the session and return the user who was signed in (if any)."""
        previous = self._user
        self._user = None
        return previous
