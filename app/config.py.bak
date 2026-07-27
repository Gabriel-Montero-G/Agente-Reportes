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
