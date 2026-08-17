"""Login dialog UI tests (Qt)."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QLineEdit

from app.data.models import ROLE_ADMIN, User
from app.domain.errors import AuthenticationError
from app.ui.login import LoginDialog


def _admin_authenticator():
    admin = User(
        id=1,
        username="jamilu",
        role=ROLE_ADMIN,
        full_name="Jamilu",
        is_active=True,
    )

    def authenticate(username: str, password: str) -> User:
        if username == "jamilu" and password == "shop123":
            return admin
        raise AuthenticationError("Invalid username or password.")

    return authenticate


def test_password_field_is_masked(qtbot):
    dialog = LoginDialog(authenticator=_admin_authenticator())
    qtbot.addWidget(dialog)
    assert dialog.password_input.echoMode() == QLineEdit.EchoMode.Password


def test_successful_login_sets_current_user(qtbot):
    dialog = LoginDialog(authenticator=_admin_authenticator())
    qtbot.addWidget(dialog)

    dialog.username_input.setText("jamilu")
    dialog.password_input.setText("shop123")
    dialog.login_button.click()

    assert dialog.result() == QDialog.DialogCode.Accepted
    assert dialog.current_user is not None
    assert dialog.current_user.username == "jamilu"
    assert dialog.current_user.role == ROLE_ADMIN
    assert dialog.current_user.display_label == "Admin: Jamilu"


def test_wrong_credentials_show_error_and_do_not_accept(qtbot):
    dialog = LoginDialog(authenticator=_admin_authenticator())
    qtbot.addWidget(dialog)

    dialog.username_input.setText("jamilu")
    dialog.password_input.setText("wrong")
    dialog.login_button.click()

    assert dialog.result() != QDialog.DialogCode.Accepted
    assert dialog.current_user is None
    assert dialog.error_label.isHidden() is False
    assert "Invalid username or password." in dialog.error_label.text()


def test_empty_fields_show_error(qtbot):
    dialog = LoginDialog(authenticator=_admin_authenticator())
    qtbot.addWidget(dialog)

    dialog.login_button.click()

    assert dialog.result() != QDialog.DialogCode.Accepted
    assert dialog.error_label.isHidden() is False
    assert "username and password" in dialog.error_label.text()


def test_enter_key_submits_login(qtbot):
    dialog = LoginDialog(authenticator=_admin_authenticator())
    qtbot.addWidget(dialog)

    dialog.username_input.setText("jamilu")
    dialog.password_input.setText("shop123")
    qtbot.keyClick(dialog.password_input, Qt.Key.Key_Return)

    assert dialog.result() == QDialog.DialogCode.Accepted
    assert dialog.current_user is not None


def test_unknown_exception_uses_safe_message(qtbot):
    def authenticate(username: str, password: str) -> User:
        raise RuntimeError("boom")

    dialog = LoginDialog(authenticator=authenticate)
    qtbot.addWidget(dialog)

    dialog.username_input.setText("jamilu")
    dialog.password_input.setText("shop123")
    dialog.login_button.click()

    assert dialog.result() != QDialog.DialogCode.Accepted
    assert dialog.error_label.isHidden() is False
    assert "boom" not in dialog.error_label.text()
