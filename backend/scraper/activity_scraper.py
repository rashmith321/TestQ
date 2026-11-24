"""Recent Activity extraction.

Two public, limit-only lists feed the profile's Recent Activity:
  * recentAcSubmissionList - accepted submissions, WITH submission id, no language/status
  * recentSubmissionList   - submissions of any status, WITH status + language, no id
Both are probed with LimitProbePaginator (see pagination_handler.py for why). The results
are merged so each record carries every field LeetCode exposed for it, then difficulty is
looked up per unique problem.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable

from . import queries
from .exceptions import ScraperError, UpstreamStructureChanged
from .pagination_handler import LimitProbePaginator, PaginationOutcome

log = logging.getLogger(__name__)
Progress = Callable[[str], None]


@dataclass
class SourceReport:
    name: str
    status: str  # "completed" | "partial" | "failed"
    records: int = 0
    batches: int = 0
    stop_reason: str | None = None
    detected_cap: int | None = None
    error: str | None = None

    def to_dict(self) -> dict:
        return dict(self.__dict__)


@dataclass
class ActivityExtraction:
    records: list[dict[str, Any]]
    raw: dict[str, Any]
    sources: list[SourceReport]
    difficulties: dict[str, str | None] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def batches(self) -> int:
        return sum(s.batches for s in self.sources)

    @property
    def status(self) -> str:
        if all(s.status == "failed" for s in self.sources):
            return "failed"
        if self.errors or any(s.status != "completed" for s in self.sources):
            return "partial"
        return "completed"


def _ts_int(value: Any) -> int | None:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _list_field(data: dict, key: str, operation: str) -> list[dict]:
    if key not in data:
        raise UpstreamStructureChanged(f"'{key}' is missing from the {operation} response.")
    value = data[key]
    if value is None:
        return []
    if not isinstance(value, list):
        raise UpstreamStructureChanged(f"'{key}' in the {operation} response is not a list.")
    return [v for v in value if isinstance(v, dict)]


def _ac_key(r: dict) -> Any:
    return ("id", str(r["id"])) if r.get("id") not in (None, "") else ("slug_ts", r.get("titleSlug"), str(r.get("timestamp")))


def _all_key(r: dict) -> Any:
    # No id in this list. Exact duplicates share slug + time + status + language;
    # repeated attempts at the same problem differ in timestamp and are kept.
    return (r.get("titleSlug"), str(r.get("timestamp")), r.get("statusDisplay"), r.get("lang"))


def _probe(name: str, fetch: Callable[[int], list], key, settings, progress: Progress | None) -> tuple[PaginationOutcome | None, SourceReport]:
    def on_batch(n: int, count: int) -> None:
        if progress:
            progress(f"{name}: batch {n} returned {count} records")

    paginator = LimitProbePaginator(
        fetch, key,
        start_limit=settings.activity_start_limit,
        max_limit=settings.activity_max_limit,
        max_batches=settings.activity_max_batches,
        on_batch=on_batch,
    )
    try:
        outcome = paginator.run()
    except ScraperError as exc:
        return None, SourceReport(name, "failed", error=exc.message)
    status = "completed" if outcome.complete else "partial"
    return outcome, SourceReport(
        name, status, len(outcome.records), outcome.batches, outcome.stop_reason, outcome.detected_cap,
        "; ".join(outcome.errors) or None,
    )


def merge_activity(ac: list[dict], all_status: list[dict]) -> list[dict]:
    """Combine both lists into one newest-first list without merging distinct submissions."""
    ac_by_slug_ts: dict[tuple, dict] = {}
    for r in ac:
        ac_by_slug_ts.setdefault((r.get("titleSlug"), str(r.get("timestamp"))), r)
    used: set[tuple] = set()
    merged: list[dict] = []

    for r in all_status:
        rec = {
            "title": r.get("title"),
            "title_slug": r.get("titleSlug"),
            "timestamp": r.get("timestamp"),
            "status": r.get("statusDisplay"),
            "lang": r.get("lang"),
            "submission_id": None,
            "sources": ["recentSubmissionList"],
        }
        k = (r.get("titleSlug"), str(r.get("timestamp")))
        if r.get("statusDisplay") == "Accepted" and k in ac_by_slug_ts and k not in used:
            rec["submission_id"] = ac_by_slug_ts[k].get("id")
            rec["sources"].append("recentAcSubmissionList")
            used.add(k)
        merged.append(rec)

    for r in ac:
        k = (r.get("titleSlug"), str(r.get("timestamp")))
        if k in used:
            continue
        used.add(k)
        merged.append(
            {
                "title": r.get("title"),
                "title_slug": r.get("titleSlug"),
                "timestamp": r.get("timestamp"),
                "status": "Accepted",  # the list only contains accepted submissions
                "lang": None,
                "submission_id": r.get("id"),
                "sources": ["recentAcSubmissionList"],
            }
        )

    order = {id(rec): i for i, rec in enumerate(merged)}
    merged.sort(key=lambda rec: (-(_ts_int(rec["timestamp"]) or -1), order[id(rec)]))
    return merged


def fetch_difficulties(
    client, slugs: list[str], batch_size: int, progress: Progress | None = None
) -> tuple[dict[str, str | None], list[str], list[str]]:
    """Return (slug -> difficulty, warnings, errors). Request failures are errors;
    a problem LeetCode returns no difficulty for is a warning."""
    difficulties: dict[str, str | None] = {}
    warnings: list[str] = []
    errors: list[str] = []
    unique = [s for s in dict.fromkeys(slugs) if s]
    for start in range(0, len(unique), max(1, batch_size)):
        chunk = unique[start:start + batch_size]
        query, variables, alias_map = queries.build_difficulty_query(chunk)
        try:
            result = client.graphql(query, variables, "questionDifficulties")
        except ScraperError as exc:
            errors.append(f"Difficulty lookup failed for {len(chunk)} problems: {exc.message}")
            difficulties.update({s: None for s in chunk})
            continue
        for alias, slug in alias_map.items():
            node = (result.data or {}).get(alias)
            difficulties[slug] = node.get("difficulty") if isinstance(node, dict) else None
            if difficulties[slug] is None:
                warnings.append(f"Difficulty not available for '{slug}'.")
        if progress:
            progress(f"Difficulty looked up for {min(start + batch_size, len(unique))}/{len(unique)} problems")
    return difficulties, warnings, errors


def fetch_recent_activity(client, username: str, settings, progress: Progress | None = None) -> ActivityExtraction:
    def fetch_ac(limit: int) -> list[dict]:
        res = client.graphql(queries.RECENT_AC_SUBMISSIONS, {"username": username, "limit": limit}, "recentAcSubmissions")
        return _list_field(res.data, "recentAcSubmissionList", "recentAcSubmissions")

    def fetch_all(limit: int) -> list[dict]:
        res = client.graphql(queries.RECENT_SUBMISSIONS, {"username": username, "limit": limit}, "recentSubmissions")
        return _list_field(res.data, "recentSubmissionList", "recentSubmissions")

    ac_out, ac_report = _probe("recentAcSubmissionList", fetch_ac, _ac_key, settings, progress)
    all_out, all_report = _probe("recentSubmissionList", fetch_all, _all_key, settings, progress)

    ac = ac_out.records if ac_out else []
    all_status = all_out.records if all_out else []
    raw = {"recentAcSubmissionList": ac, "recentSubmissionList": all_status}
    errors = [f"{r.name}: {r.error}" for r in (ac_report, all_report) if r.error]
    warnings: list[str] = []
    if all_out is None and ac_out is not None:
        warnings.append("Submissions of other statuses and the language of each submission were not available; "
                        "only accepted submissions were extracted.")

    records = merge_activity(ac, all_status)
    difficulties: dict[str, str | None] = {}
    if records:
        if progress:
            progress("Looking up problem difficulty")
        difficulties, diff_warnings, diff_errors = fetch_difficulties(
            client, [r["title_slug"] for r in records], settings.difficulty_batch_size, progress
        )
        warnings += diff_warnings
        errors += diff_errors
    return ActivityExtraction(records, raw, [ac_report, all_report], difficulties, errors, warnings)
