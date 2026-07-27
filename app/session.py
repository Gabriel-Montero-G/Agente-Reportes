"""In-memory session store. Nothing survives a process restart, by design."""
from __future__ import annotations

from dataclasses import dataclass, field

from langchain_core.chat_history import InMemoryChatMessageHistory


@dataclass
class Session:
    """One browser tab's conversation and its current report."""

    id: str
    history: InMemoryChatMessageHistory = field(default_factory=InMemoryChatMessageHistory)
    report: str = ""


_SESSIONS: dict[str, Session] = {}


def get_or_create_session(session_id: str) -> Session:
    """Return the session for `session_id`, creating it on first use."""
    session = _SESSIONS.get(session_id)
    if session is None:
        session = Session(id=session_id)
        _SESSIONS[session_id] = session
    return session


def get_session(session_id: str) -> Session | None:
    """Return the session for `session_id`, or None if it does not exist."""
    return _SESSIONS.get(session_id)


def reset_sessions() -> None:
    """Drop every session. Used by tests."""
    _SESSIONS.clear()
