from __future__ import annotations

import pytest

from app.session import get_or_create_session
from app.tools import build_tools, make_write_report, tavily_search


class FakeTavily:
    """Stand-in for langchain_tavily.TavilySearch."""

    def __init__(self, payload=None, error: Exception | None = None) -> None:
        self.payload = payload
        self.error = error
        self.calls: list[dict] = []

    def invoke(self, args: dict) -> dict:
        self.calls.append(args)
        if self.error is not None:
            raise self.error
        return self.payload


@pytest.fixture
def fake_tavily(monkeypatch):
    fake = FakeTavily(
        payload={
            "results": [
                {"title": "Informe IA 2025", "url": "https://a.example", "content": "Contenido A"},
                {"title": "Datos IA", "url": "https://b.example", "content": "Contenido B"},
            ]
        }
    )
    monkeypatch.setattr("app.tools._client", lambda: fake)
    return fake


def test_search_returns_a_countable_first_line(fake_tavily):
    output = tavily_search.invoke({"query": "IA en España"})
    assert output.splitlines()[0].startswith("2 resultados")
    assert fake_tavily.calls == [{"query": "IA en España"}]


def test_search_includes_titles_and_urls(fake_tavily):
    output = tavily_search.invoke({"query": "IA en España"})
    assert "[1] Informe IA 2025" in output
    assert "https://a.example" in output


def test_search_failure_becomes_an_observation(monkeypatch):
    monkeypatch.setattr("app.tools._client", lambda: FakeTavily(error=RuntimeError("timeout")))
    output = tavily_search.invoke({"query": "lo que sea"})
    assert output.startswith("Búsqueda fallida")
    assert "timeout" in output


def test_search_handles_an_empty_result_set(monkeypatch):
    monkeypatch.setattr("app.tools._client", lambda: FakeTavily(payload={"results": []}))
    assert tavily_search.invoke({"query": "x"}).splitlines()[0].startswith("0 resultados")


def test_write_report_writes_to_its_own_session():
    session = get_or_create_session("s1")
    other = get_or_create_session("s2")
    tool = make_write_report(session)

    result = tool.invoke({"markdown": "# Informe\n\nCuerpo."})

    assert session.report == "# Informe\n\nCuerpo."
    assert other.report == ""
    assert result == "Informe actualizado."


def test_write_report_replaces_the_previous_report():
    session = get_or_create_session("s3")
    tool = make_write_report(session)
    tool.invoke({"markdown": "# Primero"})
    tool.invoke({"markdown": "# Segundo"})
    assert session.report == "# Segundo"


def test_build_tools_exposes_both_tools_by_name():
    names = {tool.name for tool in build_tools(get_or_create_session("s4"))}
    assert names == {"tavily_search", "write_report"}
