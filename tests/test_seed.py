"""Seed and password-hashing tests."""

from __future__ import annotations

from sqlalchemy import func, select

from app.data.models import ROLE_ADMIN, ROLE_CASHIER, User
from app.data.seed import ensure_seed_users
from app.security.passwords import hash_password, verify_password


def _count(session, model) -> int:
    return int(session.scalar(select(func.count()).select_from(model)) or 0)


# --- Password hashing -----------------------------------------------------


def test_hash_verify_roundtrip():
    encoded = hash_password("correct horse", iterations=10_000)
    assert encoded != "correct horse"
    assert "correct horse" not in encoded
    assert verify_password("correct horse", encoded) is True
    assert verify_password("wrong", encoded) is False


def test_hashes_are_salted_and_unique():
    first = hash_password("same", iterations=10_000)
    second = hash_password("same", iterations=10_000)
    assert first != second


def test_malformed_hash_returns_false():
    assert verify_password("anything", "not-a-valid-hash") is False
    assert verify_password("anything", "") is False
    assert verify_password("anything", "pbkdf2_sha256$x$badhex$badhex") is False


# --- Seed accounts --------------------------------------------------------


def test_seed_creates_admin_and_cashier(session):
    created = ensure_seed_users(session, iterations=10_000)
    assert set(created) == {"admin", "cashier"}
    assert _count(session, User) == 2

    admin = session.scalar(select(User).where(User.username == "admin"))
    cashier = session.scalar(select(User).where(User.username == "cashier"))
    assert admin is not None and admin.role == ROLE_ADMIN
    assert cashier is not None and cashier.role == ROLE_CASHIER


def test_seeded_passwords_are_hashed_not_plaintext(session):
    ensure_seed_users(session, iterations=10_000)
    for username in ("admin", "cashier"):
        user = session.scalar(select(User).where(User.username == username))
        assert user.password_hash != "admin123"
        assert user.password_hash != "cashier123"
        assert "admin123" not in user.password_hash


def test_seeded_default_passwords_verify(session):
    ensure_seed_users(session, iterations=10_000)
    admin = session.scalar(select(User).where(User.username == "admin"))
    cashier = session.scalar(select(User).where(User.username == "cashier"))
    assert verify_password("admin123", admin.password_hash) is True
    assert verify_password("cashier123", cashier.password_hash) is True
    assert verify_password("wrong-password", admin.password_hash) is False


def test_seed_is_idempotent(session):
    ensure_seed_users(session, iterations=10_000)
    session.commit()
    created = ensure_seed_users(session, iterations=10_000)
    assert created == []
    assert _count(session, User) == 2


def test_seed_accepts_custom_accounts(session):
    ensure_seed_users(
        session,
        admin_username="jamilu",
        admin_password="s3cret",
        iterations=10_000,
    )
    assert _count(session, User) == 2
    user = session.scalar(select(User).where(User.username == "jamilu"))
    assert user is not None
    assert verify_password("s3cret", user.password_hash) is True
