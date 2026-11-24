"""HTTP client for LeetCode's public GraphQL endpoint.

Behaves like a browser visiting a public profile: it sends the same kind of request the
profile page sends, throttles itself, honours Retry-After on HTTP 429 and gives up
cleanly on 403 / bot-check pages. It never logs in, never solves CAPTCHAs and never
rotates identities to dodge limits.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable

import requests

from .exceptions import (
    AccessBlocked,
    GraphQLQueryError,
    NetworkError,
    RateLimited,
    UpstreamStructureChanged,
)

log = logging.getLogger(__name__)

BASE_URL = "https://leetcode.com"
GRAPHQL_URL = f"{BASE_URL}/graphql/"
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36 LeetCodeProfileAnalyzer/1.0"
    ),
    "Accept": "application/json",
    "Accept-Language": "en-US,en;q=0.9",
}
MAX_RETRY_AFTER_SECONDS = 30.0


@dataclass
class GraphQLResult:
    data: dict[str, Any]
    errors: list[dict[str, Any]] = field(default_factory=list)

    @property
    def error_messages(self) -> list[str]:
        return [str(e.get("message", e)) for e in self.errors]


class LeetCodeClient:
    def __init__(
        self,
        *,
        timeout: float = 15.0,
        max_retries: int = 3,
        min_interval: float = 0.8,
        session: requests.Session | Any | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
        warm_up: bool = True,
    ):
        self.timeout = timeout
        self.max_retries = max_retries
        self.min_interval = min_interval
        self.session = session or requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)
        self._sleep = sleep
        self._clock = clock
        self._last_request_at: float | None = None
        self._warm_up_pending = warm_up
        self.request_count = 0

    # -- internals ---------------------------------------------------------
    def _throttle(self) -> None:
        if self._last_request_at is not None:
            wait = self.min_interval - (self._clock() - self._last_request_at)
            if wait > 0:
                self._sleep(wait)
        self._last_request_at = self._clock()

    def _warm_up(self) -> None:
        """Load the home page once, as a browser would, so the session has a csrftoken cookie."""
        self._warm_up_pending = False
        try:
            self._throttle()
            self.session.get(BASE_URL + "/", timeout=self.timeout, headers={"Accept": "text/html"})
            self.request_count += 1
        except requests.RequestException as exc:  # not fatal: public queries usually work without it
            log.info("Warm-up request failed (continuing): %s", exc)

    def _headers(self, referer: str | None) -> dict[str, str]:
        headers = {"Content-Type": "application/json", "Referer": referer or BASE_URL + "/", "Origin": BASE_URL}
        cookies = getattr(self.session, "cookies", None)
        token = cookies.get("csrftoken") if cookies is not None else None
        if token:
            headers["x-csrftoken"] = token
        return headers

    @staticmethod
    def _retry_after(response) -> float | None:
        value = response.headers.get("Retry-After") if getattr(response, "headers", None) else None
        try:
            return float(value) if value is not None else None
        except ValueError:
            return None

    # -- public API ----------------------------------------------------------
    def graphql(
        self,
        query: str,
        variables: dict[str, Any],
        operation_name: str,
        *,
        referer: str | None = None,
    ) -> GraphQLResult:
        """POST a GraphQL query. Retries timeouts, 5xx and 429; raises typed errors otherwise."""
        if self._warm_up_pending:
            self._warm_up()

        payload = {"query": query, "variables": variables, "operationName": operation_name}
        last_error: Exception | None = None

        for attempt in range(self.max_retries + 1):
            backoff = 1.5 * (2**attempt)
            self._throttle()
            try:
                response = self.session.post(
                    GRAPHQL_URL, json=payload, headers=self._headers(referer), timeout=self.timeout
                )
                self.request_count += 1
            except requests.Timeout:
                last_error = NetworkError(f"LeetCode did not answer within {self.timeout:.0f}s ({operation_name}).")
            except requests.ConnectionError as exc:
                last_error = NetworkError(f"Could not connect to leetcode.com: {exc.__class__.__name__}.")
            else:
                status = response.status_code
                if status == 429:
                    last_error = RateLimited(
                        "LeetCode is rate-limiting requests. Wait a few minutes and try again.",
                        details={"operation": operation_name},
                    )
                    if attempt < self.max_retries:
                        delay = min(self._retry_after(response) or backoff, MAX_RETRY_AFTER_SECONDS)
                        log.warning("429 on %s, retrying in %.1fs", operation_name, delay)
                        self._sleep(delay)
                        continue
                    raise last_error
                if status in (401, 403):
                    raise AccessBlocked(
                        f"LeetCode refused the request (HTTP {status}). The data may need a login or the "
                        "request was flagged as automated; this tool does not work around that.",
                        details={"operation": operation_name, "http_status": status},
                    )
                if status >= 500:
                    last_error = NetworkError(f"LeetCode returned HTTP {status} for {operation_name}.")
                else:
                    return self._parse(response, operation_name)

            if attempt < self.max_retries:
                log.warning("%s (attempt %d), retrying in %.1fs", last_error, attempt + 1, backoff)
                self._sleep(backoff)

        assert last_error is not None
        raise last_error

    @staticmethod
    def _parse(response, operation_name: str) -> GraphQLResult:
        try:
            body = response.json()
        except ValueError:
            raise AccessBlocked(
                "LeetCode answered with a web page instead of data (often a browser check). "
                "Try again later; this tool does not bypass such checks.",
                details={"operation": operation_name, "http_status": response.status_code},
            ) from None
        if not isinstance(body, dict):
            raise UpstreamStructureChanged(f"Unexpected response shape for {operation_name}.")
        data = body.get("data")
        errors = body.get("errors") or []
        if data is None:
            messages = "; ".join(str(e.get("message", e)) for e in errors) or f"HTTP {response.status_code}"
            raise GraphQLQueryError(
                f"LeetCode rejected the {operation_name} query: {messages}",
                details={"operation": operation_name, "errors": errors},
            )
        if not isinstance(data, dict):
            raise UpstreamStructureChanged(f"'data' for {operation_name} is not an object.")
        return GraphQLResult(data=data, errors=errors)

    def get_profile_html(self, username: str) -> str:
        """Fetch the public profile page HTML (used only by the HTML fallback parser)."""
        self._throttle()
        try:
            response = self.session.get(
                f"{BASE_URL}/u/{username}/", timeout=self.timeout, headers={"Accept": "text/html"}
            )
            self.request_count += 1
        except requests.RequestException as exc:
            raise NetworkError(f"Could not load the profile page: {exc.__class__.__name__}.") from exc
        if response.status_code == 404:
            from .exceptions import ProfileNotFound

            raise ProfileNotFound(f"No public LeetCode profile named '{username}' was found.")
        if response.status_code in (401, 403, 429):
            raise AccessBlocked(f"LeetCode refused the profile page (HTTP {response.status_code}).")
        return response.text
