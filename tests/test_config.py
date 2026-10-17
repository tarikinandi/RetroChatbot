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
    assert settings.model == "gemini-2.5-flash"


def test_get_settings_uses_custom_model(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("GEMINI_MODEL", "gemini-3.7-flash")
    settings = config.get_settings()
    assert settings.model == "gemini-3.7-flash"


def test_get_settings_returns_data_dir():
    settings = config.get_settings()
    assert settings.data_dir == config.DATA_DIR


def test_models_list_default_and_env(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    monkeypatch.delenv("GEMINI_MODEL", raising=False)
    monkeypatch.delenv("GEMINI_MODELS", raising=False)
    assert config.get_models() == list(config.DEFAULT_MODELS)
    monkeypatch.setenv("GEMINI_MODELS", " a , b,,a ")
    assert config.get_models() == ["a", "b"]
    monkeypatch.setenv("GEMINI_MODEL", "z")
    assert config.get_models() == ["z", "a", "b"]
    assert config.get_settings().model == "z"
    monkeypatch.delenv("GEMINI_MODELS")
    assert config.get_models() == ["z", *config.DEFAULT_MODELS]
