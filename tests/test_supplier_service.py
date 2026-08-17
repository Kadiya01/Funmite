"""Supplier service tests (Phase 07)."""

from __future__ import annotations

import pytest

from app.data.db import session_scope
from app.data.models import Supplier
from app.domain.errors import AuthorizationError, NotFoundError, ValidationError
from app.domain.services.supplier_service import SupplierService
from tests.factories import make_user


# ── helpers ──────────────────────────────────────────────────────────────── #

def _svc(session):
    return SupplierService(session)


# ── authorization ────────────────────────────────────────────────────────── #

class TestAuthorization:
    def test_admin_can_list(self, session, session_factory):
        admin = make_user(session)
        session.commit()
        with session_factory() as s:
            assert _svc(s).list_suppliers(admin) == []

    def test_cashier_cannot_list(self, session, session_factory):
        cashier = make_user(session, role="CASHIER")
        session.commit()
        with session_factory() as s:
            with pytest.raises(AuthorizationError):
                _svc(s).list_suppliers(cashier)

    def test_admin_can_create(self, session, session_factory):
        admin = make_user(session)
        session.commit()
        with session_factory() as s:
            supplier = _svc(s).create_supplier(admin, name="Test Supplier")
            assert supplier.id is not None
            assert supplier.name == "Test Supplier"

    def test_cashier_cannot_create(self, session, session_factory):
        cashier = make_user(session, role="CASHIER")
        session.commit()
        with session_factory() as s:
            with pytest.raises(AuthorizationError):
                _svc(s).create_supplier(cashier, name="Test")

    def test_unauthenticated_cannot_create(self, session, session_factory):
        with session_factory() as s:
            with pytest.raises(AuthorizationError):
                _svc(s).create_supplier(None, name="Test")


# ── create supplier ──────────────────────────────────────────────────────── #

class TestCreateSupplier:
    def test_create_with_all_fields(self, session, session_factory):
        admin = make_user(session)
        session.commit()
        with session_factory() as s:
            supplier = _svc(s).create_supplier(
                admin, name="ABC Fabrics", phone="08031234567", address="Sabo Market",
            )
            assert supplier.name == "ABC Fabrics"
            assert supplier.phone == "08031234567"
            assert supplier.address == "Sabo Market"
            assert supplier.id is not None

    def test_create_minimal(self, session, session_factory):
        admin = make_user(session)
        session.commit()
        with session_factory() as s:
            supplier = _svc(s).create_supplier(admin, name="Minimal")
            assert supplier.name == "Minimal"
            assert supplier.phone is None
            assert supplier.address is None

    def test_empty_name_rejected(self, session, session_factory):
        admin = make_user(session)
        session.commit()
        with session_factory() as s:
            with pytest.raises(ValidationError, match="name"):
                _svc(s).create_supplier(admin, name="")

    def test_whitespace_name_rejected(self, session, session_factory):
        admin = make_user(session)
        session.commit()
        with session_factory() as s:
            with pytest.raises(ValidationError, match="name"):
                _svc(s).create_supplier(admin, name="   ")

    def test_name_is_stripped(self, session, session_factory):
        admin = make_user(session)
        session.commit()
        with session_factory() as s:
            supplier = _svc(s).create_supplier(admin, name="  ABC  ")
            assert supplier.name == "ABC"


# ── update supplier ──────────────────────────────────────────────────────── #

class TestUpdateSupplier:
    def test_update_name(self, session, session_factory):
        admin = make_user(session)
        session.commit()
        with session_factory() as s:
            supplier = _svc(s).create_supplier(admin, name="Old Name")
            updated = _svc(s).update_supplier(admin, supplier.id, name="New Name")
            assert updated.name == "New Name"

    def test_update_not_found(self, session, session_factory):
        admin = make_user(session)
        session.commit()
        with session_factory() as s:
            with pytest.raises(NotFoundError):
                _svc(s).update_supplier(admin, 99999, name="X")

    def test_cannot_clear_name(self, session, session_factory):
        admin = make_user(session)
        session.commit()
        with session_factory() as s:
            supplier = _svc(s).create_supplier(admin, name="Test")
            with pytest.raises(ValidationError, match="name"):
                _svc(s).update_supplier(admin, supplier.id, name="")


# ── list / search ────────────────────────────────────────────────────────── #

class TestListSuppliers:
    def test_list_empty(self, session, session_factory):
        admin = make_user(session)
        session.commit()
        with session_factory() as s:
            assert _svc(s).list_suppliers(admin) == []

    def test_list_returns_created(self, session, session_factory):
        admin = make_user(session)
        session.commit()
        with session_factory() as s:
            _svc(s).create_supplier(admin, name="Alpha")
            _svc(s).create_supplier(admin, name="Beta")
            result = _svc(s).list_suppliers(admin)
            names = [s.name for s in result]
            assert "Alpha" in names
            assert "Beta" in names

    def test_search_by_name(self, session, session_factory):
        admin = make_user(session)
        session.commit()
        with session_factory() as s:
            _svc(s).create_supplier(admin, name="ABC Fabrics")
            _svc(s).create_supplier(admin, name="XYZ Traders")
            result = _svc(s).list_suppliers(admin, search="ABC")
            assert len(result) == 1
            assert result[0].name == "ABC Fabrics"

    def test_search_by_phone(self, session, session_factory):
        admin = make_user(session)
        session.commit()
        with session_factory() as s:
            _svc(s).create_supplier(admin, name="A", phone="08031234567")
            _svc(s).create_supplier(admin, name="B", phone="09087654321")
            result = _svc(s).list_suppliers(admin, search="0803")
            assert len(result) == 1


# ── get supplier ─────────────────────────────────────────────────────────── #

class TestGetSupplier:
    def test_get_existing(self, session, session_factory):
        admin = make_user(session)
        session.commit()
        with session_factory() as s:
            supplier = _svc(s).create_supplier(admin, name="Test")
            got = _svc(s).get_supplier(admin, supplier.id)
            assert got.name == "Test"

    def test_get_not_found(self, session, session_factory):
        admin = make_user(session)
        session.commit()
        with session_factory() as s:
            with pytest.raises(NotFoundError):
                _svc(s).get_supplier(admin, 99999)
