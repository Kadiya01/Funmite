"""Phase 6 regression: operations hygiene (findings #7 and #8).

#7 same-disk backups: the Settings page reports the active backup folder and
   steers admins to ``FUNMITE_BACKUP_DIR`` on an external/network drive; the
   same-volume helper is unit-tested directly.
#8 doc/count drift: living deployment docs must not hard-code stale test
   counts — they point at ``REMEDIATION_MATRIX.md`` (the canonical per-phase
   record). Also pins the removal of an unused import.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from app.domain.session import CurrentUser
from app.ui.settings import settings_page as sp

REPO_ROOT = Path(__file__).resolve().parents[1]


class _FakeWin32Print:
    """Empty stand-in for the Windows spooler enumeration API."""

    PRINTER_ENUM_LOCAL = 0x00000002
    PRINTER_ENUM_CONNECTIONS = 0x00000004

    def __init__(self, names: list[str]) -> None:
        self._names = list(names)

    def EnumPrinters(self, flags):
        return [("printer", None, name, None) for name in self._names]


def _build_page(qtbot, settings, monkeypatch) -> sp.SettingsPage:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.backup_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(sp.SettingsPage, "refresh", lambda self: None)
    monkeypatch.setattr(sp, "load_settings", lambda: settings)
    monkeypatch.setitem(sys.modules, "win32print", _FakeWin32Print([]))
    current = CurrentUser(
        user_id=1, username="admin", full_name="Test Admin", role="admin"
    )
    return sp.SettingsPage(session_factory=lambda: None, current_user=current)


def _repo_file(rel: str) -> str:
    return (REPO_ROOT / rel).read_text(encoding="utf-8")


# --- Finding #7: same-disk backups -------------------------------------- #


def test_same_volume_helper():
    assert sp._same_volume(Path("C:/data"), Path("C:/backups")) is True
    if os.name == "nt":
        assert sp._same_volume(Path("C:/data"), Path("D:/backups")) is False


@pytest.mark.parametrize("separate", [False, True])
def test_backup_location_hint_reports_drive_relationship(
    qtbot, settings, monkeypatch, separate
):
    monkeypatch.setattr(sp, "_same_volume", lambda a, b: separate is False)
    page = _build_page(qtbot, settings, monkeypatch)
    text = page.backup_location_label.text()
    assert "Backup folder:" in text
    if separate:
        assert "separate drive from the database" in text
    else:
        assert "Same drive as your data" in text
        assert "FUNMITE_BACKUP_DIR" in text


# --- Finding #8: doc/count drift ---------------------------------------- #


def test_expense_form_has_no_unused_format_money_import():
    source = _repo_file("app/ui/expenses/expense_form.py")
    assert "from app.utils.formatting import format_money" not in source


def test_deploy_checklist_has_current_counts_and_backup_guidance():
    text = _repo_file("DEPLOYMENT_CHECKLIST.md")
    assert "838 tests passing" not in text
    assert "REMEDIATION_MATRIX" in text
    assert "FUNMITE_BACKUP_DIR" in text
    assert "external or network drive" in text


def test_project_status_validation_step_not_stale():
    text = _repo_file("PROJECT_STATUS.md")
    assert "expect 657" not in text
    assert "REMEDIATION_MATRIX" in text


def test_deployment_guide_backup_strategy():
    text = _repo_file("docs/DEPLOYMENT_GUIDE.md")
    assert "FUNMITE_BACKUP_DIR" in text
    assert "external or network drive" in text
    assert "same drive" in text