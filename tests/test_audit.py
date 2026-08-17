"""Audit logging tests."""

from __future__ import annotations

from sqlalchemy import select

from app.data.models import AuditLog, ROLE_ADMIN
from app.domain.services.audit_service import (
    ACTION_LOGIN_FAILED,
    ACTION_LOGIN_SUCCESS,
    ACTION_LOGOUT,
    AuditService,
)
from tests.factories import make_user


def test_record_with_user_stores_id_and_username(session):
    user = make_user(session, username="jamilu", role=ROLE_ADMIN)
    service = AuditService(session)
    entry = service.record(user=user, action=ACTION_LOGIN_SUCCESS)

    assert entry.user_id == user.id
    assert entry.username == "jamilu"
    assert entry.action == ACTION_LOGIN_SUCCESS
    assert entry.created_at is not None


def test_record_without_user_keeps_username_only(session):
    service = AuditService(session)
    entry = service.login_failed("unknown_person")

    assert entry.user_id is None
    assert entry.username == "unknown_person"
    assert entry.action == ACTION_LOGIN_FAILED


def test_login_failed_details_include_reason_not_password(session):
    service = AuditService(session)
    entry = service.login_failed("admin", reason="account disabled")

    assert entry.details is not None
    assert "account disabled" in entry.details
    assert "password" not in entry.details.lower()


def test_details_are_stored_as_json(session):
    from decimal import Decimal

    user = make_user(session, username="jamilu")
    entry = AuditService(session).record(
        user=user,
        action="PRICE_CHANGE",
        details={"old": Decimal("100.50"), "new": "200.00", "note": "调整"},
    )
    assert entry.details == '{"new": "200.00", "note": "调整", "old": "100.50"}'


def test_logout_helper(session):
    user = make_user(session, username="jamilu")
    entry = AuditService(session).logout(user)
    assert entry.action == ACTION_LOGOUT
    assert entry.user_id == user.id


def test_audit_entries_persist_after_commit(session):
    user = make_user(session, username="jamilu")
    AuditService(session).login_success(user)
    session.commit()

    reloaded = session.scalar(select(AuditLog).where(AuditLog.user_id == user.id))
    assert reloaded is not None
    assert reloaded.username == "jamilu"
