from __future__ import annotations

from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage

from app.agent import MAX_ITERATIONS, SYSTEM_PROMPT, build_agent
from app.session import get_or_create_session

REPORT = "# La IA en España\n\nCuerpo del informe [1].\n\n## Fuentes\n1. https://a.example"


class ToolCallingFake(FakeMessagesListChatModel):
    """FakeMessagesListChatModel plus the bind_tools() the agent requires."""

    def bind_tools(self, tools, **kwargs):
        return self


def _fake(*messages: AIMessage) -> ToolCallingFake:
    return ToolCallingFake(responses=list(messages))


def _search_call(query: str, call_id: str = "call_1") -> AIMessage:
    return AIMessage(
        content="",
        tool_calls=[{"name": "tavily_search", "args": {"query": query}, "id": call_id}],
    )


def _write_call(markdown: str, call_id: str = "call_2") -> AIMessage:
    return AIMessage(
        content="",
        tool_calls=[{"name": "write_report", "args": {"markdown": markdown}, "id": call_id}],
    )


def test_agent_searches_then_publishes(monkeypatch):
    monkeypatch.setattr("app.tools._client", lambda: _StubTavily())
    session = get_or_create_session("agent-1")
    agent = build_agent(
        session,
        llm=_fake(
            _search_call("IA en España 2025"),
            _write_call(REPORT),
            AIMessage(content="Listo. Puedes pedirme que amplíe cualquier sección."),
        ),
    )

    result = agent.invoke(
        {"input": "Hazme un brief sobre la IA en España"},
        config={"configurable": {"session_id": session.id}},
    )

    assert session.report == REPORT
    assert result["output"].startswith("Listo")


def test_history_grows_across_turns(monkeypatch):
    monkeypatch.setattr("app.tools._client", lambda: _StubTavily())
    session = get_or_create_session("agent-2")
    agent = build_agent(session, llm=_fake(AIMessage(content="Hecho.")))

    agent.invoke({"input": "primer mensaje"}, config={"configurable": {"session_id": session.id}})

    assert len(session.history.messages) == 2  # human + ai


def test_refinement_replaces_the_whole_report(monkeypatch):
    monkeypatch.setattr("app.tools._client", lambda: _StubTavily())
    session = get_or_create_session("agent-3")
    session.report = "# Viejo\n\nContenido anterior."
    agent = build_agent(
        session,
        llm=_fake(_write_call("# Nuevo\n\nInforme reescrito entero."), AIMessage(content="Actualizado.")),
    )

    agent.invoke({"input": "amplía la sección 2"}, config={"configurable": {"session_id": session.id}})

    assert session.report.startswith("# Nuevo")
    assert "Viejo" not in session.report


def test_system_prompt_states_the_hard_rules():
    assert "write_report" in SYSTEM_PROMPT
    assert "300-600" in SYSTEM_PROMPT
    assert "Fuentes" in SYSTEM_PROMPT


def test_iteration_cap_matches_the_quota_budget():
    assert MAX_ITERATIONS == 6


class _StubTavily:
    def invoke(self, args: dict) -> dict:
        return {"results": [{"title": "T", "url": "https://a.example", "content": "C"}]}
