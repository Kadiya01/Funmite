"""Configuration loading tests."""

from __future__ import annotations

from app.config import PROJECT_ROOT, Settings, load_settings


def test_load_settings_defaults(tmp_path):
    settings = load_settings()
    assert settings.project_root == PROJECT_ROOT
    assert settings.log_level == "INFO"
    assert settings.api_host == "127.0.0.1"
    assert settings.api_port == 8000
    assert settings.data_dir.is_absolute()
    assert settings.backup_dir.is_absolute()


def test_load_settings_env_overrides(tmp_path, monkeypatch):
    monkeypatch.setenv("FUNMITE_DATA_DIR", str(tmp_path / "custom_data"))
    monkeypatch.setenv("FUNMITE_LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("FUNMITE_API_PORT", "9001")
    settings = load_settings()
    assert settings.data_dir == tmp_path / "custom_data"
    assert settings.log_level == "DEBUG"
    assert settings.api_port == 9001


def test_relative_env_paths_resolve_to_project_root(tmp_path, monkeypatch):
    monkeypatch.setenv("FUNMITE_DATA_DIR", "relative/data")
    settings = load_settings()
    assert settings.data_dir == PROJECT_ROOT / "relative" / "data"


def test_ensure_directories_creates_folders(settings):
    settings.ensure_directories()
    assert settings.data_dir.is_dir()
    assert settings.log_dir.is_dir()
    assert settings.backup_dir.is_dir()


def test_settings_are_frozen(settings):
    assert isinstance(settings, Settings)
    assert settings.data_dir.is_absolute()
