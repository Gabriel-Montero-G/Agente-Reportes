from __future__ import annotations

from langchain_core.messages import HumanMessage

from app.session import get_or_create_session, get_session, reset_sessions


def test_get_or_create_returns_the_same_object_for_one_id():
    first = get_or_create_session("abc")
    second = get_or_create_session("abc")
    assert first is second
    assert first.id == "abc"


def test_sessions_are_isolated():
    a = get_or_create_session("a")
    b = get_or_create_session("b")
    a.report = "# Informe A"
    assert b.report == ""


def test_new_session_starts_empty():
    session = get_or_create_session("fresh")
    assert session.report == ""
    assert session.history.messages == []


def test_history_is_per_session():
    session = get_or_create_session("hist")
    session.history.add_message(HumanMessage("hola"))
    assert len(get_or_create_session("hist").history.messages) == 1


def test_get_session_returns_none_for_unknown_id():
    assert get_session("does-not-exist") is None


def test_reset_sessions_clears_the_store():
    get_or_create_session("temp")
    reset_sessions()
    assert get_session("temp") is None
