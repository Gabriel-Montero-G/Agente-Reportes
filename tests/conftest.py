"""Shared fixtures. No test in the default suite touches the network."""
from __future__ import annotations

import pytest

from app import config
from app import session as session_mod


@pytest.fixture(autouse=True)
def fake_env(monkeypatch):
    """Give every test valid fake credentials and a clean session store."""
    monkeypatch.setattr(config, "load_dotenv", lambda *a, **k: None)
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-openrouter-key")
    monkeypatch.setenv("TAVILY_API_KEY", "test-tavily-key")
    monkeypatch.delenv("MODEL_ID", raising=False)
    config.get_settings.cache_clear()
    session_mod.reset_sessions()
    yield
    config.get_settings.cache_clear()
    session_mod.reset_sessions()
