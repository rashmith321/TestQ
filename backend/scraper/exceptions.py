"""Typed errors so the API can map each failure to a clear status and message."""
from __future__ import annotations


class ScraperError(Exception):
    """Base class for all extraction errors."""

    code = "scraper_error"
    http_status = 502

    def __init__(self, message: str, *, details: dict | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}

    def to_dict(self) -> dict:
        return {"code": self.code, "message": self.message, "details": self.details}


class InvalidProfileURL(ScraperError):
    code = "invalid_url"
    http_status = 400


class ProfileNotFound(ScraperError):
    code = "profile_not_found"
    http_status = 404


class AccessBlocked(ScraperError):
    """LeetCode answered with a non-JSON page (bot check, login wall) or HTTP 403."""

    code = "access_blocked"
    http_status = 503


class RateLimited(ScraperError):
    code = "rate_limited"
    http_status = 429


class NetworkError(ScraperError):
    code = "network_error"
    http_status = 504


class UpstreamStructureChanged(ScraperError):
    """The response was valid JSON but not in the shape this scraper expects."""

    code = "structure_changed"
    http_status = 502


class GraphQLQueryError(ScraperError):
    """The GraphQL server returned errors and no usable data for a query."""

    code = "graphql_error"
    http_status = 502
