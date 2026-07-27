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
