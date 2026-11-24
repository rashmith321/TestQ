"""Cleaning and normalisation of raw extraction output."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from models.schemas import ActivityRecord, SkillItem, Skills

DIFFICULTIES = {"easy": "Easy", "medium": "Medium", "hard": "Hard"}


def _clean_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _to_int(value: Any) -> int | None:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def timestamp_to_iso(ts: Any) -> str | None:
    seconds = _to_int(ts)
    if seconds is None or seconds < 0:
        return None
    if seconds > 10**11:  # milliseconds, just in case the API ever switches
        seconds //= 1000
    return datetime.fromtimestamp(seconds, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def clean_skills(sections: dict[str, list[dict]]) -> tuple[Skills, list[str]]:
    warnings: list[str] = []
    cleaned: dict[str, list[SkillItem]] = {"fundamentals": [], "intermediate": [], "advanced": []}
    for category in cleaned:
        seen: set[str] = set()
        for item in sections.get(category, []) or []:
            name = _clean_str(item.get("skill_name"))
            if not name:
                warnings.append(f"Dropped a {category} skill with no name.")
                continue
            key = (_clean_str(item.get("skill_slug")) or name).lower()
            if key in seen:
                warnings.append(f"Duplicate skill '{name}' in {category} removed.")
                continue
            seen.add(key)
            cleaned[category].append(
                SkillItem(
                    skill_name=name,
                    skill_slug=_clean_str(item.get("skill_slug")),
                    category=category,
                    source_section=item.get("source_section") or category.title(),
                    problems_solved=_to_int(item.get("problems_solved")),
                )
            )
    return Skills(**cleaned), warnings


def activity_key(record: ActivityRecord) -> tuple:
    """Identity of a submission: its id when known, otherwise problem + time + status + language."""
    if record.submission_id:
        return ("id", record.submission_id)
    return ("composite", record.problem_slug, record.submission_timestamp, record.status, record.language)


def clean_activity(records: list[dict], difficulties: dict[str, str | None]) -> tuple[list[ActivityRecord], list[str]]:
    warnings: list[str] = []
    out: list[ActivityRecord] = []
    seen: set[tuple] = set()
    for raw in records:
        slug = _clean_str(raw.get("title_slug"))
        title = _clean_str(raw.get("title"))
        if not slug and not title:
            warnings.append("Dropped an activity record with neither a problem name nor a slug.")
            continue
        difficulty = DIFFICULTIES.get(str(difficulties.get(slug) or "").lower()) if slug else None
        record = ActivityRecord(
            problem_name=title,
            problem_slug=slug,
            problem_url=f"https://leetcode.com/problems/{slug}/" if slug else None,
            submission_id=_clean_str(raw.get("submission_id")),
            submission_date=timestamp_to_iso(raw.get("timestamp")),
            submission_timestamp=_to_int(raw.get("timestamp")),
            status=_clean_str(raw.get("status")),
            language=_clean_str(raw.get("lang")),
            difficulty=difficulty,
            sources=list(raw.get("sources") or []),
        )
        if record.submission_date is None:
            warnings.append(f"Submission time missing or invalid for '{title or slug}'.")
        key = activity_key(record)
        if key in seen:
            warnings.append(f"Exact duplicate of a '{title or slug}' submission removed.")
            continue
        seen.add(key)
        out.append(record)
    missing_lang = sum(1 for r in out if r.language is None)
    if out and missing_lang:
        warnings.append(f"Language not exposed for {missing_lang} of {len(out)} records.")
    return out, warnings
