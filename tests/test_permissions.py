"""Permission catalog and service-level authorization tests.

The expectations mirror the permission matrix in Engineering Artifact 02.
Authorization must hold regardless of the UI, so these tests exercise the
catalog functions directly.
"""

from __future__ import annotations

import pytest

from app.data.models import ROLE_ADMIN, ROLE_CASHIER, User
from app.domain.errors import AuthorizationError
from app.domain.permissions import (
    CAP_BACKUP,
    CAP_CANCEL_SALE,
    CAP_CHANGE_PRICE,
    CAP_CREATE_PRODUCT,
    CAP_DISCOUNT,
    CAP_EDIT_PRODUCT,
    CAP_EXCHANGE,
    CAP_LOGIN,
    CAP_MAKE_SALE,
    CAP_MANAGE_CUSTOMERS,
    CAP_MANAGE_EXPENSES,
    CAP_MANAGE_PURCHASES_SUPPLIERS,
    CAP_MANAGE_USERS,
    CAP_PROCESS_PAYMENT,
    CAP_RESTORE,
    CAP_SCAN_BARCODE,
    CAP_STOCK_ADJUSTMENT,
    CAP_STOCK_IN,
    CAP_VIEW_OWN_SALES,
    CAP_VIEW_PROFIT,
    CAP_VIEW_REPORTS,
    has_permission,
    permissions_for_role,
    require_permission,
)

SHARED_CAPABILITIES = {
    CAP_LOGIN,
    CAP_MAKE_SALE,
    CAP_PROCESS_PAYMENT,
    CAP_SCAN_BARCODE,
    CAP_VIEW_OWN_SALES,
}

ADMIN_ONLY_CAPABILITIES = {
    CAP_CREATE_PRODUCT,
    CAP_EDIT_PRODUCT,
    CAP_CHANGE_PRICE,
    CAP_DISCOUNT,
    CAP_CANCEL_SALE,
    CAP_EXCHANGE,
    CAP_STOCK_IN,
    CAP_STOCK_ADJUSTMENT,
    CAP_VIEW_PROFIT,
    CAP_VIEW_REPORTS,
    CAP_MANAGE_USERS,
    CAP_MANAGE_CUSTOMERS,
    CAP_BACKUP,
    CAP_RESTORE,
    CAP_MANAGE_EXPENSES,
    CAP_MANAGE_PURCHASES_SUPPLIERS,
}


def make_user(role: str, *, is_active: bool = True) -> User:
    return User(
        username="u",
        password_hash="x",
        role=role,
        full_name="Test",
        is_active=is_active,
    )


def test_admin_has_all_shared_capabilities():
    for capability in SHARED_CAPABILITIES:
        assert has_permission(make_user(ROLE_ADMIN), capability)


def test_cashier_has_all_shared_capabilities():
    for capability in SHARED_CAPABILITIES:
        assert has_permission(make_user(ROLE_CASHIER), capability)


def test_admin_has_every_admin_only_capability():
    for capability in ADMIN_ONLY_CAPABILITIES:
        assert has_permission(make_user(ROLE_ADMIN), capability)


@pytest.mark.parametrize("capability", sorted(ADMIN_ONLY_CAPABILITIES))
def test_cashier_denied_admin_only_capability(capability):
    assert has_permission(make_user(ROLE_CASHIER), capability) is False


def test_require_permission_passes_for_allowed_role():
    require_permission(make_user(ROLE_ADMIN), CAP_DISCOUNT)
    require_permission(make_user(ROLE_CASHIER), CAP_MAKE_SALE)


@pytest.mark.parametrize("capability", sorted(ADMIN_ONLY_CAPABILITIES))
def test_require_permission_rejects_cashier_for_admin_capability(capability):
    with pytest.raises(AuthorizationError):
        require_permission(make_user(ROLE_CASHIER), capability)


def test_require_permission_rejects_unauthenticated_user():
    with pytest.raises(AuthorizationError):
        require_permission(None, CAP_MAKE_SALE)


def test_require_permission_rejects_inactive_user():
    user = make_user(ROLE_ADMIN, is_active=False)
    assert has_permission(user, CAP_DISCOUNT) is False
    with pytest.raises(AuthorizationError):
        require_permission(user, CAP_DISCOUNT)


def test_unknown_capability_is_denied():
    assert has_permission(make_user(ROLE_ADMIN), "fly_the_shop") is False


def test_unknown_role_is_denied():
    user = make_user("CUSTOMER")
    assert has_permission(user, CAP_MAKE_SALE) is False


def test_permissions_for_role_are_immutable_snapshots():
    admin = permissions_for_role(ROLE_ADMIN)
    cashier = permissions_for_role(ROLE_CASHIER)
    assert admin - cashier == frozenset(ADMIN_ONLY_CAPABILITIES)
    assert cashier <= admin
    assert permissions_for_role("NOPE") == frozenset()
