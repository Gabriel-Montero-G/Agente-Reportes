# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```powershell
# Activate the venv first (all commands below assume this)
.venv\Scripts\Activate.ps1

# Run the app
uvicorn app.server:app --reload --port 8000

# Offline test suite (default: no network, no API keys spent)
pytest

# Single test file / single test
pytest tests/test_agent.py
pytest tests/test_agent.py::test_agent_searches_then_publishes

# Live smoke test — hits real OpenRouter + Tavily, spends real quota. Only run
# when explicitly asked to; requires real keys in .env (not the fake ones conftest injects).
pytest -m live
```

```powershell
# Docker — an alternative to the venv for running the app; needs .env present.
# The image is deliberately portable: no secrets baked in, port from $PORT.
docker compose up --build
docker compose logs -f
docker compose down
```

There is no build/lint step — this is a plain FastAPI app served directly by uvicorn, no bundler for the frontend (`static/`).

## Architecture

**Request flow:** browser → `POST /api/chat` (`app/server.py`) → per-session `AgentExecutor` (`app/agent.py`) → `astream_events(version="v2")` → `event_stream()` translates each LangChain event into one SSE `data: {...}\n\n` frame → browser's hand-rolled SSE parser (`static/app.js`).

**Everything is in-memory, single-process, no auth.** `app/session.py` holds a module-level `dict[str, Session]`; a `Session` bundles one browser tab's chat history *and* its current report markdown. Restarting the process discards all state — this is by design, not a bug to fix. This is also why the container runs one uvicorn worker and must not be scaled to replicas: a request landing on a process that lacks the session's report would 404 on `GET /api/report/{id}`. There is no access control: anyone who can reach the port and knows/guesses a `session_id` can read that session's report via `GET /api/report/{id}`.

**The agent is composed per-session, not globally**, because `write_report` (`app/tools.py::make_write_report`) closes over one specific `Session` object. This is what keeps two browser tabs from overwriting each other's report — there's no session-id parameter threaded through the tool call itself. `app/agent.py::build_agent(session, llm=None)` takes an optional injected `llm` so tests can pass a fake chat model without touching `app.llm.build_llm()` (the only place OpenRouter credentials are used).

**Dependency direction is strictly one-way:** `config → llm/session → render/errors/tools → agent → server`. No module imports `server`. When adding something, keep it flowing this direction rather than reaching back upstream.

**SSE contract** (`app/server.py::event_stream`) — the frontend and any test stubbing the agent must agree on this shape:

| `type` | Fields | Emitted on |
|---|---|---|
| `token` | `text` | `on_chat_model_stream` — the agent's chat reply (always *after* the report is published, per the system prompt) |
| `step` | `tool`, `input`, `run_id` | `on_tool_start` |
| `step_done` | `tool`, `summary`, `run_id` | `on_tool_end` |
| `report` | `markdown`, `html` | `on_tool_end` for `write_report` specifically |
| `error` | `message` | any exception, or a finished run with no report published |
| `done` | — | always last, even after an error |

`step`/`step_done` are correlated by `run_id`, not by tool name — two concurrent `tavily_search` calls in the same turn get distinct `run_id`s. The `done` frame is yielded after the `try/except`, never in a `finally`: yielding inside `finally` while the generator is being closed (client tab closed mid-stream) raises `RuntimeError: async generator ignored GeneratorExit`.

**The frontend (`static/`) derives all displayed numbers from that SSE stream and from the raw report markdown** — word counts, section counts, cited-source domains, elapsed time. Nothing is fabricated client-side; if you add a UI element that needs data the backend doesn't expose, get it from parsing the markdown/HTML already sent rather than inventing a new value.

**Sanitization is server-side and non-negotiable** (`app/render.py`): the agent's markdown originates from scraped web pages via Tavily, so `render_markdown()` always runs through `bleach.clean` + a hardened `linkify` (forces `rel="noopener noreferrer"` on every link, since `Fuentes` links point to untrusted third-party pages) before reaching the browser. The frontend must only insert this pre-sanitized `html` field via `innerHTML`; any other agent-authored text goes through `textContent`.

**Rate-limit handling is split in two places:** `app/llm.py` sets `max_retries=2` on the `ChatOpenAI` client so the OpenAI SDK silently backs off on transient per-minute 429s (honouring OpenRouter's `Retry-After`). `app/errors.py` classifies the *daily*-quota 429 (unrecoverable until reset) versus the per-minute one, producing distinct Spanish user-facing messages.

**LangChain is pinned to `<1.0`** (`requirements.txt`) because `AgentExecutor` / `create_tool_calling_agent` moved to a separate `langchain-classic` package in 1.x. Do not run a bare `pip install -U langchain` or migrate off `AgentExecutor` without a deliberate decision to do so.

**User-facing language is Spanish** — system prompt (`app/agent.py::SYSTEM_PROMPT`), UI copy, and error messages (`app/errors.py`) are all Spanish by design. Code identifiers, docstrings, and commit messages stay English.

## Testing conventions

`tests/conftest.py` autouse-injects fake OpenRouter/Tavily keys and resets the session store before/after every test — no test in the default suite touches the network or spends quota. `pytest.ini` excludes `tests/test_live.py` (`-m "not live"`) since it's the only test that hits real APIs. When stubbing the agent in a test (see `tests/test_server.py`), replicate the SSE contract table above exactly, including `run_id`.
