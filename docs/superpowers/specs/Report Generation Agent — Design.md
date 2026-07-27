# Report Generation Agent — Design

**Date:** 2026-07-27
**Status:** approved, pending implementation plan

## Problem

Producing a research brief on any topic requires searching for sources, reading them, and synthesizing them. The goal is a local application where the user types a topic into a chat, an agent researches the web, and publishes a one-page brief in an adjacent panel, refinable through conversation.

## Scope

A single-user local web application with two panels: chat on the left, brief on the right. The agent researches with Tavily and writes using a free NVIDIA model served through OpenRouter. The brief is the session's living artifact: the user requests changes via chat ("expand section 2," "add 2025 data") and the panel updates.

**Out of scope:** authentication, multi-user support, disk or database persistence, PDF export, history of previous reports.

## Constraints that drive the design

**OpenRouter's free tier allows 20 requests per minute and 50 per day** (rising to 1000/day only if the account has purchased ≥$10 in credits at some point). Each agent iteration consumes one request. This limit shapes the executor's caps, the system prompt, and error handling.

**Model:** `nvidia/nemotron-3-ultra-550b-a55b:free` — 1M context, supports native tool calling. It is the only suitable free NVIDIA model on OpenRouter: `nvidia/nemotron-3.5-content-safety:free` is a guardrail model with no tool support, and `nvidia/nemotron-3-ultra-550b-a55b` (without the suffix) is paid.

**Tavily**'s free tier offers 1000 monthly credits.

## Design decisions

| Decision | Choice | Reason |
|---|---|---|
| Agent architecture | ReAct with `AgentExecutor` | Chosen by the user over a deterministic pipeline, for flexibility across varied topics |
| Framework | Plain LangChain, no LangGraph | Explicit user requirement |
| Agent construction | `create_tool_calling_agent` | The model supports native tools; avoids the fragile `Thought:/Action:` parsing of textual ReAct |
| Interface | FastAPI + vanilla HTML/JS | Control over the two-panel layout and streaming, with no build step |
| Persistence | None, everything in memory | Minimal scope; `.md` download for anything worth keeping |
| Report length | 300-600 word brief | Cheap in tokens, allows iterating within the daily quota |
| Language | Spanish | The user's working language |

`AgentExecutor` is in maintenance mode in LangChain — the official docs recommend LangGraph. It is stable and works, but won't receive further development. This is a conscious tradeoff.

## Architecture

```
Browser (index.html + app.js)
   │  POST /api/chat  (SSE: token, step, step_done, report, error, done)
   ▼
FastAPI (server.py)
   │  astream_events
   ▼
RunnableWithMessageHistory
   └── AgentExecutor (max_iterations=6, max_execution_time=120)
         ├── ChatOpenAI ──► OpenRouter ──► nemotron-3-ultra-550b-a55b:free
         └── tools
              ├── tavily_search(query)      ──► Tavily API
              └── write_report(markdown)    ──► SessionStore
```

### Components

**`config.py`** — Loads and validates environment variables at startup. If `OPENROUTER_API_KEY` or `TAVILY_API_KEY` is missing, the server won't start and says so. Exposes `MODEL_ID` (defaults to `nvidia/nemotron-3-ultra-550b-a55b:free`).

**`llm.py`** — Builds the `ChatOpenAI` client pointed at `https://openrouter.ai/api/v1` with `streaming=True`. The single place where the provider is configured.

**`session.py`** — In-memory store: a `session_id → Session` dictionary. Each `Session` holds an `InMemoryChatMessageHistory` and the current report markdown. No TTL or cleanup: the process dies and everything disappears, which is the intended behavior.

**`tools.py`** — Two tools:

- `tavily_search(query: str) -> str`: wraps `TavilySearch` from `langchain-tavily`. Catches every exception and returns `"Search failed: <reason>"`. In ReAct, a tool failure is an observation for the agent, not a server error.
- `make_write_report(session) -> Tool`: factory that returns a `write_report(markdown: str)` closed over the session. Writes the markdown to `session.report` and returns `"Report updated."` to the agent.

**`agent.py`** — `build_agent(session)` composes the system prompt, `create_tool_calling_agent`, `AgentExecutor`, and `RunnableWithMessageHistory`. Built **per session**, not globally: composing runnables is cheap, and this way `write_report` always writes to the correct session, with no shared state between tabs.

**`server.py`** — FastAPI. Serves static files and exposes the endpoints. Translates `astream_events` events into SSE events.

### The `write_report` tool

The agent publishes the brief **by calling a tool**, not by writing it in its final response. This unambiguously separates the conversation from the artifact: the chat carries the dialogue ("I searched for X, found Y, should I go deeper?") and the right-hand panel only changes when there's a call to `write_report`. No need to parse free text or guess where the report begins.

**Critical rule:** when refining, `write_report` receives the **entire rewritten brief**, never a fragment. The panel is replaced wholesale; sending only "the improved section 2" would erase the rest.

## API contract

| Endpoint | Method | Description |
|---|---|---|
| `/` | GET | Serves `index.html` |
| `/api/chat` | POST | `{session_id, message}` → `StreamingResponse` of `text/event-stream` |
| `/api/report/{session_id}` | GET | Raw markdown of the current report (for the download button) |

`POST` with SSE instead of `EventSource`, because `EventSource` only does GET and sending the message in the query string would force a double round-trip. The client reads the stream with `fetch` + `ReadableStream` and parses SSE by hand.

### SSE events

Each event is a `data: {json}` line.

| `type` | Fields | Effect on the UI |
|---|---|---|
| `token` | `text` | Appends text to the assistant's message |
| `step` | `tool`, `input` | Shows "🔍 Searching: *query*" |
| `step_done` | `tool`, `summary` | Closes the step: "✓ 5 results" |
| `report` | `html`, `markdown` | Replaces the right-hand panel |
| `error` | `message` | Error bubble in the chat |
| `done` | — | Closes the stream |

Showing the steps matters with ReAct: each search is visible as it happens, so research that goes off track is caught instantly instead of at the end.

**The report is not streamed token by token.** It arrives complete in a single `report` event when the agent calls `write_report`. For a one-page brief this is the right call: the panel goes straight from "generating…" to the finished document.

## Interface

Two panels: chat on the left (~40%), brief on the right (~60%). The brief panel has a header with the topic and a "Download .md" button. Empty state: *"Type a topic in the chat to generate a brief."*

`index.html`, `app.js`, and `styles.css` served as static files. No npm, no bundler.

**The markdown is rendered server-side** with `markdown` + `bleach`, and the `report` event carries already-sanitized HTML. This was preferred over vendoring `marked.js`: it avoids third-party JS in the repo, and sanitization is not optional when the content is written by an LLM from uncontrolled web pages.

**Session:** `crypto.randomUUID()` on the client, stored in `sessionStorage`. If the server has restarted, the session no longer exists and a fresh one starts.

**Not implemented:** a remaining-quota indicator — it would require querying OpenRouter's API separately and would still be inaccurate. Instead, the 429 error is reported explicitly.

## System prompt

Defines the report's quality. Rules:

- Role: an analyst who produces 300-600 word briefs in Spanish.
- Search before asserting. Maximum 3 searches per turn.
- Cite with `[n]` and close with a "Sources" section listing the URLs.
- **Always** publish the brief with `write_report`, never in the chat response.
- When refining, rewrite the entire brief.
- Chat responses are brief and don't repeat the report's content.

## Error handling

| Situation | Behavior |
|---|---|
| A missing API key | The server doesn't start; explicit console message |
| 429 for per-minute limit | Retry with backoff (2s, 6s), max 2 times |
| 429 for per-day limit | No retry. `error` event: "You've used up the free tier's 50 daily requests. Wait for the reset or switch `MODEL_ID` to the paid variant." |
| Tavily failure | The tool returns the error as an observation; the agent retries with another query or writes with what it has |
| Iterations exhausted without `write_report` | `error` event explaining it. History is preserved, so the next message ("write the report with what you found") finishes it off without repeating the research |
| Markdown with dangerous HTML | `bleach` sanitizes it before it reaches the browser |
| The client closes the tab | The SSE generator is cancelled with no dangling tasks |

`max_iterations=6` and `max_execution_time=120` bound the worst case to ~6 requests per report, i.e. about 8 complete reports within the daily quota.

## Testing

No test in the default suite touches the network or consumes quota.

- **`test_tools.py`** — `tavily_search` with a mocked client, on success and failure; `write_report` writes to the correct session.
- **`test_agent.py`** — `FakeMessagesListChatModel` from `langchain_core` with scripted tool calls. Verifies the executor searches and then publishes.
- **`test_server.py`** — FastAPI's `TestClient` with the agent mocked. Verifies the exact sequence of SSE events and that `/api/report` returns the markdown.
- **Smoke test** marked `@pytest.mark.live`, with real keys, **excluded by default** in `pytest.ini`. Every run spends real quota.

## File structure

```
agente-reportes/
  app/
    __init__.py
    config.py       # environment variables, validated at startup
    llm.py          # OpenRouter client
    tools.py        # tavily_search + write_report factory
    agent.py         # create_tool_calling_agent + AgentExecutor + prompt
    session.py       # in-memory store
    server.py         # FastAPI: SSE + static files
  static/
    index.html
    app.js
    styles.css
  tests/
    test_tools.py
    test_agent.py
    test_server.py
  .claude/agents/   # 36 Claude Code subagents (dev tooling)
  docs/superpowers/specs/
  .env.example      # OPENROUTER_API_KEY, TAVILY_API_KEY, MODEL_ID
  requirements.txt
  pytest.ini
  README.md
```

## Dependencies

`langchain`, `langchain-openai`, `langchain-tavily`, `fastapi`, `uvicorn`, `python-dotenv`, `markdown`, `bleach`, `pytest`, `pytest-asyncio`, `httpx`.

## Success criteria

1. The user types a topic and gets a cited 300-600 word brief in the right-hand panel.
2. The agent's searches are visible in the chat as they happen.
3. A refinement message updates the full brief without losing sections.
4. The download button delivers the current brief's markdown.
5. Running out of daily quota produces a comprehensible message, not a generic error.
6. The test suite passes without API keys or network access.
