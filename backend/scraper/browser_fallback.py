"""Optional Playwright-based client with the same interface as LeetCodeClient.

Enabled with LCPA_BROWSER_FALLBACK=1 and only tried when the plain HTTP client gets a
non-JSON page or HTTP 403. It opens the public profile in a real browser and runs the
same GraphQL queries from inside that page. If LeetCode shows a challenge, login wall or
CAPTCHA, it stops and reports it: it never tries to solve or evade one.

Install: pip install playwright && python -m playwright install chromium
"""
from __future__ import annotations

import logging
from typing import Any

from .exceptions import AccessBlocked, GraphQLQueryError, NetworkError
from .leetcode_client import BASE_URL, GraphQLResult

log = logging.getLogger(__name__)
CHALLENGE_MARKERS = ("cf-challenge", "challenge-platform", "Just a moment", "captcha")


class PlaywrightClient:
    def __init__(self, username: str, timeout: float = 30.0):
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:  # pragma: no cover - depends on optional install
            raise AccessBlocked("Browser fallback is enabled but Playwright is not installed.") from exc
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(headless=True)
        self._page = self._browser.new_page()
        self.request_count = 0
        try:
            self._page.goto(f"{BASE_URL}/u/{username}/", timeout=timeout * 1000, wait_until="domcontentloaded")
        except Exception as exc:  # pragma: no cover - network dependent
            self.close()
            raise NetworkError(f"Browser could not open the profile page: {exc}") from exc
        html = self._page.content()
        if any(marker.lower() in html.lower() for marker in CHALLENGE_MARKERS):
            self.close()
            raise AccessBlocked("LeetCode showed a browser check. This tool does not bypass it; try later.")

    def graphql(self, query: str, variables: dict[str, Any], operation_name: str, **_: Any) -> GraphQLResult:
        body = self._page.evaluate(
            """async ({query, variables, operationName}) => {
                const r = await fetch('/graphql/', {method: 'POST', credentials: 'same-origin',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({query, variables, operationName})});
                const text = await r.text();
                try { return {status: r.status, json: JSON.parse(text)}; }
                catch (e) { return {status: r.status, json: null}; }
            }""",
            {"query": query, "variables": variables, "operationName": operation_name},
        )
        self.request_count += 1
        payload = body.get("json")
        if payload is None:
            raise AccessBlocked(f"Browser request for {operation_name} returned a non-JSON page (HTTP {body.get('status')}).")
        if payload.get("data") is None:
            raise GraphQLQueryError(f"LeetCode rejected the {operation_name} query in the browser.", details=payload)
        return GraphQLResult(data=payload["data"], errors=payload.get("errors") or [])

    def close(self) -> None:
        browser, pw = getattr(self, "_browser", None), getattr(self, "_pw", None)
        try:
            if browser is not None:
                browser.close()
        finally:
            if pw is not None:
                pw.stop()
