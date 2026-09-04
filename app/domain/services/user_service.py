"""User / Cashier account management service (Phase 12, F4).

Admins manage Cashier accounts: create, edit details, soft-deactivate/reactivate,
and reset passwords. The capability ``CAP_MANAGE_USERS`` is Admin-only and is
enforced here in the service layer — never merely by hiding a UI button.

Security guarantees:
- Only an active Admin (``require_permission``) may manage other users.
- Accounts are always created as ``ROLE_CASHIER``; the management UI can never
  mint a second Admin, and neither can this service.
- Admin accounts are read-only: they can never be edited, deactivated,
  reactivated or have their password reset through this service.
- A user cannot deactivate themselves (prevents accidental lock-out).
- Passwords are only ever changed via ``hash_password`` from
  ``app.security.passwords``; plaintext is never stored or logged.

User records are intentionally never synced to the cloud (credentials must not
leave the local PC), so there is no sync enqueue here.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.data.models import ROLE_CASHIER, User
from app.data.repositories.user_repository import UserRepository
from app.domain.errors import NotFoundError, ValidationError
from app.domain.permissions import CAP_MANAGE_USERS, require_permission
from app.domain.services.audit_service import AuditService
from app.domain.session import user_record_id
from app.security.passwords import DEFAULT_ITERATIONS, hash_password

MIN_PASSWORD_LENGTH = 6


class UserService:
    """Use-case service for Admin-managed Cashier accounts."""

    def __init__(
        self,
        session: Session,
        *,
        iterations: int = DEFAULT_ITERATIONS,
        audit: AuditService | None = None,
    ) -> None:
        self.session = session
        self.iterations = iterations
        self.repo = UserRepository(session)
        self.audit = audit or AuditService(session)

    # --- Authorization helpers ------------------------------------------- #

    def _require_admin(self, actor) -> None:
        require_permission(actor, CAP_MANAGE_USERS)

    def _require_cashier_target(self, target: User) -> None:
        """Management actions may only touch Cashier accounts.

        Admin accounts are immutable through this service; the management page
        only ever deals with Cashiers, and this guards against any caller
        attempting to tamper with admin accounts.
        """
        if target.role != ROLE_CASHIER:
            raise ValidationError("Admin accounts cannot be modified here.")

    def _get_target(self, user_id: int) -> User:
        target = self.repo.get(user_id)
        if target is None:
            raise NotFoundError("User not found.")
        return target

    # --- Queries ---------------------------------------------------------- #

    def search(self, actor, query: str = "", *, limit: int = 200) -> list[User]:
        """List/search accounts for an Admin."""
        self._require_admin(actor)
        return self.repo.search(query, limit=limit)

    # --- Commands --------------------------------------------------------- #

    def create(
        self,
        actor,
        *,
        username: str,
        full_name: str,
        password: str,
    ) -> User:
        """Create a new Cashier account (Admin only).

        The role is always ``ROLE_CASHIER`` — this service intentionally cannot
        create another Admin.
        """
        self._require_admin(actor)
        username = (username or "").strip()
        full_name = (full_name or "").strip()
        if not username:
            raise ValidationError("Username is required.")
        if not full_name:
            raise ValidationError("Full name is required.")
        if not password:
            raise ValidationError("Password is required.")
        if len(password) < MIN_PASSWORD_LENGTH:
            raise ValidationError(
                f"Password must be at least {MIN_PASSWORD_LENGTH} characters."
            )
        if self.repo.get_by_username(username) is not None:
            raise ValidationError(f"Username '{username}' already exists.")

        user = User(
            username=username,
            full_name=full_name,
            password_hash=hash_password(password, iterations=self.iterations),
            role=ROLE_CASHIER,
            is_active=True,
        )
        self.repo.add(user)
        self.session.flush()
        self.audit.user_created(self._actor_orm(actor), user)
        return user

    def update(self, actor, user_id: int, *, full_name: str) -> User:
        """Edit a Cashier's details (Admin only). Role cannot be changed."""
        self._require_admin(actor)
        target = self._get_target(user_id)
        self._require_cashier_target(target)

        cleaned = (full_name or "").strip()
        if not cleaned:
            raise ValidationError("Full name is required.")
        target.full_name = cleaned
        self.session.flush()
        self.audit.user_updated(self._actor_orm(actor), target)
        return target

    def deactivate(self, actor, user_id: int) -> User:
        """Soft-deactivate a Cashier (Admin only). Cannot act on self/Admin."""
        self._require_admin(actor)
        target = self._get_target(user_id)
        self._require_cashier_target(target)
        if user_record_id(actor) == target.id:
            raise ValidationError("You cannot deactivate your own account.")
        if target.is_active:
            target.is_active = False
            self.session.flush()
            self.audit.user_deactivated(self._actor_orm(actor), target)
        return target

    def activate(self, actor, user_id: int) -> User:
        """Re-enable a deactivated Cashier (Admin only)."""
        self._require_admin(actor)
        target = self._get_target(user_id)
        self._require_cashier_target(target)
        if not target.is_active:
            target.is_active = True
            self.session.flush()
            self.audit.user_activated(self._actor_orm(actor), target)
        return target

    def reset_password(self, actor, user_id: int, new_password: str) -> User:
        """Reset a Cashier's password (Admin only). Cannot target Admin."""
        self._require_admin(actor)
        target = self._get_target(user_id)
        self._require_cashier_target(target)
        if not new_password:
            raise ValidationError("New password is required.")
        if len(new_password) < MIN_PASSWORD_LENGTH:
            raise ValidationError(
                f"Password must be at least {MIN_PASSWORD_LENGTH} characters."
            )
        target.password_hash = hash_password(new_password, iterations=self.iterations)
        self.session.flush()
        self.audit.password_reset(self._actor_orm(actor), target)
        return target

    def _actor_orm(self, actor):
        """Resolve the audit actor to an ORM ``User`` (or None)."""
        user_id = user_record_id(actor)
        return self.repo.get(user_id)
