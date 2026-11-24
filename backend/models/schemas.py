"""Pydantic models: API request/response bodies and the exported JSON document."""
from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

SkillCategory = Literal["fundamentals", "intermediate", "advanced"]
SectionStatus = Literal["completed", "partial", "failed"]
OverallStatus = Literal["completed", "partially_completed", "failed"]


class AnalyzeRequest(BaseModel):
    profile_url: str = Field(..., min_length=1, max_length=300, examples=["https://leetcode.com/u/username/"])


class ProfileInfo(BaseModel):
    username: str
    profile_url: str
    real_name: Optional[str] = None


class SkillItem(BaseModel):
    skill_name: str
    skill_slug: Optional[str] = None
    category: SkillCategory
    source_section: str
    problems_solved: Optional[int] = None


class Skills(BaseModel):
    fundamentals: list[SkillItem] = Field(default_factory=list)
    intermediate: list[SkillItem] = Field(default_factory=list)
    advanced: list[SkillItem] = Field(default_factory=list)


class ActivityRecord(BaseModel):
    problem_name: Optional[str] = None
    problem_slug: Optional[str] = None
    problem_url: Optional[str] = None
    submission_id: Optional[str] = None
    submission_date: Optional[str] = None  # ISO 8601, UTC
    submission_timestamp: Optional[int] = None  # Unix seconds, as given by LeetCode
    status: Optional[str] = None
    language: Optional[str] = None
    difficulty: Optional[Literal["Easy", "Medium", "Hard"]] = None
    sources: list[str] = Field(default_factory=list)


class SectionReport(BaseModel):
    status: SectionStatus
    source: Optional[str] = None
    records: int = 0
    missing: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class Metadata(BaseModel):
    total_skills: int
    skills_by_category: dict[str, int]
    total_activity_records: int
    pages_processed: int
    scraping_status: OverallStatus
    scraped_at: str
    sections: dict[str, SectionReport]
    activity_sources: list[dict[str, Any]] = Field(default_factory=list)
    history_coverage: str
    field_coverage: dict[str, int] = Field(default_factory=dict)  # records where each field is non-null
    data_source: str
    requests_made: int = 0
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class AnalysisResult(BaseModel):
    profile: ProfileInfo
    skills: Skills
    recent_activity: list[ActivityRecord] = Field(default_factory=list)
    metadata: Metadata


class JobAccepted(BaseModel):
    job_id: str
    username: str
    status_url: str


class JobView(BaseModel):
    job_id: str
    username: str
    status: Literal["queued", "running", "done", "error"]
    progress: int = 0
    stage: str = ""
    log: list[str] = Field(default_factory=list)
    result: Optional[AnalysisResult] = None
    download_filename: Optional[str] = None
    error: Optional[dict[str, Any]] = None
