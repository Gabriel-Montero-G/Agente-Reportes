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
