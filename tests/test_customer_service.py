"""Customer service tests (Phase 03).

Covers the acceptance point: a customer record can be registered (with an
auto-generated code) and is available for association with a sale. Customer
record management defaults to Admin-only (see OPEN_DECISIONS.md).
"""

from __future__ import annotations

import pytest

from app.data.models import ROLE_ADMIN, ROLE_CASHIER
from app.domain.errors import AuthorizationError, NotFoundError, ValidationError
from app.domain.services.customer_service import CUSTOMER_CODE_PREFIX, CustomerService
from tests.factories import make_customer, make_user


def test_create_generates_customer_code(session):
    admin = make_user(session, role=ROLE_ADMIN)
    customer = CustomerService(session).create(
        admin, name="Amina Yusuf", phone="0803 123 4567", address="No. 79 NAK Plaza"
    )
    session.flush()
    assert customer.customer_code == f"{CUSTOMER_CODE_PREFIX}-00001"
    assert customer.name == "Amina Yusuf"
    assert customer.phone == "0803 123 4567"
    assert customer.address == "No. 79 NAK Plaza"


def test_create_without_phone_allowed(session):
    admin = make_user(session, role=ROLE_ADMIN)
    customer = CustomerService(session).create(admin, name="No Phone Customer")
    session.flush()
    assert customer.phone is None


def test_create_with_explicit_code(session):
    admin = make_user(session, role=ROLE_ADMIN)
    customer = CustomerService(session).create(admin, name="X", customer_code="CUS-VIP")
    session.flush()
    assert customer.customer_code == "CUS-VIP"


def test_create_duplicate_code_rejected(session):
    admin = make_user(session, role=ROLE_ADMIN)
    CustomerService(session).create(admin, name="First", customer_code="CUS-1")
    session.flush()
    with pytest.raises(ValidationError) as exc:
        CustomerService(session).create(admin, name="Second", customer_code="CUS-1")
    assert "already exists" in str(exc.value)


def test_create_requires_name(session):
    admin = make_user(session, role=ROLE_ADMIN)
    with pytest.raises(ValidationError):
        CustomerService(session).create(admin, name="  ")


def test_cashier_cannot_manage_customers(session):
    cashier = make_user(session, role=ROLE_CASHIER)
    with pytest.raises(AuthorizationError):
        CustomerService(session).create(cashier, name="X")


def test_update_customer(session):
    admin = make_user(session, role=ROLE_ADMIN)
    customer = make_customer(session, name="Old")
    session.flush()
    updated = CustomerService(session).update(
        admin, customer.id, name="New", phone="", address="Somewhere"
    )
    assert updated.name == "New"
    assert updated.phone is None
    assert updated.address == "Somewhere"


def test_update_duplicate_code_rejected(session):
    admin = make_user(session, role=ROLE_ADMIN)
    first = make_customer(session, name="First")
    second = make_customer(session, name="Second")
    first.customer_code = "CUS-AAA"
    second.customer_code = "CUS-BBB"
    session.flush()
    with pytest.raises(ValidationError):
        CustomerService(session).update(admin, second.id, customer_code="CUS-AAA")


def test_get_unknown_customer_raises(session):
    admin = make_user(session, role=ROLE_ADMIN)
    with pytest.raises(NotFoundError):
        CustomerService(session).get(999999)


def test_get_by_code_and_search(session):
    admin = make_user(session, role=ROLE_ADMIN)
    customer = CustomerService(session).create(admin, name="Amina Yusuf", phone="08031234567")
    session.flush()

    service = CustomerService(session)
    assert service.get_by_code(customer.customer_code).id == customer.id
    assert [c.id for c in service.search("amina")] == [customer.id]
    assert [c.id for c in service.search("08031234567")] == [customer.id]
    assert [c.id for c in service.search("nobody")] == []


def test_list_is_ordered_by_name(session):
    admin = make_user(session, role=ROLE_ADMIN)
    CustomerService(session).create(admin, name="Zainab")
    CustomerService(session).create(admin, name="Ali")
    session.flush()
    names = [customer.name for customer in CustomerService(session).list()]
    assert names == ["Ali", "Zainab"]


# --- create_for_sale (Phase 05) -------------------------------------------- #


def test_cashier_can_register_minimal_customer_for_sale(session):
    cashier = make_user(session, role=ROLE_CASHIER)
    customer = CustomerService(session).create_for_sale(cashier, name="Walk-in Buyer")
    session.flush()
    assert customer.name == "Walk-in Buyer"
    assert customer.phone is None
    assert customer.customer_code == f"{CUSTOMER_CODE_PREFIX}-00001"


def test_create_for_sale_accepts_phone(session):
    cashier = make_user(session, role=ROLE_CASHIER)
    customer = CustomerService(session).create_for_sale(cashier, name="Amina", phone="0803 000 0000")
    session.flush()
    assert customer.phone == "0803 000 0000"


def test_create_for_sale_requires_name(session):
    cashier = make_user(session, role=ROLE_CASHIER)
    with pytest.raises(ValidationError):
        CustomerService(session).create_for_sale(cashier, name="   ")


def test_create_for_sale_requires_authentication(session):
    with pytest.raises(AuthorizationError):
        CustomerService(session).create_for_sale(None, name="Ghost")
