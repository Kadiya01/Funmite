"""Authentication service tests.

Covers the Phase 02 acceptance points: valid login, safe failure for wrong
credentials, disabled/unknown accounts, plaintext never stored, and auditing
of every login outcome.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.data.models import ROLE_ADMIN, AuditLog, User
from app.domain.errors import AuthenticationError
from app.domain.services.audit_service import (
    ACTION_LOGIN_FAILED,
    ACTION_LOGIN_SUCCESS,
    ACTION_LOGOUT,
    ACTION_PASSWORD_CHANGE,
    ACTION_PASSWORD_CHANGE_FAILED,
)
from app.domain.services.auth_service import AuthService, GENERIC_LOGIN_ERROR
from app.security.passwords import verify_password
from tests.factories import make_user


def _audit_actions(session) -> list[str]:
    return list(session.scalars(select(AuditLog.action)))


def test_authenticate_returns_active_user(session):
    make_user(session, username="admin", role=ROLE_ADMIN, password="secret123")
    user = AuthService(session, iterations=10_000).authenticate("admin", "secret123")
    assert user.role == ROLE_ADMIN
    assert user.username == "admin"


def test_authenticate_records_login_success(session):
    make_user(session, username="admin", password="secret123")
    AuthService(session, iterations=10_000).authenticate("admin", "secret123")
    assert _audit_actions(session) == [ACTION_LOGIN_SUCCESS]


def test_authenticate_wrong_password_fails_safely(session):
    make_user(session, username="admin", password="secret123")
    with pytest.raises(AuthenticationError) as exc:
        AuthService(session, iterations=10_000).authenticate("admin", "wrongpw")
    assert str(exc.value) == GENERIC_LOGIN_ERROR


def test_authenticate_unknown_user_fails_safely(session):
    with pytest.raises(AuthenticationError) as exc:
        AuthService(session, iterations=10_000).authenticate("ghost", "anything")
    assert str(exc.value) == GENERIC_LOGIN_ERROR


def test_authenticate_inactive_user_is_blocked(session):
    user = make_user(session, username="admin", password="secret123")
    user.is_active = False
    session.flush()
    with pytest.raises(AuthenticationError):
        AuthService(session, iterations=10_000).authenticate("admin", "secret123")


def test_authenticate_username_is_case_sensitive(session):
    make_user(session, username="admin", password="secret123")
    with pytest.raises(AuthenticationError):
        AuthService(session, iterations=10_000).authenticate("Admin", "secret123")


def test_passwords_are_never_stored_in_plaintext(session):
    make_user(session, username="admin", password="secret123")
    row = session.scalar(select(User).where(User.username == "admin"))
    assert row.password_hash != "secret123"
    assert "secret123" not in row.password_hash
    assert row.password_hash.startswith("pbkdf2_sha256$")


def test_failed_login_audit_row_persists_after_exception(session_factory):
    with session_factory() as session:
        make_user(session, username="admin", password="secret123")
        with pytest.raises(AuthenticationError):
            AuthService(session, iterations=10_000).authenticate("admin", "wrong")

    with session_factory() as check:
        entry = check.scalar(
            select(AuditLog).where(AuditLog.action == ACTION_LOGIN_FAILED)
        )
        assert entry is not None
        assert entry.username == "admin"
        assert entry.user_id is None
        assert "wrong" not in (entry.details or "")


def test_logout_records_audit(session):
    user = make_user(session, username="admin")
    AuthService(session, iterations=10_000).logout(user)
    entry = session.scalar(select(AuditLog).where(AuditLog.action == ACTION_LOGOUT))
    assert entry is not None
    assert entry.user_id == user.id
    assert entry.username == "admin"


def test_change_password_works_and_is_audited(session):
    make_user(session, username="admin", password="oldpw")
    user = session.scalar(select(User).where(User.username == "admin"))
    AuthService(session, iterations=10_000).change_password(user, "oldpw", "newpw")
    session.commit()

    reloaded = session.scalar(select(User).where(User.username == "admin"))
    assert verify_password("newpw", reloaded.password_hash) is True
    assert verify_password("oldpw", reloaded.password_hash) is False

    assert ACTION_PASSWORD_CHANGE in _audit_actions(session)


def test_change_password_wrong_current_fails(session):
    user = make_user(session, username="admin", password="oldpw")
    with pytest.raises(AuthenticationError):
        AuthService(session, iterations=10_000).change_password(user, "nope", "newpw")
    assert ACTION_PASSWORD_CHANGE_FAILED in _audit_actions(session)
