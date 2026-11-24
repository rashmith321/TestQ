"""URL validation, username extraction and profile existence check."""
from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlparse

from . import queries
from .exceptions import InvalidProfileURL, ProfileNotFound

ALLOWED_HOSTS = {"leetcode.com", "www.leetcode.com"}
# LeetCode usernames: letters, digits, underscore, hyphen and dot in practice.
USERNAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,39}$")
# First path segments that are site sections, not usernames (legacy /<username>/ form).
RESERVED_PATHS = {
    "u", "problems", "problemset", "contest", "discuss", "explore", "study-plan", "studyplan",
    "accounts", "subscribe", "store", "interview", "assessment", "submissions", "tag", "list",
    "company", "profile", "notifications", "playground", "support", "jobs", "graphql", "api",
    "points", "progress", "favorites", "problem-list", "about", "terms", "privacy", "region",
}


@dataclass(frozen=True)
class ValidatedProfile:
    username: str
    profile_url: str


def canonical_profile_url(username: str) -> str:
    return f"https://leetcode.com/u/{username}/"


def extract_username(raw_url: str) -> str:
    """Return the username from a LeetCode profile URL or raise InvalidProfileURL."""
    if not isinstance(raw_url, str) or not raw_url.strip():
        raise InvalidProfileURL("Enter a LeetCode profile URL, for example https://leetcode.com/u/username/.")

    candidate = raw_url.strip()
    if "://" not in candidate:
        candidate = "https://" + candidate
    parsed = urlparse(candidate)

    if parsed.scheme not in {"http", "https"}:
        raise InvalidProfileURL("The URL must start with https://.")
    host = (parsed.hostname or "").lower()
    if host in {"leetcode.cn", "www.leetcode.cn"}:
        raise InvalidProfileURL(
            "leetcode.cn profiles use a different site and API and are not supported; use a leetcode.com profile."
        )
    if host not in ALLOWED_HOSTS:
        raise InvalidProfileURL(f"'{parsed.hostname or raw_url}' is not leetcode.com.")

    segments = [s for s in parsed.path.split("/") if s]
    if len(segments) == 2 and segments[0].lower() == "u":
        username = segments[1]
    elif len(segments) == 1 and segments[0].lower() not in RESERVED_PATHS:
        username = segments[0]  # legacy https://leetcode.com/<username>/ form
    else:
        raise InvalidProfileURL(
            "This is not a profile URL. Profile URLs look like https://leetcode.com/u/username/."
        )

    if not USERNAME_RE.match(username):
        raise InvalidProfileURL(f"'{username}' is not a valid LeetCode username.")
    return username


def validate_profile_url(raw_url: str) -> ValidatedProfile:
    username = extract_username(raw_url)
    return ValidatedProfile(username=username, profile_url=canonical_profile_url(username))


def check_profile_exists(client, username: str) -> dict:
    """Ask LeetCode for the public profile; raise ProfileNotFound when it does not exist.

    Returns the matchedUser object (username as LeetCode spells it, plus public profile fields).
    """
    result = client.graphql(queries.USER_PROFILE, {"username": username}, "userPublicProfile")
    user = (result.data or {}).get("matchedUser")
    if not user:
        raise ProfileNotFound(f"No public LeetCode profile named '{username}' was found.")
    return user
