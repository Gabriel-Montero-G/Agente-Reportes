"""Smoke test against the real APIs. Excluded by default: every run spends quota.

Run with:  .venv\\Scripts\\python.exe -m pytest -m live -v
"""
from __future__ import annotations

import os

import pytest

from app.agent import build_agent
from app.session import get_or_create_session

pytestmark = pytest.mark.live


@pytest.fixture(autouse=True)
def real_env(monkeypatch):
    """Undo conftest's fake credentials — this test needs the real .env."""
    from app import config

    monkeypatch.undo()
    config.get_settings.cache_clear()
    settings = config.load_settings()
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
