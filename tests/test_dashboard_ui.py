"""Dashboard low-stock indicator UI tests (Phase 04)."""

from __future__ import annotations

from app.data.models import ROLE_ADMIN
from app.domain.session import CurrentUser
from app.ui.dashboard import DashboardPage
from tests.factories import make_category, make_product, make_user


def _admin_user(session) -> CurrentUser:
    user = make_user(session, username="admin", role=ROLE_ADMIN)
    session.commit()
    return CurrentUser(
        user_id=user.id,
        username=user.username,
        full_name=user.full_name,
        role=user.role,
    )


def _make_product(session_factory, *, name: str, quantity: int):
    with session_factory() as session:
        product = make_product(session, make_category(session), name=name, quantity=quantity)
        session.commit()
        return product.id


def _build_page(qtbot, session_factory, session):
    current_user = _admin_user(session)
    page = DashboardPage(session_factory, current_user)
    qtbot.addWidget(page)
    return page


def test_dashboard_shows_empty_state(qtbot, session_factory, session):
    page = _build_page(qtbot, session_factory, session)

    assert page.table.rowCount() == 0
    assert page.summary_label.text() == "No products are low on stock."
    assert page.view_stock_button.isEnabled() is False


def test_dashboard_lists_low_stock_products(qtbot, session_factory, session):
    _make_product(session_factory, name="Gown", quantity=2)
    _make_product(session_factory, name="Top", quantity=3)
    _make_product(session_factory, name="Shoes", quantity=9)

    page = _build_page(qtbot, session_factory, session)

    assert page.table.rowCount() == 2
    names = [page.table.item(row, 0).text() for row in range(2)]
    assert "Gown" in names and "Top" in names and "Shoes" not in names
    assert "2 product(s) are low" in page.summary_label.text()
    assert page.view_stock_button.isEnabled() is True


def test_dashboard_refresh_button_reloads(qtbot, session_factory, session):
    page = _build_page(qtbot, session_factory, session)
    assert page.table.rowCount() == 0

    _make_product(session_factory, name="Gown", quantity=1)
    page.refresh_button.click()

    assert page.table.rowCount() == 1
    assert page.table.item(0, 0).text() == "Gown"
    assert page.table.item(0, 3).text() == "LOW"


def test_view_stock_button_emits_signal(qtbot, session_factory, session):
    _make_product(session_factory, name="Gown", quantity=1)
    page = _build_page(qtbot, session_factory, session)

    with qtbot.waitSignal(page.view_stock_requested, timeout=1000):
        page.view_stock_button.click()
