"""Phase 4 regression: ``python -m app.data.db`` CLI entry point.

The module must never be a silent no-op: with no arguments it prints the real
desktop launch command; ``init`` builds/upgrades the database headlessly;
unknown commands exit non-zero.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _run_cli(args: list[str], tmp_path) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["FUNMITE_DATA_DIR"] = str(tmp_path / "data")
    env["FUNMITE_LOG_DIR"] = str(tmp_path / "logs")
    env["FUNMITE_BACKUP_DIR"] = str(tmp_path / "backups")
    return subprocess.run(
        [sys.executable, "-m", "app.data.db", *args],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )


def test_no_args_points_to_real_entry_point(tmp_path):
    result = _run_cli([], tmp_path)
    assert result.returncode == 0
    assert "NOT the desktop application entry point" in result.stdout
    assert "python -m app.main" in result.stdout


def test_help_exits_zero(tmp_path):
    result = _run_cli(["--help"], tmp_path)
    assert result.returncode == 0
    assert "init" in result.stdout


def test_unknown_command_exits_nonzero(tmp_path):
    result = _run_cli(["frobnicate"], tmp_path)
    assert result.returncode == 2
    assert "Unknown command: frobnicate" in result.stdout


def test_init_builds_database_without_ui(tmp_path):
    result = _run_cli(["init"], tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Funmite database ready:" in result.stdout
    assert "schema version 5" in result.stdout
    assert (tmp_path / "data" / "funmite.db").is_file()