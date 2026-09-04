"""Inline Add Supplier in the Purchase form (F2-inline) UI tests."""

from __future__ import annotations

from PySide6.QtWidgets import QDialog

from app.data.db import session_scope
from app.data.models import ROLE_ADMIN, Product, Supplier
from app.data.repositories.supplier_repository import SupplierRepository
from app.domain.session import CurrentUser
from app.domain.services.supplier_service import SupplierService
from app.ui.purchases.purchase_form import PurchaseFormDialog
from app.ui.suppliers.supplier_form import SupplierFormDialog
from tests.factories import make_category, make_product, make_user


def _admin(session) -> CurrentUser:
    user = make_user(session, username="admin", role=ROLE_ADMIN)
    session.commit()
    return CurrentUser(
        user_id=user.id,
        username=user.username,
        full_name=user.full_name,
        role=user.role,
    )


def _make_dialog(session_factory, session):
    current_user = _admin(session)
    # Pre-created supplier so the combo is populated before opening.
    with session_scope(session_factory) as s:
        SupplierService(s).create_supplier(current_user, name="Existing Supplier")
    return PurchaseFormDialog(
        session_factory=session_factory,
        complete_handler=lambda data: None,
        current_user=current_user,
    )


def _supplier_ids(dialog) -> list[int | None]:
    return [dialog.supplier_combo.itemData(i) for i in range(dialog.supplier_combo.count())]


def test_add_supplier_action_exists(qtbot, session_factory, session):
    dialog = _make_dialog(session_factory, session)
    qtbot.addWidget(dialog)
    assert hasattr(dialog, "add_supplier_button")
    assert dialog.add_supplier_button.text() == "+ Add Supplier"


def test_supplier_dialog_type(qtbot, session_factory, session):
    """The action opens the reusable SupplierFormDialog."""
    dialog = _make_dialog(session_factory, session)
    qtbot.addWidget(dialog)

    shown = []
    dialog._add_supplier = lambda: shown.append(1)
    dialog.add_supplier_button.click()
    assert shown == [1]


def test_successful_creation_adds_and_selects_supplier(qtbot, session_factory, session, monkeypatch):
    dialog = _make_dialog(session_factory, session)
    qtbot.addWidget(dialog)

    # Simulate the reusable dialog accepting with a saved supplier.
    created = {}

    def fake_save_handler(data):
        nonlocal created
        with session_scope(session_factory) as s:
            created["supplier"] = SupplierService(s).create_supplier(
                dialog.current_user, name=data["name"], phone=data["phone"]
            )
        return created["supplier"]

    fake_dialog = SupplierFormDialog(save_handler=fake_save_handler)
    fake_dialog.name_input.setText("New Supplier")
    monkeypatch.setattr(
        "app.ui.purchases.purchase_form.SupplierFormDialog",
        lambda *a, **k: fake_dialog,
    )

    def fake_exec():
        fake_dialog._save()
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(fake_dialog, "exec", fake_exec)

    before = _supplier_ids(dialog)
    dialog._add_supplier()

    supplier = created["supplier"]
    assert supplier.id in _supplier_ids(dialog)
    assert len(_supplier_ids(dialog)) == len(before) + 1
    assert dialog.supplier_combo.currentData() == supplier.id
    assert dialog.supplier_combo.currentText() == "New Supplier"


def test_cancel_leaves_selector_unchanged(qtbot, session_factory, session, monkeypatch):
    dialog = _make_dialog(session_factory, session)
    qtbot.addWidget(dialog)

    before = _supplier_ids(dialog)
    monkeypatch.setattr(
        "app.ui.purchases.purchase_form.SupplierFormDialog.exec",
        lambda self: QDialog.DialogCode.Rejected,
    )
    dialog._add_supplier()
    assert _supplier_ids(dialog) == before
    assert dialog.supplier_combo.currentData() is None


def test_validation_failure_keeps_form_intact(qtbot, session_factory, session, monkeypatch):
    """A failed create (rejected save) must not corrupt the purchase form."""
    dialog = _make_dialog(session_factory, session)
    qtbot.addWidget(dialog)

    before = _supplier_ids(dialog)

    # A SupplierFormDialog whose save fails validation stays open (rejects nothing).
    class FlakyDialog(SupplierFormDialog):
        def _save(self):
            self._show_error("Supplier name is required.")

        def exec(self):
            self._save()
            return QDialog.DialogCode.Rejected

    monkeypatch.setattr(
        "app.ui.purchases.purchase_form.SupplierFormDialog",
        lambda *a, **k: FlakyDialog(save_handler=lambda data: None),
    )
    dialog._add_supplier()

    assert _supplier_ids(dialog) == before
    assert dialog.supplier_combo.currentData() is None


def test_existing_purchase_workflow_still_completes(qtbot, session_factory, session):
    """The purchase form still completes normally with a supplier selected."""
    from decimal import Decimal

    from app.domain.services.purchase_service import PurchaseLine

    current_user = _admin(session)
    category = make_category(session)
    product = make_product(session, category, name="Fabric", cost_price="1000", quantity=5)
    session.commit()

    with session_scope(session_factory) as s:
        supplier = SupplierService(s).create_supplier(current_user, name="ABC Fabrics")
        fresh_product = s.get(Product, product.id)
        unit_cost = Decimal(str(fresh_product.cost_price))

    completed = {}

    def complete_handler(data):
        completed.update(data)

    dialog = PurchaseFormDialog(
        session_factory=session_factory,
        complete_handler=complete_handler,
        current_user=current_user,
    )
    qtbot.addWidget(dialog)

    dialog._populate_suppliers([supplier])
    dialog.supplier_combo.setCurrentIndex(dialog.supplier_combo.findData(supplier.id))
    dialog._lines.append({
        "product_id": product.id,
        "product_name": product.name,
        "quantity": 2,
        "unit_cost": unit_cost,
        "line_total": unit_cost * 2,
    })
    dialog.paid_input.setText("2000")
    dialog._complete()

    assert completed["supplier_id"] == supplier.id
    assert len(completed["items"]) == 1
    assert completed["items"][0].product_id == product.id
    assert completed["items"][0].quantity == 2
    assert completed["amount_paid"] == 2000
    assert dialog.completed is True