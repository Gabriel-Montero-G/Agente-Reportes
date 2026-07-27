from __future__ import annotations

import pytest

from app.config import DEFAULT_MODEL_ID, ConfigError, get_settings, load_settings


def test_load_settings_reads_env():
    settings = load_settings()
    assert settings.openrouter_api_key == "test-openrouter-key"
    assert settings.tavily_api_key == "test-tavily-key"
    assert settings.model_id == DEFAULT_MODEL_ID


def test_model_id_is_overridable(monkeypatch):
    monkeypatch.setenv("MODEL_ID", "some/other-model")
    assert load_settings().model_id == "some/other-model"


def test_missing_key_raises_with_the_variable_name(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with pytest.raises(ConfigError, match="OPENROUTER_API_KEY"):
        load_settings()


def test_get_settings_is_cached():
    assert get_settings() is get_settings()
