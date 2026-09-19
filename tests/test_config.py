import pytest

from app import config


def test_get_settings_raises_without_api_key(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(RuntimeError):
        config.get_settings()


def test_get_settings_uses_default_model(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.delenv("GEMINI_MODEL", raising=False)
    settings = config.get_settings()
    assert settings.model == "gemini-3.8-flash"


def test_get_settings_uses_custom_model(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("GEMINI_MODEL", "gemini-3.7-flash")
    settings = config.get_settings()
    assert settings.model == "gemini-3.7-flash"


def test_get_settings_returns_data_dir():
    settings = config.get_settings()
    assert settings.data_dir == config.DATA_DIR
