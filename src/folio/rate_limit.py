"""Rate-limit handling: ``Retry-After`` parsing and the crawl's back-off rule."""

from __future__ import annotations

import math
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

DEFAULT_BACKOFF_SECONDS = 30.0
DEFAULT_MAX_BACKOFF_SECONDS = 300.0
DEFAULT_ADAPTIVE_STEP_SECONDS = 1.0


class RateLimitedError(Exception):
    """A page answered HTTP 429 (or 503 with ``Retry-After``); nothing was saved."""

    def __init__(self, url: str, status: int, retry_after: float | None) -> None:
        super().__init__(f"HTTP {status} (rate limited): {url}")
        self.url = url
        self.status = status
        self.retry_after = retry_after


def parse_retry_after(
    value: str | None, *, now: datetime | None = None
) -> float | None:
    """Seconds to wait from a ``Retry-After`` header: delta-seconds or an HTTP-date
    (never negative). ``None`` when absent or unparseable."""
    if value is None:
        return None
    text = value.strip()
    if not text:
        return None
    try:
        seconds = float(text)
    except ValueError:
        try:
            when = parsedate_to_datetime(text)
        except (TypeError, ValueError, IndexError):
            return None
        if when.tzinfo is None:
            when = when.replace(tzinfo=UTC)
        seconds = (when - (now or datetime.now(UTC))).total_seconds()
    if not math.isfinite(seconds):
        return None
    return max(0.0, seconds)


def is_rate_limited(status: int | None, retry_after: float | None) -> bool:
    """HTTP 429, or 503 that says when to come back."""
    return status == 429 or (status == 503 and retry_after is not None)


def backoff_seconds(
    consecutive: int,
    retry_after: float | None,
    *,
    base: float = DEFAULT_BACKOFF_SECONDS,
    cap: float = DEFAULT_MAX_BACKOFF_SECONDS,
) -> float:
    """Pause for the ``consecutive``-th cool-down in a row (1-based): the server's
    ``Retry-After`` when given, else ``base`` doubling per cool-down; at most
    ``cap``."""
    if retry_after is not None:
        return min(retry_after, cap)
    exponent = max(0, consecutive - 1)
    if exponent > 60:  # 2**60 * base dwarfs any cap
        return cap
    return min(base * float(2**exponent), cap)
