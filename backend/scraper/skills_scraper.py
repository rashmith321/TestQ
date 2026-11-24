"""Skills extraction: the Fundamental / Intermediate / Advanced card of a profile."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from . import queries
from .exceptions import ProfileNotFound, ScraperError, UpstreamStructureChanged
from .html_fallback import extract_next_data, find_first

log = logging.getLogger(__name__)

# LeetCode key -> (our JSON key, label shown on the profile page)
SECTIONS: dict[str, tuple[str, str]] = {
    "fundamental": ("fundamentals", "Fundamental"),
    "intermediate": ("intermediate", "Intermediate"),
    "advanced": ("advanced", "Advanced"),
}


@dataclass
class SkillsExtraction:
    sections: dict[str, list[dict[str, Any]]]
    raw: dict[str, Any] | None
    source: str | None
    missing_sections: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def status(self) -> str:
        if self.raw is None:
            return "failed"
        return "partial" if (self.missing_sections or self.errors) else "completed"


def _empty_sections() -> dict[str, list]:
    return {json_key: [] for json_key, _ in SECTIONS.values()}


def parse_tag_problem_counts(tag_counts: Any) -> tuple[dict[str, list[dict]], list[str], list[str]]:
    """Turn LeetCode's tagProblemCounts object into three separate lists.

    Returns (sections, missing_sections, errors). Sections are never mixed: every item
    keeps the section it came from.
    """
    if not isinstance(tag_counts, dict):
        raise UpstreamStructureChanged("Skills data ('tagProblemCounts') is missing or not an object.")

    sections, missing, errors = _empty_sections(), [], []
    for lc_key, (json_key, label) in SECTIONS.items():
        items = tag_counts.get(lc_key)
        if items is None:
            missing.append(json_key)
            continue
        if not isinstance(items, list):
            errors.append(f"Section '{label}' is not a list; skipped.")
            missing.append(json_key)
            continue
        for item in items:
            if not isinstance(item, dict):
                errors.append(f"Skipped a malformed item in '{label}'.")
                continue
            sections[json_key].append(
                {
                    "skill_name": item.get("tagName"),
                    "skill_slug": item.get("tagSlug"),
                    "category": json_key,
                    "source_section": label,
                    "problems_solved": item.get("problemsSolved"),
                }
            )
    return sections, missing, errors


def fetch_skills(client, username: str, *, allow_html_fallback: bool = True) -> SkillsExtraction:
    """Extract skills via GraphQL; fall back to the page's embedded data if that fails."""
    try:
        result = client.graphql(queries.SKILL_STATS, {"username": username}, "skillStats")
        user = (result.data or {}).get("matchedUser")
        if user is None:
            raise ProfileNotFound(f"No public LeetCode profile named '{username}' was found.")
        tag_counts = user.get("tagProblemCounts")
        sections, missing, errors = parse_tag_problem_counts(tag_counts)
        errors += [f"GraphQL warning: {m}" for m in result.error_messages]
        return SkillsExtraction(sections, {"tagProblemCounts": tag_counts}, "graphql:skillStats", missing, errors)
    except ProfileNotFound:
        raise
    except ScraperError as exc:
        log.warning("Skills via GraphQL failed for %s: %s", username, exc.message)
        primary_error = f"GraphQL skillStats failed: {exc.message}"

    if allow_html_fallback and hasattr(client, "get_profile_html"):
        try:
            next_data = extract_next_data(client.get_profile_html(username))
            tag_counts = find_first(next_data, "tagProblemCounts") if next_data else None
            if tag_counts is not None:
                sections, missing, errors = parse_tag_problem_counts(tag_counts)
                return SkillsExtraction(
                    sections, {"tagProblemCounts": tag_counts}, "html:__NEXT_DATA__", missing,
                    [primary_error, *errors],
                )
            primary_error += " The profile HTML did not contain skills data either."
        except ScraperError as exc:
            primary_error += f" HTML fallback failed: {exc.message}"

    return SkillsExtraction(_empty_sections(), None, None, list(_empty_sections()), [primary_error])
