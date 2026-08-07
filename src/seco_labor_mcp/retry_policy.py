"""Shared retry policy for both HTTP paths in this package.

`server.py::_fetch_text_cached` and `uvg.py::_fetch_bytes` each carried their
own copy of the same ladder. That is the mistake this module exists to undo, one
scale down: the portfolio-wide defect these functions inherited came from a
template that was copied into eleven servers, and inside this package the same
code was copied twice. Two copies drift, and a drifted retry is invisible —
nothing fails, one path is just less patient than the other.

Adopted from the mcp-data-source-probe reference template (repaired
2026-08-07). Three questions: *what* is retried, *how fast*, and *how long*. The
first stays with each call site (their non-retryable statuses differ — `uvg.py`
treats a 404 on `Ts27.pdf` as an answer); this module settles the other two.
"""

from __future__ import annotations

import random
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

import httpx

# Adopted from the mcp-data-source-probe reference template (repaired
# 2026-08-07). Three questions: *what* is retried, *how fast*, and *how long*.
# The first is settled in the retry loop (4xx except 429 fails fast); these
# settle the other two.

RETRY_BASE_DELAY = 2.0  # ladder before jitter: 2, 4, 8

# Ceiling on the WHOLE call — every attempt and every wait together. An attempt
# count is not a bound: four attempts against an upstream that takes 30s to time
# out is two minutes inside one tool call, and the number never says so. The
# anchor is measured, not guessed: the Python MCP SDK ships
# MCP_DEFAULT_TIMEOUT = 30.0, so 25s leaves headroom for framing and parsing.
RETRY_TOTAL_BUDGET = 25.0

# Ceiling for a single wait. Bounds the exponential ladder, and bounds a
# `Retry-After` the source may send but we are not obliged to sit through.
RETRY_MAX_DELAY = 20.0

# Jitter spread. Without it every client that hit the same outage retries in
# lockstep, and the load returns as a wave exactly when the source recovers —
# the retry storm extends the outage it was meant to bridge.
RETRY_JITTER_SPREAD = 0.5  # exponential delays land in [0.5x, 1.5x]

# On a `Retry-After`, deliberately one-sided: the source said when to come back,
# so coming back later is fine and coming back earlier is not.
RETRY_AFTER_JITTER = 0.25  # lands in [1.0x, 1.25x]

# Statuses that carry a meaningful `Retry-After` (RFC 9110 section 10.2.3).
RETRY_AFTER_STATUSES = frozenset({429, 503})


def parse_retry_after(resp: httpx.Response | None) -> float | None:
    """Seconds to wait per the response's ``Retry-After``, or ``None``.

    RFC 9110 section 10.2.3 allows two forms — delta-seconds (``120``) and an
    HTTP-date (``Wed, 21 Oct 2026 07:28:00 GMT``). Both appear in the wild, so
    both are read. Anything unparseable yields ``None`` and the caller falls
    back to its own curve: a malformed header must not become a crash on the
    error path, which is the one path already going badly.
    """
    if resp is None or resp.status_code not in RETRY_AFTER_STATUSES:
        return None
    raw = (resp.headers.get("retry-after") or "").strip()
    if not raw:
        return None
    if raw.isdigit():
        return float(raw)
    try:
        when = parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        return None
    if when is None:
        return None
    if when.tzinfo is None:  # RFC 9110 dates are GMT; a naive one means UTC
        when = when.replace(tzinfo=UTC)
    return max(0.0, (when - datetime.now(UTC)).total_seconds())


def compute_delay(attempt: int, last_error: Exception | None) -> float:
    """Seconds to wait before ``attempt`` (1-based for the first retry).

    The source's own answer beats our guess: a ``Retry-After`` on a 429 or 503
    wins over the exponential curve. Everything is spread, then capped.

    The cap wraps the jitter and not the other way round. ``min(cap, base) *
    jitter`` and ``min(cap, base * jitter)`` both contain a cap and a jitter;
    only the second is bounded — a value capped at 20s and then multiplied by
    up to 1.5 lands at 30s, and the constant would claim a ceiling it does not
    hold.
    """
    hinted = parse_retry_after(getattr(last_error, "response", None))
    if hinted is not None:
        return min(
            hinted * (1.0 + random.random() * RETRY_AFTER_JITTER),
            RETRY_MAX_DELAY,
        )
    return min(
        RETRY_BASE_DELAY
        * 2 ** (attempt - 1)
        * (1.0 - RETRY_JITTER_SPREAD + random.random() * 2 * RETRY_JITTER_SPREAD),
        RETRY_MAX_DELAY,
    )
