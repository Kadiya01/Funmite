"""Audit logging for sensitive actions.

Sensitive actions (login success/failure, logout, password changes, and later
user management, discount, exchange, stock adjustment, backup/restore, expense
and purchase events) are recorded in the ``audit_logs`` table. Entries are
append-only in normal use: services add rows, they never edit or delete them.

A failed login may reference a username that does not exist, so ``user_id`` is
nullable and the username is always stored alongside it. Passwords are never
written to the audit log.
"""

from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.data.models import AuditLog, User

ACTION_LOGIN_SUCCESS = "LOGIN_SUCCESS"
ACTION_LOGIN_FAILED = "LOGIN_FAILED"
ACTION_LOGOUT = "LOGOUT"
ACTION_PASSWORD_CHANGE = "PASSWORD_CHANGE"
ACTION_PASSWORD_CHANGE_FAILED = "PASSWORD_CHANGE_FAILED"
ACTION_BACKUP = "BACKUP"
ACTION_RESTORE = "RESTORE"


def _to_json(details: Any) -> str:
    def default(value: Any) -> str:
        if isinstance(value, (Decimal, datetime, date)):
            return str(value)
        return str(value)

    return json.dumps(details, ensure_ascii=False, default=default, sort_keys=True)


class AuditService:
    """Writes audit entries for a single session."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def record(
        self,
        *,
        user: User | None = None,
        user_id: int | None = None,
        username: str | None = None,
        action: str,
        details: dict[str, Any] | None = None,
    ) -> AuditLog:
        """Append an audit entry.

        Pass either an ORM ``user`` (which supplies both the id and username)
        or explicit ``user_id``/``username`` values (e.g. for a failed login
        whose username does not exist yet).
        """
        if user is not None:
            user_id = user.id
            username = user.username
        entry = AuditLog(
            user_id=user_id,
            username=username,
            action=action,
            details=_to_json(details) if details is not None else None,
        )
        self.session.add(entry)
        self.session.flush()
        return entry

    def login_success(self, user: User) -> AuditLog:
        return self.record(user=user, action=ACTION_LOGIN_SUCCESS)

    def login_failed(self, username: str, *, reason: str | None = None) -> AuditLog:
        details = {"reason": reason} if reason else None
        return self.record(username=username, action=ACTION_LOGIN_FAILED, details=details)

    def logout(self, user: User) -> AuditLog:
        return self.record(user=user, action=ACTION_LOGOUT)

    def password_changed(self, user: User) -> AuditLog:
        return self.record(user=user, action=ACTION_PASSWORD_CHANGE)

    def password_change_failed(self, user: User) -> AuditLog:
        return self.record(user=user, action=ACTION_PASSWORD_CHANGE_FAILED)
