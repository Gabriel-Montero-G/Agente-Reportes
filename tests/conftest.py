"""Shared fixtures. No test in the default suite touches the network."""
from __future__ import annotations

import os

import pytest

from app import config
from app import session as session_mod

# app.server calls get_settings() at import time (fail fast on a missing key).
# pytest imports every test module during collection, before any fixture below
# runs, so the fake credentials must already be in the real environment by the
# time `import app.server` happens.
os.environ.setdefault("OPENROUTER_API_KEY", "test-openrouter-key")
os.environ.setdefault("TAVILY_API_KEY", "test-tavily-key")


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
