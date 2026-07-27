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


def tool_start(name: str, tool_input: dict, run_id: str = "run-1"):
    return {"event": "on_tool_start", "name": name, "data": {"input": tool_input}, "run_id": run_id}


def tool_end(name: str, output: str, run_id: str = "run-1"):
    return {"event": "on_tool_end", "name": name, "data": {"output": output}, "run_id": run_id}


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
            tool_start("tavily_search", {"query": "IA en España"}, run_id="search-1"),
            tool_end("tavily_search", "5 resultados para «IA en España»\n\n[1] ...", run_id="search-1"),
            tool_start("write_report", {"markdown": REPORT}, run_id="write-1"),
            tool_end("write_report", "Informe actualizado.", run_id="write-1"),
            chunk("Listo. "),
            chunk("Pídeme lo que quieras ampliar."),
        ],
    )

    response = client.post("/api/chat", json={"session_id": "s1", "message": "brief sobre IA"})
    events = parse_sse(response.text)
    types = [event["type"] for event in events]

    assert response.status_code == 200
    assert types == ["step", "step_done", "step", "report", "step_done", "token", "token", "done"]
    step, step_done = events[0], events[1]
    assert step["run_id"] == step_done["run_id"] == "search-1"
    write_step, write_done = events[2], events[4]
    assert write_step["run_id"] == write_done["run_id"] == "write-1"


def test_step_and_step_done_carry_matching_run_ids_for_concurrent_tool_calls(monkeypatch, client):
    """Two concurrent calls to the same tool must be distinguishable by run_id,
    not just by tool name, so the UI can resolve each step_done to the right
    in-flight step even when several calls to the same tool overlap."""
    install(
        monkeypatch,
        [
            tool_start("tavily_search", {"query": "a"}, run_id="run-a"),
            tool_start("tavily_search", {"query": "b"}, run_id="run-b"),
            tool_end("tavily_search", "resultado a", run_id="run-a"),
            tool_end("tavily_search", "resultado b", run_id="run-b"),
        ],
    )
    events = parse_sse(client.post("/api/chat", json={"session_id": "s9", "message": "x"}).text)
    steps = [e for e in events if e["type"] in ("step", "step_done")]
    assert steps[0]["run_id"] == "run-a" and steps[0]["input"] == "a"
    assert steps[1]["run_id"] == "run-b" and steps[1]["input"] == "b"
    assert steps[2]["run_id"] == "run-a" and steps[2]["summary"] == "resultado a"
    assert steps[3]["run_id"] == "run-b" and steps[3]["summary"] == "resultado b"


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


def test_tool_input_falls_back_to_str_for_a_non_dict_input():
    event = {"data": {"input": "raw string input"}}
    assert server._tool_input(event) == "raw string input"


def test_tool_input_truncates_a_non_dict_input_to_input_chars():
    event = {"data": {"input": "x" * (server.INPUT_CHARS + 50)}}
    result = server._tool_input(event)
    assert len(result) == server.INPUT_CHARS


def test_summary_reads_the_content_attribute_of_a_tool_message_output():
    from langchain_core.messages import ToolMessage

    output = ToolMessage(content="5 resultados para «IA»\n\n[1] título", tool_call_id="call-1")
    event = {"data": {"output": output}}
    assert server._summary(event) == "5 resultados para «IA»"
