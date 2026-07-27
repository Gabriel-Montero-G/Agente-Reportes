"""Smoke test against the real APIs. Excluded by default: every run spends quota.

Run with:  .venv\\Scripts\\python.exe -m pytest -m live -v
"""
from __future__ import annotations

import os

import pytest

from app.agent import build_agent
from app.config import ConfigError
from app.session import get_or_create_session

pytestmark = pytest.mark.live


@pytest.fixture(autouse=True)
def real_env(monkeypatch):
    """Undo conftest's fake credentials — this test needs the real .env.

    conftest.py sets fake OPENROUTER_API_KEY/TAVILY_API_KEY at *module import*
    time (before any fixture runs), so `monkeypatch.undo()` only restores
    os.environ to the state it was in right after that fake-key injection —
    the fake keys are still present. `load_dotenv(override=False)` (the
    default) then refuses to overwrite them with the real .env values. So the
    fake keys must be explicitly removed before loading the real settings.
    """
    from app import config

    monkeypatch.undo()
    for name in ("OPENROUTER_API_KEY", "TAVILY_API_KEY"):
        os.environ.pop(name, None)
    config.get_settings.cache_clear()
    try:
        settings = config.load_settings()
    except ConfigError:
        # No real .env and no real env vars at all — same "no real
        # credentials" case as a fake `test-` key, just surfaced differently.
        pytest.skip("No hay claves reales en el entorno.")
    if settings.openrouter_api_key.startswith("test-"):
        pytest.skip("No hay claves reales en el entorno.")


def test_agent_produces_a_cited_brief():
    session = get_or_create_session("live-smoke")
    agent = build_agent(session)

    result = agent.invoke(
        {"input": "Hazme un brief sobre la energía eólica marina en España en 2025."},
        config={"configurable": {"session_id": session.id}},
    )

    words = len(session.report.split())
    assert session.report.startswith("#"), "el informe debe empezar por un título"
    assert 250 <= words <= 750, f"longitud fuera de rango: {words} palabras"
    assert "## Fuentes" in session.report
    assert "http" in session.report
    assert result["output"], "el agente debe responder algo en el chat"
