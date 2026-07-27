"""The agent's two tools: web search and report publication."""
from __future__ import annotations

from functools import lru_cache
from typing import Any

from langchain_core.tools import BaseTool, StructuredTool, tool
from langchain_tavily import TavilySearch

from .config import get_settings
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
    return TavilySearch(max_results=MAX_RESULTS, tavily_api_key=get_settings().tavily_api_key)


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
