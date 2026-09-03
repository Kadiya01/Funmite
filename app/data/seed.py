"""Seed data: the initial ADMIN and CASHIER accounts.

Development-only default passwords are used only when no override is supplied.
They are clearly marked and must be changed before production use. The shop's
real login flow lands in Phase 02.
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.data.models import ROLE_ADMIN, ROLE_CASHIER, User
from app.security.passwords import DEFAULT_ITERATIONS, hash_password

logger = logging.getLogger(__name__)

DEV_ADMIN_USERNAME = "admin"
DEV_CASHIER_USERNAME = "cashier"
DEV_ADMIN_PASSWORD = "admin123"
DEV_CASHIER_PASSWORD = "cashier123"


def ensure_seed_users(
    session: Session,
    *,
    admin_username: str | None = None,
    admin_password: str | None = None,
    admin_full_name: str | None = None,
    cashier_username: str | None = None,
    cashier_password: str | None = None,
    cashier_full_name: str | None = None,
    iterations: int = DEFAULT_ITERATIONS,
) -> list[str]:
    """Idempotently create the ADMIN and CASHIER development accounts.

    Returns the list of usernames that were newly created. Existing users are
    left untouched.
    """
    accounts = [
        (
            admin_username or DEV_ADMIN_USERNAME,
            admin_password or DEV_ADMIN_PASSWORD,
            admin_full_name or "Administrator",
            ROLE_ADMIN,
        ),
        (
            cashier_username or DEV_CASHIER_USERNAME,
            cashier_password or DEV_CASHIER_PASSWORD,
            cashier_full_name or "Cashier",
            ROLE_CASHIER,
        ),
    ]

    created: list[str] = []
    for username, password, full_name, role in accounts:
        exists = session.scalar(select(User).where(User.username == username))
        if exists is not None:
            continue
        session.add(
            User(
                username=username,
                password_hash=hash_password(password, iterations=iterations),
                role=role,
                full_name=full_name,
                is_active=True,
            )
        )
        created.append(username)

    if created:
        session.flush()
        logger.warning(
            "Seeded development accounts %s with default passwords. "
            "Change them before production use.",
            created,
        )
    return created
