"""FastAPI app: static files, SSE chat endpoint, report download."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, AsyncIterator

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, PlainTextResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .agent import build_agent
from .config import get_settings
from .errors import NO_REPORT_MESSAGE, friendly_error
from .render import render_markdown
from .session import Session, get_or_create_session, get_session

get_settings()  # fail fast at import time if a key is missing

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
SUMMARY_CHARS = 120
INPUT_CHARS = 200

app = FastAPI(title="Agente de Informes")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


class ChatRequest(BaseModel):
    session_id: str
    message: str


def sse(payload: dict[str, Any]) -> str:
    """Serialise one SSE frame."""
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _tool_input(event: dict) -> str:
    """A short, displayable rendering of a tool's arguments."""
    data = event.get("data", {}).get("input")
    if isinstance(data, dict):
        value = data.get("query") or next(iter(data.values()), "")
        return str(value)[:INPUT_CHARS]
    return str(data)[:INPUT_CHARS]


def _summary(event: dict) -> str:
    """First line of a tool's observation — the tools format it as a summary."""
    output = event.get("data", {}).get("output")
    text = getattr(output, "content", output)
    return str(text).split("\n", 1)[0][:SUMMARY_CHARS]


async def event_stream(session: Session, message: str) -> AsyncIterator[str]:
    """Translate the agent's event stream into SSE frames."""
    agent = build_agent(session)
    config = {"configurable": {"session_id": session.id}}
    published = False
    try:
        async for event in agent.astream_events({"input": message}, config=config, version="v2"):
            kind = event["event"]
            if kind == "on_chat_model_stream":
                text = event["data"]["chunk"].content
                if text:
                    yield sse({"type": "token", "text": text})
            elif kind == "on_tool_start":
                yield sse({"type": "step", "tool": event["name"], "input": _tool_input(event)})
            elif kind == "on_tool_end":
                name = event["name"]
                if name == "write_report":
                    published = True
                    yield sse(
                        {
                            "type": "report",
                            "markdown": session.report,
                            "html": render_markdown(session.report),
                        }
                    )
                    yield sse({"type": "step_done", "tool": name, "summary": "Informe publicado"})
                else:
                    yield sse({"type": "step_done", "tool": name, "summary": _summary(event)})
        if not published and not session.report:
            yield sse({"type": "error", "message": NO_REPORT_MESSAGE})
    except Exception as exc:  # CancelledError is a BaseException and passes through
        yield sse({"type": "error", "message": friendly_error(exc)})
    yield sse({"type": "done"})


@app.get("/")
async def index() -> FileResponse:
    """Serve the app shell."""
    return FileResponse(STATIC_DIR / "index.html")


@app.post("/api/chat")
async def chat(request: ChatRequest) -> StreamingResponse:
    """Run one agent turn, streaming progress as SSE."""
    session = get_or_create_session(request.session_id)
    return StreamingResponse(
        event_stream(session, request.message),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/api/report/{session_id}")
async def report(session_id: str) -> PlainTextResponse:
    """Raw markdown of the session's current report, for the download button."""
    session = get_session(session_id)
    if session is None or not session.report:
        raise HTTPException(status_code=404, detail="No hay informe para esta sesión.")
    return PlainTextResponse(session.report, media_type="text/markdown; charset=utf-8")
