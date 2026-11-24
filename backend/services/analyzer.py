"""Orchestrates one profile analysis: validate -> skills -> activity -> clean -> JSON."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Callable

from config import Settings
from models.schemas import AnalysisResult, Metadata, ProfileInfo, SectionReport
from scraper.activity_scraper import fetch_recent_activity
from scraper.exceptions import AccessBlocked, ScraperError
from scraper.leetcode_client import LeetCodeClient
from scraper.profile_validator import ValidatedProfile, check_profile_exists
from scraper.skills_scraper import fetch_skills
from services.data_processor import clean_activity, clean_skills
from services.json_generator import write_document

log = logging.getLogger(__name__)
ProgressFn = Callable[[int, str], None]

DATA_SOURCE_NOTE = (
    "LeetCode's internal GraphQL endpoint https://leetcode.com/graphql/ (undocumented, used by the public "
    "profile page; not an official API and subject to change), with a profile-page HTML fallback for skills."
)


class AnalysisFailed(ScraperError):
    code = "analysis_failed"
    http_status = 502


def default_client_factory(settings: Settings):
    return LeetCodeClient(
        timeout=settings.request_timeout,
        max_retries=settings.max_retries,
        min_interval=settings.min_request_interval,
    )


def _history_note(activity) -> str:
    caps = [s.detected_cap for s in activity.sources if s.detected_cap]
    cap_text = f" LeetCode returned at most {max(caps)} records per list for this profile." if caps else ""
    return (
        "These are only the submissions LeetCode shows publicly in Recent Activity. LeetCode does "
        "not paginate this feed publicly and caps its length, so this is NOT the user's complete submission "
        f"history.{cap_text} The full history is only visible to the account owner when logged in."
    )


def _overall(skills_status: str, activity_status: str) -> str:
    if skills_status == "completed" and activity_status == "completed":
        return "completed"
    if skills_status == "failed" and activity_status == "failed":
        return "failed"
    return "partially_completed"


def run_analysis(
    profile: ValidatedProfile,
    settings: Settings,
    progress: ProgressFn = lambda pct, msg: None,
    client_factory: Callable[[Settings], object] = default_client_factory,
) -> tuple[AnalysisResult, str]:
    client = client_factory(settings)
    progress(5, f"Checking that {profile.username} has a public profile")
    try:
        user = check_profile_exists(client, profile.username)
    except AccessBlocked:
        if not settings.browser_fallback:
            raise
        progress(8, "Direct requests were refused; retrying in a browser (Playwright)")
        from scraper.browser_fallback import PlaywrightClient

        client = PlaywrightClient(profile.username)
        user = check_profile_exists(client, profile.username)

    username = user.get("username") or profile.username
    try:
        progress(20, "Reading skills (Fundamental, Intermediate, Advanced)")
        skills_x = fetch_skills(client, username)

        progress(40, "Reading Recent Activity")
        step = {"pct": 40}

        def activity_progress(message: str) -> None:
            step["pct"] = min(step["pct"] + 5, 85)
            progress(step["pct"], message)

        activity_x = fetch_recent_activity(client, username, settings, activity_progress)
    finally:
        close = getattr(client, "close", None)
        if callable(close):
            close()

    progress(90, "Cleaning and validating the data")
    skills, skill_warnings = clean_skills(skills_x.sections)
    activity, activity_warnings = clean_activity(activity_x.records, activity_x.difficulties)

    status = _overall(skills_x.status, activity_x.status)
    if status == "failed":
        raise AnalysisFailed(
            "Neither skills nor recent activity could be extracted.",
            details={"errors": skills_x.errors + activity_x.errors},
        )

    fields = ["submission_id", "submission_date", "status", "language", "difficulty", "problem_url"]
    metadata = Metadata(
        total_skills=len(skills.fundamentals) + len(skills.intermediate) + len(skills.advanced),
        skills_by_category={k: len(getattr(skills, k)) for k in ("fundamentals", "intermediate", "advanced")},
        total_activity_records=len(activity),
        pages_processed=activity_x.batches,
        scraping_status=status,
        scraped_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        sections={
            "skills": SectionReport(
                status=skills_x.status, source=skills_x.source,
                records=sum(len(v) for v in skills_x.sections.values()),
                missing=skills_x.missing_sections, errors=skills_x.errors,
            ),
            "recent_activity": SectionReport(
                status=activity_x.status, source="graphql:recentSubmissionList+recentAcSubmissionList",
                records=len(activity), errors=activity_x.errors,
            ),
        },
        activity_sources=[s.to_dict() for s in activity_x.sources],
        history_coverage=_history_note(activity_x),
        field_coverage={f: sum(1 for r in activity if getattr(r, f) is not None) for f in fields},
        data_source=DATA_SOURCE_NOTE,
        requests_made=getattr(client, "request_count", 0),
        warnings=skill_warnings + activity_x.warnings + activity_warnings,
        errors=skills_x.errors + activity_x.errors,
    )
    document = AnalysisResult(
        profile=ProfileInfo(
            username=username,
            profile_url=f"https://leetcode.com/u/{username}/",
            real_name=((user.get("profile") or {}).get("realName") or None),
        ),
        skills=skills,
        recent_activity=activity,
        metadata=metadata,
    )

    progress(95, "Writing the JSON file")
    raw = {"skills": skills_x.raw, "recent_activity": activity_x.raw} if settings.save_raw else None
    filename = write_document(document, settings.output_dir, raw)
    progress(100, f"Done: {status.replace('_', ' ')}")
    return document, filename
