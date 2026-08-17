"""Authentication and password-change service.

All password verification goes through ``app.security.passwords``; plaintext
passwords are never stored, logged or audited. Authorization is enforced by
``app.domain.permissions``, not by this service.

Note on commits: ``authenticate`` and ``logout`` manage their own commit because
a failed login must still be audited even though it raises (otherwise the
transaction would roll back the audit row). ``change_password`` leaves the
commit to the caller so it can stay atomic inside a larger unit of work.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.data.models import User
from app.data.repositories.user_repository import UserRepository
from app.domain.errors import AuthenticationError
from app.domain.services.audit_service import AuditService
from app.security.passwords import DEFAULT_ITERATIONS, hash_password, verify_password

GENERIC_LOGIN_ERROR = "Invalid username or password."


class AuthService:
    """Use-case service for local credential login and password changes."""

    def __init__(
        self,
        session: Session,
        *,
        iterations: int = DEFAULT_ITERATIONS,
        audit: AuditService | None = None,
    ) -> None:
        self.session = session
        self.iterations = iterations
        self.audit = audit or AuditService(session)

    def authenticate(self, username: str, password: str) -> User:
        """Return the active ``User`` for valid credentials.

        Fails safely for unknown users, wrong passwords and disabled accounts,
        with the same generic message so no information is leaked. The outcome
        is always recorded in the audit log (and committed) before returning or
        raising.
        """
        user = UserRepository(self.session).get_by_username(username)

        if user is None or not verify_password(password, user.password_hash):
            self.audit.login_failed(username or "")
            self.session.commit()
            raise AuthenticationError(GENERIC_LOGIN_ERROR)

        if not user.is_active:
            self.audit.login_failed(username, reason="account disabled")
            self.session.commit()
            raise AuthenticationError(GENERIC_LOGIN_ERROR)

        self.audit.login_success(user)
        self.session.commit()
        return user

    def logout(self, user: User) -> None:
        """Record a logout in the audit log."""
        self.audit.logout(user)
        self.session.commit()

    def change_password(self, user: User, old_password: str, new_password: str) -> None:
        """Replace ``user``'s password after verifying the current one.

        The caller owns the transaction (use ``session_scope``/``transaction``)
        so the change and its audit entry commit atomically.
        """
        if not verify_password(old_password, user.password_hash):
            self.audit.password_change_failed(user)
            raise AuthenticationError("Current password is incorrect.")

        user.password_hash = hash_password(new_password, iterations=self.iterations)
        self.audit.password_changed(user)
