"""Settings receipt-printer selector and Test Print (Phase 12-F5 hardening).

Covers the editable printer dropdown populated from the Windows spooler, the
Settings-UI / environment precedence, the Save Printer round-trip into
``PrinterConfigStore``, and the Test Print button routing a sample receipt to
the selected printer without completing a sale. ``win32print`` is faked so the
test never touches the real spooler.
"""

from __future__ import annotations

import sys
from dataclasses import replace

from app.domain.session import CurrentUser
from app.printing.printer import (
    PrinterConfigStore,
    PrinterUnavailableError,
)
from app.ui.settings import settings_page as sp


class _FakeWin32Print:
    """Minimal stand-in for the ``win32print`` module enumeration API."""

    PRINTER_ENUM_LOCAL = 0x00000002
    PRINTER_ENUM_CONNECTIONS = 0x00000004

    def __init__(self, names: list[str]) -> None:
        self._names = list(names)

    def EnumPrinters(self, flags):
        return [("printer", None, name, None) for name in self._names]


class _FakeMessageBox:
    """Records ``QMessageBox`` calls instead of showing dialogs."""

    calls: list[tuple] = []

    @classmethod
    def information(cls, *args):
        cls.calls.append(("information",) + args[1:])

    @classmethod
    def warning(cls, *args):
        cls.calls.append(("warning",) + args[1:])


def _build_page(qtbot, settings, monkeypatch, installed, *, env_name="") -> sp.SettingsPage:
    """Build a SettingsPage with the heavy refresh and spooler faked."""
    settings = replace(settings, printer_name=env_name) if env_name else settings
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(sp.SettingsPage, "refresh", lambda self: None)
    monkeypatch.setattr(sp, "load_settings", lambda: settings)
    monkeypatch.setitem(sys.modules, "win32print", _FakeWin32Print(installed))
    current = CurrentUser(
        user_id=1, username="admin", full_name="Test Admin", role="admin"
    )
    page = sp.SettingsPage(session_factory=lambda: None, current_user=current)
    qtbot.addWidget(page)
    return page


def _combo_items(page: sp.SettingsPage) -> list[str]:
    return [
        page.printer_name_input.itemText(i)
        for i in range(page.printer_name_input.count())
    ]


def _store(settings) -> PrinterConfigStore:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    return PrinterConfigStore(settings.data_dir)


# --- selector population and precedence ------------------------------------ #


def test_selector_lists_installed_printer_names(qtbot, settings, monkeypatch):
    page = _build_page(
        qtbot, settings, monkeypatch, ["XP-80C", "OneNote (Desktop)"]
    )
    items = _combo_items(page)
    assert "XP-80C" in items
    assert "OneNote (Desktop)" in items
    assert page.printer_name_input.currentText() == ""


def test_selector_prefers_saved_settings_name(qtbot, settings, monkeypatch):
    _store(settings).save("XP-80C")
    page = _build_page(
        qtbot, settings, monkeypatch, ["XP-80C", "Microsoft Print to PDF"]
    )
    assert page.printer_name_input.currentText() == "XP-80C"


def test_selector_falls_back_to_environment_name(qtbot, settings, monkeypatch):
    page = _build_page(qtbot, settings, monkeypatch, ["XP-80C"], env_name="XP-80C")
    assert page.printer_name_input.currentText() == "XP-80C"
    assert page.printer_hint_label.text() != ""


def test_selector_empty_when_nothing_configured(qtbot, settings, monkeypatch):
    page = _build_page(qtbot, settings, monkeypatch, [])
    assert page.printer_name_input.currentText() == ""


# --- save / clear ---------------------------------------------------------- #


def test_save_printer_persists_to_config_store(qtbot, settings, monkeypatch):
    monkeypatch.setattr(sp, "QMessageBox", _FakeMessageBox)
    _FakeMessageBox.calls.clear()
    page = _build_page(qtbot, settings, monkeypatch, ["XP-80C"])
    page.printer_name_input.setCurrentText("XP-80C")

    page._on_save_printer()

    assert _store(settings).load() == "XP-80C"
    assert _FakeMessageBox.calls[0][1] == "Printer Saved"


def test_clear_printer_empties_config_store(qtbot, settings, monkeypatch):
    _store(settings).save("XP-80C")
    monkeypatch.setattr(sp, "QMessageBox", _FakeMessageBox)
    _FakeMessageBox.calls.clear()
    page = _build_page(qtbot, settings, monkeypatch, ["XP-80C"])

    page._on_clear_printer()

    assert _store(settings).load() == ""
    assert page.printer_name_input.currentText() == ""
    assert _FakeMessageBox.calls[0][1] == "Printer Cleared"


# --- test print ------------------------------------------------------------ #


def test_test_print_routes_sample_receipt_to_selected_printer(
    qtbot, settings, monkeypatch
):
    sent_to: list[str] = []

    class FakePrinter:
        def __init__(self, name, *, renderer=None):
            sent_to.append(name)

        def print_receipt(self, receipt):
            self.receipt = receipt

    monkeypatch.setattr(sp, "WindowsPrinter", FakePrinter)
    monkeypatch.setattr(sp, "QMessageBox", _FakeMessageBox)
    _FakeMessageBox.calls.clear()
    page = _build_page(qtbot, settings, monkeypatch, ["XP-80C"])
    page.printer_name_input.setCurrentText("XP-80C")

    page._on_test_print()

    assert sent_to == ["XP-80C"]
    assert _FakeMessageBox.calls[0][:2] == ("information", "Test Print Sent")


def test_test_print_without_printer_warns_and_prints_nothing(
    qtbot, settings, monkeypatch
):
    sent_to: list[str] = []

    class FakePrinter:
        def __init__(self, name, *, renderer=None):
            sent_to.append(name)

        def print_receipt(self, receipt):
            self.receipt = receipt

    monkeypatch.setattr(sp, "WindowsPrinter", FakePrinter)
    monkeypatch.setattr(sp, "QMessageBox", _FakeMessageBox)
    _FakeMessageBox.calls.clear()
    page = _build_page(qtbot, settings, monkeypatch, [])

    page._on_test_print()

    assert sent_to == []
    assert _FakeMessageBox.calls[0][0] == "warning"


def test_test_print_surfaces_printer_unavailable(qtbot, settings, monkeypatch):
    class FailingPrinter:
        def __init__(self, name, *, renderer=None):
            pass

        def print_receipt(self, receipt):
            raise PrinterUnavailableError("spooler is gone")

    monkeypatch.setattr(sp, "WindowsPrinter", FailingPrinter)
    monkeypatch.setattr(sp, "QMessageBox", _FakeMessageBox)
    _FakeMessageBox.calls.clear()
    page = _build_page(qtbot, settings, monkeypatch, ["XP-80C"])
    page.printer_name_input.setCurrentText("XP-80C")

    page._on_test_print()

    assert any(call[0] == "warning" for call in _FakeMessageBox.calls)
    assert "spooler is gone" in str(_FakeMessageBox.calls)