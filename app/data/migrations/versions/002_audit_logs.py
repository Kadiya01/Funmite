"""Adds the ``audit_logs`` table.

Sensitive actions (successful/failed login, logout, password changes, and later
user-management, discount, exchange, stock-adjustment and backup events) are
recorded here. Required by the master specification (``Audit sensitive
actions``) and the technical architecture (``Record sensitive administrative
actions in an audit log``).
"""

from __future__ import annotations

from app.data.models import Base

version = 2
name = "audit_logs"


def upgrade(bind) -> None:
    Base.metadata.tables["audit_logs"].create(bind)


def downgrade(bind) -> None:
    Base.metadata.tables["audit_logs"].drop(bind)
