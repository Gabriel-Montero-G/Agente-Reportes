# Agente de Generación de Informes — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` to implement this plan task-by-task, dispatching the repo-local subagent named in each task's **Agent** field. Steps use checkbox (`- [ ]`) syntax for tracking.

## Context

The repo is currently empty of code — only `docs/` and `.claude/agents/` exist. The approved spec ([Report Generation Agent — Design.md](docs/superpowers/specs/Report%20Generation%20Agent%20—%20Design.md)) describes a single-user local web app: chat on the left, a live research brief on the right. A ReAct agent (plain LangChain, no LangGraph) searches with Tavily and writes a 300–600 word Spanish brief through a `write_report` tool, streamed to the browser over SSE. This plan builds that application from zero.

**Goal:** A local FastAPI app where typing a topic in the chat produces a cited 300–600 word brief in the right-hand panel, refinable through conversation.

**Architecture:** FastAPI serves static HTML/JS and one SSE endpoint. Per request, a `RunnableWithMessageHistory` wraps an `AgentExecutor` built *per session*, so the `write_report` tool closes over the correct session's state. `astream_events(version="v2")` is translated event-by-event into SSE frames. Everything lives in memory; the process dying discards all state, by design.

**Tech Stack:** Python 3.11+, LangChain 0.3.x, `langchain-openai` → OpenRouter, `langchain-tavily`, FastAPI + uvicorn, `markdown` + `bleach` for server-side rendering, pytest + pytest-asyncio. Vanilla HTML/CSS/JS, no bundler.

## Global Constraints

Every task's requirements implicitly include this section.

- **Model:** `nvidia/nemotron-3-ultra-550b-a55b:free` — verified live on OpenRouter's model list: 1M context, `tools` in `supported_parameters`. Overridable via the `MODEL_ID` env var.
- **Base URL:** `https://openrouter.ai/api/v1`.
- **LangChain line is pinned to 0.3.x** (`langchain>=0.3,<1.0`, `langchain-core>=0.3,<1.0`). LangChain 1.x moved `AgentExecutor` and `create_tool_calling_agent` into the separate `langchain-classic` package; pinning 0.3 keeps the spec's import paths valid. **Never** run a bare `pip install -U langchain`.
- **Executor caps:** `max_iterations=6`, `max_execution_time=120`. OpenRouter's free tier gives 20 req/min and 50 req/day.
- **User-facing language is Spanish** — system prompt, UI copy, error messages, tool descriptions. Code identifiers, docstrings and commit messages are English.
- **No test in the default suite touches the network or consumes quota.** The live smoke test is marked `@pytest.mark.live` and excluded via `addopts` in `pytest.ini`.
- **All LLM-authored markdown is sanitized with `bleach` before reaching the browser.** Chat text is inserted with `textContent`, never `innerHTML`.
- Type hints on every function signature; `from __future__ import annotations` at the top of each module.
- Commit after every task (the plan's last step in each task). Work on the current `master` branch.

## Deviations from the spec (deliberate, small)

1. **Two extra modules** not in the spec's file tree: `app/render.py` (markdown → sanitized HTML) and `app/errors.py` (429 classification + Spanish messages). The spec assigns both jobs to `server.py`; splitting them keeps `server.py` to routing and SSE translation and makes both unit-testable without a `TestClient`.
2. **429 backoff is the OpenAI SDK's `max_retries=2`**, not the literal 2s/6s waits the spec names. The SDK honors OpenRouter's `Retry-After` header and retries only the LLM call, which is more correct than a hand-rolled sleep around a partially-streamed agent run. The daily-quota 429 still burns those two retries before surfacing; the user-facing message is unaffected.

## File Structure

| Path | Responsibility |
|---|---|
| `app/config.py` | Env vars, validated at import time. `Settings`, `ConfigError`, `get_settings()`. |
| `app/llm.py` | The only place OpenRouter is configured. `build_llm()`. |
| `app/session.py` | `session_id → Session` dict. Each `Session` holds history + current report markdown. |
| `app/render.py` | `render_markdown()` — markdown → bleach-sanitized HTML. |
| `app/errors.py` | Classifies rate-limit exceptions, produces Spanish user-facing messages. |
| `app/tools.py` | `tavily_search` tool + `make_write_report(session)` factory + `build_tools(session)`. |
| `app/agent.py` | System prompt, `create_tool_calling_agent`, `AgentExecutor`, `RunnableWithMessageHistory`. |
| `app/server.py` | FastAPI: static files, `/api/chat` SSE, `/api/report/{id}`. |
| `static/index.html`, `app.js`, `styles.css` | Two-panel UI, hand-rolled SSE parser. |
| `tests/` | `conftest.py` + one test module per app module + `test_live.py`. |

Dependency direction is strictly one-way: `config → llm/session → render/errors/tools → agent → server`. No module imports `server`.

---

## Task 0: Land the plan

**Agent:** none — the orchestrating session does this.

- [ ] **Step 1: Copy this plan into the repo**

Copy this file to `docs/superpowers/plans/2026-07-27-agente-reportes.md`.

- [ ] **Step 2: Commit the plan and the spec rename**

`git status` shows the spec was renamed (`docs/superpowers/specs/2026-07-27-agente-reportes-design.md` deleted, `Report Generation Agent — Design.md` untracked). Stage both so the rename is recorded.

```bash
git add -A docs/
git commit -m "docs: add implementation plan and rename design spec"
```

---

## Task 1: Scaffolding and configuration

**Agent:** `python-expert`

**Files:**
- Create: `requirements.txt`, `pytest.ini`, `.env.example`, `app/__init__.py`, `app/config.py`, `tests/__init__.py`, `tests/conftest.py`
- Test: `tests/test_config.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `app.config.Settings(openrouter_api_key: str, tavily_api_key: str, model_id: str)`, `app.config.ConfigError`, `app.config.get_settings() -> Settings` (lru_cached, `.cache_clear()` available), `app.config.load_settings() -> Settings`, constants `DEFAULT_MODEL_ID`, `OPENROUTER_BASE_URL`.

- [ ] **Step 1: Create the virtualenv and install dependencies**

Write `requirements.txt`:

```
langchain>=0.3,<1.0
langchain-core>=0.3,<1.0
langchain-openai>=0.2,<1.0
langchain-tavily>=0.2,<1.0
fastapi>=0.115
uvicorn[standard]>=0.30
python-dotenv>=1.0
markdown>=3.6
bleach>=6.1
pytest>=8.0
pytest-asyncio>=0.24
httpx>=0.27
```

Then, from the repo root (Windows PowerShell):

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

All later `pytest` / `uvicorn` invocations use `.venv\Scripts\python.exe -m ...`.

- [ ] **Step 2: Write `pytest.ini` and `.env.example`**

`pytest.ini`:

```ini
[pytest]
testpaths = tests
asyncio_mode = auto
addopts = -m "not live"
markers =
    live: hits real APIs and spends quota; excluded by default
```

`.env.example`:

```
# OpenRouter — https://openrouter.ai/keys
OPENROUTER_API_KEY=sk-or-v1-xxxxxxxx
# Tavily — https://app.tavily.com
TAVILY_API_KEY=tvly-xxxxxxxx
# Optional. Free tier: 20 req/min, 50 req/day.
MODEL_ID=nvidia/nemotron-3-ultra-550b-a55b:free
```

`.gitignore` already excludes `.env`, `__pycache__/`, `.venv/`, `.pytest_cache/` — leave it alone.

- [ ] **Step 3: Write `tests/conftest.py`**

`app/__init__.py` and `tests/__init__.py` are empty files.

```python
"""Shared fixtures. No test in the default suite touches the network."""
from __future__ import annotations

import pytest

from app import config
from app import session as session_mod


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
```

Note: `conftest.py` imports `app.session`, which Task 2 creates. Until then this import fails — that is expected and is what Step 5 verifies against. If the agent implementing Task 1 wants a green run before Task 2 exists, it may temporarily drop the `session_mod` lines, but **must** restore them in Task 2.

- [ ] **Step 4: Write the failing test**

`tests/test_config.py`:

```python
from __future__ import annotations

import pytest

from app.config import DEFAULT_MODEL_ID, ConfigError, get_settings, load_settings


def test_load_settings_reads_env():
    settings = load_settings()
    assert settings.openrouter_api_key == "test-openrouter-key"
    assert settings.tavily_api_key == "test-tavily-key"
    assert settings.model_id == DEFAULT_MODEL_ID


def test_model_id_is_overridable(monkeypatch):
    monkeypatch.setenv("MODEL_ID", "some/other-model")
    assert load_settings().model_id == "some/other-model"


def test_missing_key_raises_with_the_variable_name(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with pytest.raises(ConfigError, match="OPENROUTER_API_KEY"):
        load_settings()


def test_get_settings_is_cached():
    assert get_settings() is get_settings()
```

- [ ] **Step 5: Run the test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_config.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.config'`.

- [ ] **Step 6: Write `app/config.py`**

```python
"""Environment configuration, validated at startup."""
from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache

from dotenv import load_dotenv

DEFAULT_MODEL_ID = "nvidia/nemotron-3-ultra-550b-a55b:free"
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
_REQUIRED = ("OPENROUTER_API_KEY", "TAVILY_API_KEY")


class ConfigError(RuntimeError):
    """Raised when a required environment variable is missing."""


@dataclass(frozen=True)
class Settings:
    """Validated runtime configuration."""

    openrouter_api_key: str
    tavily_api_key: str
    model_id: str = DEFAULT_MODEL_ID


def load_settings() -> Settings:
    """Read and validate the environment.

    Raises:
        ConfigError: if any required variable is missing or empty.
    """
    load_dotenv()
    missing = [name for name in _REQUIRED if not os.getenv(name)]
    if missing:
        raise ConfigError(
            "Faltan variables de entorno: "
            + ", ".join(missing)
            + ". Copia .env.example a .env y rellena las claves."
        )
    return Settings(
        openrouter_api_key=os.environ["OPENROUTER_API_KEY"],
        tavily_api_key=os.environ["TAVILY_API_KEY"],
        model_id=os.getenv("MODEL_ID") or DEFAULT_MODEL_ID,
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Process-wide settings, loaded once."""
    return load_settings()
```

- [ ] **Step 7: Run the test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_config.py -v`
Expected: 4 passed.

- [ ] **Step 8: Commit**

```bash
git add requirements.txt pytest.ini .env.example app/ tests/
git commit -m "feat: project scaffolding and validated configuration"
```

---

## Task 2: Session store and LLM client

**Agent:** `python-expert`

**Files:**
- Create: `app/session.py`, `app/llm.py`
- Test: `tests/test_session.py`, `tests/test_llm.py`
- Modify: `tests/conftest.py` (restore the `session_mod` lines if they were dropped in Task 1)

**Interfaces:**
- Consumes: `app.config.get_settings()`, `app.config.OPENROUTER_BASE_URL`.
- Produces: `app.session.Session` (dataclass: `id: str`, `history: InMemoryChatMessageHistory`, `report: str = ""`), `get_or_create_session(session_id: str) -> Session`, `get_session(session_id: str) -> Session | None`, `reset_sessions() -> None`; `app.llm.build_llm() -> ChatOpenAI`.

- [ ] **Step 1: Write the failing tests**

`tests/test_session.py`:

```python
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
```

`tests/test_llm.py`:

```python
from __future__ import annotations

from app.config import DEFAULT_MODEL_ID, OPENROUTER_BASE_URL
from app.llm import build_llm


def test_build_llm_points_at_openrouter():
    llm = build_llm()
    assert llm.model_name == DEFAULT_MODEL_ID
    assert str(llm.openai_api_base).rstrip("/") == OPENROUTER_BASE_URL
    assert llm.streaming is True


def test_build_llm_honours_model_id_override(monkeypatch):
    from app import config

    monkeypatch.setenv("MODEL_ID", "some/other-model")
    config.get_settings.cache_clear()
    assert build_llm().model_name == "some/other-model"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_session.py tests/test_llm.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.session'`.

- [ ] **Step 3: Write `app/session.py`**

```python
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
```

- [ ] **Step 4: Write `app/llm.py`**

```python
"""The single place where the LLM provider is configured."""
from __future__ import annotations

from langchain_openai import ChatOpenAI

from .config import OPENROUTER_BASE_URL, get_settings

REQUEST_TIMEOUT_SECONDS = 90
MAX_RETRIES = 2


def build_llm() -> ChatOpenAI:
    """Build the streaming OpenRouter client.

    `max_retries` covers per-minute 429s: the OpenAI SDK backs off and honours
    OpenRouter's Retry-After header. Daily-quota 429s are surfaced to the user
    by `app.errors` instead.
    """
    settings = get_settings()
    return ChatOpenAI(
        model=settings.model_id,
        api_key=settings.openrouter_api_key,
        base_url=OPENROUTER_BASE_URL,
        streaming=True,
        temperature=0.3,
        timeout=REQUEST_TIMEOUT_SECONDS,
        max_retries=MAX_RETRIES,
    )
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_session.py tests/test_llm.py -v`
Expected: 8 passed. If `llm.model_name` or `llm.openai_api_base` are named differently in the installed `langchain-openai`, check with `.venv\Scripts\python.exe -c "from app.llm import build_llm; print(build_llm().dict())"` and fix the *assertions*, not the implementation.

- [ ] **Step 6: Commit**

```bash
git add app/session.py app/llm.py tests/
git commit -m "feat: in-memory session store and OpenRouter client"
```

---

## Task 3: Markdown rendering and error classification

**Agent:** `python-expert`

**Files:**
- Create: `app/render.py`, `app/errors.py`
- Test: `tests/test_render.py`, `tests/test_errors.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `app.render.render_markdown(text: str) -> str`; `app.errors.friendly_error(exc: BaseException) -> str`, `app.errors.is_rate_limit(exc) -> bool`, `app.errors.is_daily_quota(exc) -> bool`, constants `DAILY_QUOTA_MESSAGE`, `RATE_LIMIT_MESSAGE`, `NO_REPORT_MESSAGE`.

- [ ] **Step 1: Write the failing tests**

`tests/test_render.py`:

```python
from __future__ import annotations

from app.render import render_markdown


def test_renders_headings_and_lists():
    html = render_markdown("# Título\n\n- uno\n- dos")
    assert "<h1>Título</h1>" in html
    assert "<li>uno</li>" in html


def test_strips_script_tags():
    html = render_markdown("Hola <script>alert('xss')</script> mundo")
    assert "<script>" not in html
    assert "alert" not in html


def test_strips_event_handlers_and_javascript_urls():
    html = render_markdown('<a href="javascript:alert(1)" onclick="evil()">clic</a>')
    assert "javascript:" not in html
    assert "onclick" not in html


def test_keeps_http_links_and_opens_them_in_a_new_tab():
    html = render_markdown("[Fuente](https://example.com)")
    assert 'href="https://example.com"' in html
    assert 'target="_blank"' in html


def test_empty_input_renders_empty_string():
    assert render_markdown("") == ""
```

`tests/test_errors.py`:

```python
from __future__ import annotations

from app.errors import (
    DAILY_QUOTA_MESSAGE,
    RATE_LIMIT_MESSAGE,
    friendly_error,
    is_daily_quota,
    is_rate_limit,
)


class FakeApiError(Exception):
    def __init__(self, message: str, status_code: int) -> None:
        super().__init__(message)
        self.status_code = status_code


def test_detects_a_rate_limit_by_status_code():
    assert is_rate_limit(FakeApiError("slow down", 429))


def test_daily_quota_error_is_recognised():
    exc = FakeApiError("Rate limit exceeded: free-models-per-day", 429)
    assert is_daily_quota(exc)
    assert friendly_error(exc) == DAILY_QUOTA_MESSAGE


def test_per_minute_limit_is_not_a_daily_quota_error():
    exc = FakeApiError("Rate limit exceeded: 20 requests per minute", 429)
    assert is_rate_limit(exc)
    assert not is_daily_quota(exc)
    assert friendly_error(exc) == RATE_LIMIT_MESSAGE


def test_unknown_errors_get_a_generic_spanish_message():
    message = friendly_error(ValueError("boom"))
    assert "boom" in message
    assert message.startswith("Error")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_render.py tests/test_errors.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.render'`.

- [ ] **Step 3: Write `app/render.py`**

```python
"""Server-side markdown rendering. The LLM writes from uncontrolled web pages,
so sanitising is not optional."""
from __future__ import annotations

import bleach
import markdown as markdown_lib
from bleach.callbacks import target_blank

ALLOWED_TAGS = frozenset({
    "h1", "h2", "h3", "h4", "h5", "h6",
    "p", "br", "hr", "blockquote",
    "ul", "ol", "li",
    "strong", "em", "code", "pre",
    "a", "table", "thead", "tbody", "tr", "th", "td",
})
ALLOWED_ATTRIBUTES = {"a": ["href", "title"]}
ALLOWED_PROTOCOLS = frozenset({"http", "https", "mailto"})


def render_markdown(text: str) -> str:
    """Convert markdown to HTML that is safe to inject into the report panel."""
    if not text:
        return ""
    html = markdown_lib.markdown(text, extensions=["extra", "sane_lists"])
    clean = bleach.clean(
        html,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        protocols=ALLOWED_PROTOCOLS,
        strip=True,
    )
    return bleach.linkify(clean, callbacks=[target_blank])
```

- [ ] **Step 4: Write `app/errors.py`**

```python
"""Turns provider exceptions into messages a user can act on."""
from __future__ import annotations

DAILY_QUOTA_MESSAGE = (
    "Has agotado las 50 peticiones diarias del tier gratuito de OpenRouter. "
    "Espera al reinicio o cambia MODEL_ID a la variante de pago del modelo."
)
RATE_LIMIT_MESSAGE = (
    "OpenRouter está limitando las peticiones por minuto (20/min en el tier "
    "gratuito). Espera unos segundos y vuelve a intentarlo."
)
NO_REPORT_MESSAGE = (
    "El agente agotó sus iteraciones sin publicar el informe. La conversación "
    "se ha guardado: pídele «escribe el informe con lo que has encontrado» "
    "para terminarlo sin repetir la investigación."
)
_DAILY_MARKERS = ("per-day", "per day", "daily", "free-models-per-day")


def is_rate_limit(exc: BaseException) -> bool:
    """True if `exc` looks like an HTTP 429 from the provider."""
    if getattr(exc, "status_code", None) == 429:
        return True
    return "429" in str(exc) or "rate limit" in str(exc).lower()


def is_daily_quota(exc: BaseException) -> bool:
    """True if the 429 is the daily cap rather than the per-minute one."""
    if not is_rate_limit(exc):
        return False
    text = str(exc).lower()
    return any(marker in text for marker in _DAILY_MARKERS)


def friendly_error(exc: BaseException) -> str:
    """The Spanish message shown in the chat for a failed run."""
    if is_daily_quota(exc):
        return DAILY_QUOTA_MESSAGE
    if is_rate_limit(exc):
        return RATE_LIMIT_MESSAGE
    return f"Error inesperado del agente: {exc}"
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_render.py tests/test_errors.py -v`
Expected: 9 passed. If `bleach.callbacks.target_blank` is unavailable in the installed version, replace the `linkify` call with `bleach.linkify(clean, callbacks=[lambda attrs, new: {**attrs, (None, "target"): "_blank", (None, "rel"): "noopener noreferrer"}])`.

- [ ] **Step 6: Commit**

```bash
git add app/render.py app/errors.py tests/
git commit -m "feat: sanitised markdown rendering and error classification"
```

---

## Task 4: Tools

**Agent:** `python-expert`

**Files:**
- Create: `app/tools.py`
- Test: `tests/test_tools.py`

**Interfaces:**
- Consumes: `app.config.get_settings()`, `app.session.Session`.
- Produces: `app.tools.tavily_search` (a `BaseTool` named `tavily_search`, one `query: str` arg), `app.tools.make_write_report(session: Session) -> BaseTool` (tool named `write_report`, one `markdown: str` arg), `app.tools.build_tools(session: Session) -> list[BaseTool]`, `app.tools._client()` (lru_cached, monkeypatched by tests).

- [ ] **Step 1: Confirm the `TavilySearch` constructor signature**

The wrapper class's keyword arguments differ between `langchain-tavily` releases. Check before writing code:

```powershell
.venv\Scripts\python.exe -c "from langchain_tavily import TavilySearch; import inspect; print(TavilySearch.model_fields.keys())"
```

If an explicit key field exists (e.g. `tavily_api_key` or `api_key`), pass `get_settings().tavily_api_key` to it. Otherwise rely on the `TAVILY_API_KEY` environment variable, which `app.config.load_settings()` has already validated. The code below assumes the env-var path; adjust `_client()` only.

- [ ] **Step 2: Write the failing test**

`tests/test_tools.py`:

```python
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
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_tools.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.tools'`.

- [ ] **Step 4: Write `app/tools.py`**

```python
"""The agent's two tools: web search and report publication."""
from __future__ import annotations

from functools import lru_cache
from typing import Any

from langchain_core.tools import BaseTool, StructuredTool, tool
from langchain_tavily import TavilySearch

from .session import Session

MAX_RESULTS = 5
SNIPPET_CHARS = 600

WRITE_REPORT_DESCRIPTION = (
    "Publica el informe en el panel derecho. Recibe el informe COMPLETO en "
    "Markdown (300-600 palabras, con secciones y una sección final «Fuentes»). "
    "Al refinar, envía SIEMPRE el informe entero reescrito, nunca un fragmento: "
    "el panel se reemplaza por completo y perderías el resto."
)


@lru_cache(maxsize=1)
def _client() -> TavilySearch:
    """The Tavily wrapper, built once. Tests monkeypatch this function."""
    return TavilySearch(max_results=MAX_RESULTS)


def _format_results(query: str, payload: Any) -> str:
    """Render Tavily's payload so the first line is a countable summary."""
    results = payload.get("results", []) if isinstance(payload, dict) else []
    lines = [f"{len(results)} resultados para «{query}»"]
    for index, result in enumerate(results, start=1):
        title = result.get("title") or "(sin título)"
        url = result.get("url") or ""
        content = (result.get("content") or "")[:SNIPPET_CHARS]
        lines.append(f"\n[{index}] {title} — {url}\n{content}")
    return "\n".join(lines)


@tool
def tavily_search(query: str) -> str:
    """Busca en la web información actualizada sobre `query`.

    Devuelve resultados numerados con título, URL y extracto. Usa consultas
    concretas y en el idioma de las fuentes que esperas encontrar.
    """
    try:
        return _format_results(query, _client().invoke({"query": query}))
    except Exception as exc:  # a tool failure is an observation, not a 500
        return f"Búsqueda fallida: {exc}"


def make_write_report(session: Session) -> BaseTool:
    """Build a `write_report` tool bound to one session."""

    def _write_report(markdown: str) -> str:
        session.report = markdown
        return "Informe actualizado."

    return StructuredTool.from_function(
        func=_write_report,
        name="write_report",
        description=WRITE_REPORT_DESCRIPTION,
    )


def build_tools(session: Session) -> list[BaseTool]:
    """Every tool the agent gets, bound to `session`."""
    return [tavily_search, make_write_report(session)]
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_tools.py -v`
Expected: 7 passed.

- [ ] **Step 6: Commit**

```bash
git add app/tools.py tests/test_tools.py
git commit -m "feat: tavily_search and per-session write_report tools"
```

---

## Task 5: Agent

**Agent:** `python-expert`

**Files:**
- Create: `app/agent.py`
- Test: `tests/test_agent.py`

**Interfaces:**
- Consumes: `app.llm.build_llm()`, `app.tools.build_tools(session)`, `app.session.Session`.
- Produces: `app.agent.build_agent(session: Session, llm: BaseChatModel | None = None) -> Runnable` — the `llm` parameter exists so tests can inject a fake model; production callers omit it. Invoke with `{"input": message}` and `config={"configurable": {"session_id": session.id}}`; the result dict's `"output"` key holds the chat reply. Also exports `SYSTEM_PROMPT`, `MAX_ITERATIONS = 6`, `MAX_EXECUTION_TIME = 120`.

- [ ] **Step 1: Write the failing test**

`tests/test_agent.py`:

```python
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
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_agent.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.agent'`.

- [ ] **Step 3: Write `app/agent.py`**

```python
"""Composes the ReAct agent: prompt + tool-calling model + executor + history."""
from __future__ import annotations

from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.language_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.runnables import Runnable
from langchain_core.runnables.history import RunnableWithMessageHistory

from .llm import build_llm
from .session import Session
from .tools import build_tools

MAX_ITERATIONS = 6
MAX_EXECUTION_TIME = 120

SYSTEM_PROMPT = """Eres un analista de investigación. Produces briefs de 300-600 palabras en español.

Reglas de trabajo:
1. Busca antes de afirmar. Usa `tavily_search` para verificar los hechos. Máximo 3 búsquedas por turno.
2. Publica SIEMPRE el brief llamando a la herramienta `write_report`. Nunca escribas el informe en tu respuesta de chat.
3. `write_report` recibe el informe COMPLETO en Markdown. Al refinar, reescribe el brief entero: el panel se reemplaza por completo y enviar solo un fragmento borraría el resto.
4. Estructura del brief: un título con `#`, entre 2 y 4 secciones con `##`, y una sección final `## Fuentes` con la lista numerada de URLs.
5. Cita en el cuerpo con `[n]`, donde `n` es la posición de la fuente en `## Fuentes`.
6. Tu respuesta de chat es breve (1-3 frases): di qué has hecho y qué puede pedirte a continuación. No repitas el contenido del informe.
7. Si una búsqueda falla, reformula la consulta una vez; si vuelve a fallar, escribe el brief con lo que tengas e indica la limitación.
"""


def build_agent(session: Session, llm: BaseChatModel | None = None) -> Runnable:
    """Build the agent for one session.

    Composed per session, not globally: `write_report` closes over `session`,
    so two browser tabs never write into each other's report.

    Args:
        session: the session this agent reads history from and writes reports to.
        llm: injected chat model. Tests pass a fake; production leaves it None.
    """
    tools = build_tools(session)
    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", SYSTEM_PROMPT),
            MessagesPlaceholder("chat_history", optional=True),
            ("human", "{input}"),
            MessagesPlaceholder("agent_scratchpad"),
        ]
    )
    agent = create_tool_calling_agent(llm or build_llm(), tools, prompt)
    executor = AgentExecutor(
        agent=agent,
        tools=tools,
        max_iterations=MAX_ITERATIONS,
        max_execution_time=MAX_EXECUTION_TIME,
        handle_parsing_errors=True,
        return_intermediate_steps=False,
        verbose=False,
    )
    return RunnableWithMessageHistory(
        executor,
        lambda _session_id: session.history,
        input_messages_key="input",
        history_messages_key="chat_history",
        output_messages_key="output",
    )
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_agent.py -v`
Expected: 5 passed.

If `create_tool_calling_agent` rejects the fake model, confirm `ToolCallingFake.bind_tools` is being reached — that override is the whole point of the subclass. If `FakeMessagesListChatModel` lives at a different import path in the installed `langchain-core`, find it with `.venv\Scripts\python.exe -c "import langchain_core.language_models as m; print([n for n in dir(m) if 'Fake' in n])"`.

- [ ] **Step 5: Run the whole suite**

Run: `.venv\Scripts\python.exe -m pytest -v`
Expected: everything green (33 tests so far), no network calls.

- [ ] **Step 6: Commit**

```bash
git add app/agent.py tests/test_agent.py
git commit -m "feat: per-session tool-calling agent with Spanish system prompt"
```

---

## Task 6: FastAPI server and SSE translation

**Agent:** `backend-developer`

**Files:**
- Create: `app/server.py`
- Test: `tests/test_server.py`

**Interfaces:**
- Consumes: `app.agent.build_agent`, `app.session.get_or_create_session/get_session`, `app.render.render_markdown`, `app.errors.friendly_error/NO_REPORT_MESSAGE`, `app.config.get_settings`.
- Produces: `app.server.app` (FastAPI instance), `app.server.event_stream(session, message) -> AsyncIterator[str]`, `app.server.sse(payload: dict) -> str`. Tests monkeypatch `app.server.build_agent`.

**SSE contract** (each frame is one `data: {json}\n\n` line):

| `type` | Fields |
|---|---|
| `token` | `text` |
| `step` | `tool`, `input` |
| `step_done` | `tool`, `summary` |
| `report` | `html`, `markdown` |
| `error` | `message` |
| `done` | — |

- [ ] **Step 1: Write the failing test**

`tests/test_server.py`:

```python
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
```

Note: `test_root_serves_the_app_shell` needs `static/index.html` to exist. Create a one-line placeholder (`<!doctype html><title>Agente de Informes</title>`) in this task; Task 7 replaces it.

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_server.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.server'`.

- [ ] **Step 3: Write `app/server.py`**

```python
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
```

The `done` frame is emitted **after** the `try`, never in a `finally`: yielding inside `finally` while the generator is being closed (client closed the tab) raises `RuntimeError: async generator ignored GeneratorExit`.

- [ ] **Step 4: Run the test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_server.py -v`
Expected: 10 passed.

- [ ] **Step 5: Verify the event names against the real LangChain version**

The v2 event names (`on_chat_model_stream`, `on_tool_start`, `on_tool_end`) and the shape of `data["input"]` / `data["output"]` are asserted by stubs, so a mismatch with the installed LangChain would only show up live. Confirm now:

```powershell
.venv\Scripts\python.exe -c "import langchain_core; print(langchain_core.__version__)"
```

Version must be `0.3.x`. The real check happens in Task 8's live smoke test.

- [ ] **Step 6: Commit**

```bash
git add app/server.py tests/test_server.py static/index.html
git commit -m "feat: FastAPI SSE endpoint and report download"
```

---

## Task 7: Two-panel UI

**Agent:** `frontend-developer` — brief it explicitly: **vanilla HTML/CSS/JS only, no React, no TypeScript, no build step, no npm, no CDN links.**

**Files:**
- Create/replace: `static/index.html`, `static/app.js`, `static/styles.css`

**Interfaces:**
- Consumes: `POST /api/chat` (`{session_id, message}` → SSE), `GET /api/report/{session_id}` (markdown).
- Produces: nothing importable.

**Requirements:**
- Chat left (~40%), brief right (~60%). Brief header shows the report's `<h1>` (or "Informe") plus a "Descargar .md" button, disabled until a report exists.
- Empty state in the right panel: *"Escribe un tema en el chat para generar un brief."*
- `session_id` = `crypto.randomUUID()`, persisted in `sessionStorage` under `session_id`.
- **Chat text is inserted with `textContent`.** Only the report panel uses `innerHTML`, and only with the server-sanitised `html` field.
- Steps render as `🔍 Buscando: <query>` and close to `✓ <summary>`; `write_report` renders as `✍️ Escribiendo el informe`.
- The composer is disabled while a turn is streaming.

- [ ] **Step 1: Write `static/index.html`**

```html
<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Agente de Informes</title>
  <link rel="stylesheet" href="/static/styles.css">
</head>
<body>
  <main class="layout">
    <section class="panel panel--chat">
      <header class="panel__header"><h2>Conversación</h2></header>
      <div id="chat" class="chat" aria-live="polite"></div>
      <form id="composer" class="composer">
        <input id="prompt" type="text" autocomplete="off"
               placeholder="Escribe un tema, p. ej. «energía eólica marina en España»">
        <button id="send" type="submit">Enviar</button>
      </form>
    </section>
    <section class="panel panel--report">
      <header class="panel__header">
        <h2 id="report-title">Informe</h2>
        <button id="download" type="button" disabled>Descargar .md</button>
      </header>
      <div id="empty" class="empty">Escribe un tema en el chat para generar un brief.</div>
      <article id="report" class="report"></article>
    </section>
  </main>
  <script src="/static/app.js"></script>
</body>
</html>
```

- [ ] **Step 2: Write `static/app.js`**

```javascript
"use strict";

const chatEl = document.getElementById("chat");
const formEl = document.getElementById("composer");
const inputEl = document.getElementById("prompt");
const sendEl = document.getElementById("send");
const reportEl = document.getElementById("report");
const emptyEl = document.getElementById("empty");
const titleEl = document.getElementById("report-title");
const downloadEl = document.getElementById("download");

const sessionId = (() => {
  let id = sessionStorage.getItem("session_id");
  if (!id) {
    id = crypto.randomUUID();
    sessionStorage.setItem("session_id", id);
  }
  return id;
})();

let hasReport = false;

function addBubble(role, text) {
  const el = document.createElement("div");
  el.className = `bubble bubble--${role}`;
  el.textContent = text || "";
  chatEl.appendChild(el);
  chatEl.scrollTop = chatEl.scrollHeight;
  return el;
}

function addStep(tool, input) {
  const el = document.createElement("div");
  el.className = "step";
  el.textContent = tool === "write_report" ? "✍️ Escribiendo el informe" : `🔍 Buscando: ${input}`;
  chatEl.appendChild(el);
  chatEl.scrollTop = chatEl.scrollHeight;
  return el;
}

async function* readSSE(stream) {
  const reader = stream.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let index;
    while ((index = buffer.indexOf("\n\n")) !== -1) {
      const frame = buffer.slice(0, index);
      buffer = buffer.slice(index + 2);
      for (const line of frame.split("\n")) {
        if (!line.startsWith("data:")) continue;
        try {
          yield JSON.parse(line.slice(5).trim());
        } catch (err) {
          console.warn("frame SSE ilegible", line);
        }
      }
    }
  }
}

function showReport(html, markdown) {
  reportEl.innerHTML = html;
  emptyEl.hidden = true;
  hasReport = true;
  downloadEl.disabled = false;
  const heading = reportEl.querySelector("h1");
  titleEl.textContent = heading ? heading.textContent : "Informe";
}

function setBusy(busy) {
  inputEl.disabled = busy;
  sendEl.disabled = busy;
  if (!busy) inputEl.focus();
}

formEl.addEventListener("submit", async (event) => {
  event.preventDefault();
  const message = inputEl.value.trim();
  if (!message) return;
  inputEl.value = "";
  setBusy(true);
  addBubble("user", message);

  let assistantEl = null;
  const openSteps = new Map();

  try {
    const response = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: sessionId, message }),
    });
    if (!response.ok || !response.body) throw new Error(`HTTP ${response.status}`);

    for await (const event of readSSE(response.body)) {
      if (event.type === "token") {
        if (!assistantEl) assistantEl = addBubble("assistant", "");
        assistantEl.textContent += event.text;
        chatEl.scrollTop = chatEl.scrollHeight;
      } else if (event.type === "step") {
        openSteps.set(event.tool, addStep(event.tool, event.input));
      } else if (event.type === "step_done") {
        const stepEl = openSteps.get(event.tool);
        if (stepEl) {
          stepEl.textContent = `✓ ${event.summary}`;
          stepEl.classList.add("step--done");
          openSteps.delete(event.tool);
        }
      } else if (event.type === "report") {
        showReport(event.html, event.markdown);
      } else if (event.type === "error") {
        addBubble("error", event.message);
      }
    }
  } catch (err) {
    addBubble("error", `No se pudo contactar con el servidor: ${err.message}`);
  } finally {
    setBusy(false);
  }
});

downloadEl.addEventListener("click", async () => {
  if (!hasReport) return;
  const response = await fetch(`/api/report/${sessionId}`);
  if (!response.ok) {
    addBubble("error", "No hay informe disponible para descargar.");
    return;
  }
  const blob = new Blob([await response.text()], { type: "text/markdown;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = "informe.md";
  link.click();
  URL.revokeObjectURL(url);
});

inputEl.focus();
```

- [ ] **Step 3: Write `static/styles.css`**

```css
:root {
  --bg: #0f1115;
  --panel: #161a21;
  --border: #262c37;
  --text: #e6e9ef;
  --muted: #9aa4b2;
  --accent: #6ea8fe;
  --error: #ff8f8f;
}

* { box-sizing: border-box; }

body {
  margin: 0;
  height: 100vh;
  background: var(--bg);
  color: var(--text);
  font: 15px/1.6 system-ui, -apple-system, "Segoe UI", sans-serif;
}

.layout { display: grid; grid-template-columns: 40% 60%; height: 100vh; }

.panel { display: flex; flex-direction: column; min-height: 0; background: var(--panel); }
.panel--chat { border-right: 1px solid var(--border); }

.panel__header {
  display: flex; align-items: center; justify-content: space-between; gap: 12px;
  padding: 12px 18px; border-bottom: 1px solid var(--border);
}
.panel__header h2 { margin: 0; font-size: 15px; font-weight: 600; }

.chat { flex: 1; overflow-y: auto; padding: 18px; display: flex; flex-direction: column; gap: 10px; }

.bubble { padding: 10px 14px; border-radius: 12px; max-width: 90%; white-space: pre-wrap; }
.bubble--user { align-self: flex-end; background: var(--accent); color: #0b1020; }
.bubble--assistant { align-self: flex-start; background: #1e242e; }
.bubble--error { align-self: stretch; background: #3a1f22; color: var(--error); }

.step { font-size: 13px; color: var(--muted); font-style: italic; padding-left: 4px; }
.step--done { font-style: normal; }

.composer { display: flex; gap: 8px; padding: 12px 18px; border-top: 1px solid var(--border); }
.composer input {
  flex: 1; padding: 10px 12px; border-radius: 10px;
  border: 1px solid var(--border); background: #11151b; color: var(--text);
}
.composer input:disabled { opacity: 0.5; }

button {
  padding: 10px 16px; border: 0; border-radius: 10px;
  background: var(--accent); color: #0b1020; font-weight: 600; cursor: pointer;
}
button:disabled { opacity: 0.4; cursor: default; }

.empty { padding: 32px 24px; color: var(--muted); }

.report { flex: 1; overflow-y: auto; padding: 24px 32px; max-width: 760px; }
.report h1 { font-size: 24px; margin-top: 0; }
.report h2 { font-size: 17px; margin-top: 28px; border-bottom: 1px solid var(--border); padding-bottom: 6px; }
.report a { color: var(--accent); overflow-wrap: anywhere; }
.report pre { background: #11151b; padding: 12px; border-radius: 8px; overflow-x: auto; }

@media (max-width: 900px) {
  .layout { grid-template-columns: 1fr; grid-template-rows: 1fr 1fr; }
  .panel--chat { border-right: 0; border-bottom: 1px solid var(--border); }
}
```

- [ ] **Step 4: Verify the shell loads**

```powershell
.venv\Scripts\python.exe -m pytest tests/test_server.py -v
```

Expected: 10 passed, including `test_root_serves_the_app_shell` against the real `index.html`.

- [ ] **Step 5: Commit**

```bash
git add static/
git commit -m "feat: two-panel chat and report UI"
```

---

## Task 8: Live smoke test and coverage pass

**Agent:** `test-generator`

**Files:**
- Create: `tests/test_live.py`

**Interfaces:**
- Consumes: `app.agent.build_agent`, `app.session.get_or_create_session`.
- Produces: nothing importable.

- [ ] **Step 1: Write the live smoke test**

```python
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
```

`monkeypatch.undo()` inside a fixture that runs *after* the autouse `fake_env` fixture removes the fake env vars. Verify the ordering works; if it doesn't, replace it with explicit `monkeypatch.delenv` calls followed by `config.load_dotenv()`.

- [ ] **Step 2: Verify the live test is excluded by default**

Run: `.venv\Scripts\python.exe -m pytest -v`
Expected: the whole suite green, `tests/test_live.py` **not collected** (deselected by `addopts = -m "not live"`).

- [ ] **Step 3: Run the live test once, with real keys**

Requires a real `.env`. This spends ~2-6 OpenRouter requests and a handful of Tavily credits.

Run: `.venv\Scripts\python.exe -m pytest -m live -v -s`
Expected: PASS. This is the first real confirmation that the model id, tool-calling support, prompt, and executor caps all work together. If it fails on tool-call format, the fix belongs in `app/agent.py`'s prompt, not the test.

- [ ] **Step 4: Fill coverage gaps**

Run the suite and list what is untested:

```powershell
.venv\Scripts\python.exe -m pytest --tb=short -q
```

Add tests for anything that turned out to be load-bearing but unasserted — in particular `app.server._tool_input` with a non-dict input and `app.server._summary` with a `ToolMessage` output rather than a plain string. Keep them offline.

- [ ] **Step 5: Commit**

```bash
git add tests/
git commit -m "test: live smoke test and coverage gaps"
```

---

## Task 9: README

**Agent:** `doc-generator`

**Files:**
- Create: `README.md`

- [ ] **Step 1: Write `README.md`**

It must cover, in Spanish:

1. **Qué es** — one paragraph: chat izquierda, brief derecha, agente ReAct con Tavily + OpenRouter.
2. **Requisitos** — Python 3.11+, una clave de OpenRouter y otra de Tavily (both free tiers, with signup links).
3. **Instalación** (PowerShell, exact commands):
   ```powershell
   python -m venv .venv
   .venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   Copy-Item .env.example .env   # y rellena las claves
   ```
4. **Ejecución**: `uvicorn app.server:app --reload --port 8000`, then open `http://127.0.0.1:8000`.
5. **Límites de cuota** — 20 req/min y 50 req/día en el tier gratuito de OpenRouter; `max_iterations=6` acota cada informe a ~6 peticiones, es decir unos 8 informes completos al día. Tavily: 1000 créditos/mes.
6. **Uso** — pide un tema; refina con mensajes como «amplía la sección 2» o «añade datos de 2025»; descarga con el botón.
7. **Tests** — `pytest` (sin red, sin claves) y `pytest -m live` (gasta cuota real).
8. **Límites conocidos** — sin persistencia (reiniciar el servidor borra todo), un solo usuario, sin exportación a PDF, `AgentExecutor` está en modo mantenimiento en LangChain (por eso `langchain<1.0` está fijado).

- [ ] **Step 2: Verify every command in the README actually runs**

Execute the install and run commands from a clean shell. Fix the README, not the code, if a command is wrong.

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: README with setup, quota limits and usage"
```

---

## Task 10: Review pass

**Agents:** `code-reviewer`, then `security-auditor`

- [ ] **Step 1: Code review**

Dispatch `code-reviewer` over `git diff master@{u}..HEAD` (or the full tree if there's no upstream). Ask specifically about: dependency direction between `app/` modules, error paths in `event_stream`, and whether any test secretly touches the network.

- [ ] **Step 2: Security review**

Dispatch `security-auditor` with a narrow brief: (a) is `render_markdown` actually XSS-safe for LLM-authored content, (b) does any API key reach the browser, a log line, or an error message, (c) is chat text ever inserted with `innerHTML`.

- [ ] **Step 3: Triage and fix**

Apply `superpowers:receiving-code-review`: verify each finding before implementing it. Push back on anything that contradicts the spec (e.g. "add authentication", "add a database" — both explicitly out of scope).

- [ ] **Step 4: Final verification and commit**

```powershell
.venv\Scripts\python.exe -m pytest -v
```

```bash
git add -A
git commit -m "fix: address code and security review findings"
```

---

## Verification

End-to-end, after all tasks:

1. **Offline suite:** `.venv\Scripts\python.exe -m pytest -v` — all green, `test_live.py` deselected, no network access needed and no keys required (delete `.env` temporarily to prove it: `config` must raise `ConfigError` only when `app.server` is imported, not during the tests, because `conftest.py` injects fake keys).
2. **Startup guard:** rename `.env` away, run `uvicorn app.server:app`. Expected: the server refuses to start with `ConfigError: Faltan variables de entorno: OPENROUTER_API_KEY, TAVILY_API_KEY...`. Restore `.env`.
3. **Happy path:** `uvicorn app.server:app --reload --port 8000`, open `http://127.0.0.1:8000`, type *"Hazme un brief sobre la energía eólica marina en España"*. Expect: `🔍 Buscando:` lines appearing live in the chat, then the brief filling the right panel in one shot, then a 1-3 sentence chat reply. Confirms success criteria 1 and 2.
4. **Refinement:** send *"amplía la sección de retos y añade datos de 2025"*. Expect the whole brief to be rewritten with every section still present. Confirms criterion 3.
5. **Download:** click *"Descargar .md"*. Expect `informe.md` whose content matches the panel. Confirms criterion 4.
6. **Quota exhaustion:** hard to trigger on demand — instead assert it in tests (`test_daily_quota_message_is_explicit`) and, if a real 429 occurs during manual testing, confirm the chat shows the daily-quota message rather than a stack trace. Confirms criterion 5.
7. **Tab close:** start a turn and close the tab mid-stream. Expect no `RuntimeError: async generator ignored GeneratorExit` and no dangling task warning in the uvicorn console.
8. **Two tabs:** open two tabs, generate a different brief in each. Expect no cross-contamination — the per-session agent construction is what guarantees this.
