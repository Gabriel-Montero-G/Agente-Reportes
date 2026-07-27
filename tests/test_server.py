from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app import server
from app.session import get_or_create_session

REPORT = "# Informe\n\nCuerpo [1].\n\n## Fuentes\n1. https://a.example"


def parse_sse(body: str) -> list[dict]:
    return [
        json.loads(line[len("data:"):].strip())
        for line in body.splitlines()
        if line.startswith("data:")
    ]


class StubAgent:
    """Replays a scripted astream_events sequence."""

    def __init__(self, events: list[dict], error: Exception | None = None) -> None:
        self.events = events
        self.error = error

    async def astream_events(self, _input, config=None, version=None):
        for event in self.events:
            yield event
        if self.error is not None:
            raise self.error


def chunk(text: str):
    from langchain_core.messages import AIMessageChunk

    return {"event": "on_chat_model_stream", "name": "model", "data": {"chunk": AIMessageChunk(content=text)}}


def tool_start(name: str, tool_input: dict):
    return {"event": "on_tool_start", "name": name, "data": {"input": tool_input}}


def tool_end(name: str, output: str):
    return {"event": "on_tool_end", "name": name, "data": {"output": output}}


def install(monkeypatch, events, error=None, report: str = REPORT):
    def fake_build_agent(session, llm=None):
        session.report = report  # the write_report tool would have done this
        return StubAgent(events, error)

    monkeypatch.setattr(server, "build_agent", fake_build_agent)


@pytest.fixture
def client():
    return TestClient(server.app)


def test_full_happy_path_event_sequence(monkeypatch, client):
    install(
        monkeypatch,
        [
            tool_start("tavily_search", {"query": "IA en España"}),
            tool_end("tavily_search", "5 resultados para «IA en España»\n\n[1] ..."),
            tool_start("write_report", {"markdown": REPORT}),
            tool_end("write_report", "Informe actualizado."),
            chunk("Listo. "),
            chunk("Pídeme lo que quieras ampliar."),
        ],
    )

    response = client.post("/api/chat", json={"session_id": "s1", "message": "brief sobre IA"})
    events = parse_sse(response.text)
    types = [event["type"] for event in events]

    assert response.status_code == 200
    assert types == ["step", "step_done", "step", "report", "step_done", "token", "token", "done"]


def test_step_events_carry_the_query(monkeypatch, client):
    install(monkeypatch, [tool_start("tavily_search", {"query": "IA en España"})])
    step = parse_sse(client.post("/api/chat", json={"session_id": "s2", "message": "x"}).text)[0]
    assert step["tool"] == "tavily_search"
    assert step["input"] == "IA en España"


def test_step_done_summary_is_the_first_line_of_the_observation(monkeypatch, client):
    install(monkeypatch, [tool_end("tavily_search", "5 resultados para «IA»\n\n[1] título")])
    done = parse_sse(client.post("/api/chat", json={"session_id": "s3", "message": "x"}).text)[0]
    assert done["summary"] == "5 resultados para «IA»"


def test_report_event_carries_sanitised_html_and_raw_markdown(monkeypatch, client):
    install(monkeypatch, [tool_end("write_report", "Informe actualizado.")], report="# T\n\n<script>x</script>")
    report = parse_sse(client.post("/api/chat", json={"session_id": "s4", "message": "x"}).text)[0]
    assert report["type"] == "report"
    assert "<h1>T</h1>" in report["html"]
    assert "<script>" not in report["html"]
    assert report["markdown"] == "# T\n\n<script>x</script>"


def test_agent_failure_becomes_an_error_event_then_done(monkeypatch, client):
    class Boom(Exception):
        status_code = 429

    install(monkeypatch, [], error=Boom("Rate limit exceeded: free-models-per-day"))
    types = [event["type"] for event in parse_sse(client.post("/api/chat", json={"session_id": "s5", "message": "x"}).text)]
    assert types == ["error", "done"]


def test_daily_quota_message_is_explicit(monkeypatch, client):
    from app.errors import DAILY_QUOTA_MESSAGE

    class Boom(Exception):
        status_code = 429

    install(monkeypatch, [], error=Boom("Rate limit exceeded: free-models-per-day"))
    error = parse_sse(client.post("/api/chat", json={"session_id": "s6", "message": "x"}).text)[0]
    assert error["message"] == DAILY_QUOTA_MESSAGE


def test_finishing_without_a_report_explains_how_to_recover(monkeypatch, client):
    from app.errors import NO_REPORT_MESSAGE

    install(monkeypatch, [chunk("He buscado pero no he terminado.")], report="")
    events = parse_sse(client.post("/api/chat", json={"session_id": "s7", "message": "x"}).text)
    assert events[-2]["message"] == NO_REPORT_MESSAGE


def test_report_endpoint_returns_raw_markdown():
    get_or_create_session("s8").report = REPORT
    response = TestClient(server.app).get("/api/report/s8")
    assert response.status_code == 200
    assert response.text == REPORT


def test_report_endpoint_404s_for_an_unknown_session(client):
    assert client.get("/api/report/nope").status_code == 404


def test_root_serves_the_app_shell(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
