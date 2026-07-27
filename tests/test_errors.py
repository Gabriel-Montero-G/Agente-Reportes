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
