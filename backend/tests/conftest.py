"""Shared fixtures. Everything here is offline: a FakeLeetCode stands in for the server."""
from __future__ import annotations

import json
import sys
from dataclasses import replace
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from config import Settings  # noqa: E402
from scraper.exceptions import GraphQLQueryError, NetworkError  # noqa: E402
from scraper.leetcode_client import GraphQLResult  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures"
BASE_TS = 1_763_000_000  # arbitrary fixed Unix time for synthetic fixtures


def load_fixture(name: str):
    path = FIXTURES / name
    return json.loads(path.read_text(encoding="utf-8")) if path.suffix == ".json" else path.read_text(encoding="utf-8")


def make_ac(n: int, *, start_id: int = 1000, repeat_every: int = 0) -> list[dict]:
    """n accepted submissions, newest first; optionally repeat one problem every k items."""
    out = []
    for i in range(n):
        slug = "two-sum" if repeat_every and i % repeat_every == 0 else f"problem-{i}"
        out.append({"id": str(start_id + n - i), "title": slug.replace("-", " ").title(), "titleSlug": slug,
                    "timestamp": str(BASE_TS - i * 600)})
    return out


def make_all_from_ac(ac: list[dict], *, wrong_every: int = 0) -> list[dict]:
    """All-status list consistent with `ac`, with optional Wrong Answer attempts interleaved."""
    out = []
    for i, r in enumerate(ac):
        out.append({"title": r["title"], "titleSlug": r["titleSlug"], "timestamp": r["timestamp"],
                    "statusDisplay": "Accepted", "lang": "python3"})
        if wrong_every and i % wrong_every == 0:
            out.append({"title": r["title"], "titleSlug": r["titleSlug"], "timestamp": str(int(r["timestamp"]) - 60),
                        "statusDisplay": "Wrong Answer", "lang": "cpp"})
    return out


class FakeLeetCode:
    """Routes GraphQL operations to canned data and enforces a server-side cap like LeetCode does."""

    def __init__(self, *, user_exists=True, skills=None, ac=None, all_status=None, cap=20,
                 fail_ops=(), difficulties=None, fail_on_call: dict | None = None, html: str | None = None):
        self.user_exists = user_exists
        self.skills = skills if skills is not None else load_fixture("skill_stats_full.json")
        self.ac = ac if ac is not None else []
        self.all_status = all_status
        self.cap = cap
        self.fail_ops = set(fail_ops)
        self.difficulties = difficulties or {}
        self.fail_on_call = fail_on_call or {}  # op -> call number (1-based) that raises
        self.calls: dict[str, int] = {}
        self.limits: dict[str, list[int]] = {}
        self.html = html
        self.request_count = 0

    def graphql(self, query, variables, operation_name, **_):
        self.request_count += 1
        n = self.calls[operation_name] = self.calls.get(operation_name, 0) + 1
        if operation_name in self.fail_ops:
            raise NetworkError(f"simulated failure in {operation_name}")
        if self.fail_on_call.get(operation_name) == n:
            raise NetworkError(f"simulated failure on call {n} of {operation_name}")
        if operation_name == "userPublicProfile":
            user = {"username": variables["username"], "profile": {"realName": "Fixture Ünïcode"}} if self.user_exists else None
            return GraphQLResult({"matchedUser": user})
        if operation_name == "skillStats":
            return GraphQLResult(self.skills["data"])
        if operation_name in ("recentAcSubmissions", "recentSubmissions"):
            limit = variables["limit"]
            self.limits.setdefault(operation_name, []).append(limit)
            if operation_name == "recentSubmissions":
                if self.all_status is None:
                    raise GraphQLQueryError("Cannot query field recentSubmissionList (simulated)")
                return GraphQLResult({"recentSubmissionList": self.all_status[: min(limit, self.cap)]})
            return GraphQLResult({"recentAcSubmissionList": self.ac[: min(limit, self.cap)]})
        if operation_name == "questionDifficulties":
            data = {}
            for var, slug in variables.items():
                alias = "q" + var[1:]
                diff = self.difficulties.get(slug, "Medium")
                data[alias] = None if diff == "MISSING" else {"titleSlug": slug, "difficulty": diff}
            return GraphQLResult(data)
        raise AssertionError(f"unexpected operation {operation_name}")

    def get_profile_html(self, username):
        self.request_count += 1
        if self.html is None:
            raise NetworkError("no html")
        return self.html


@pytest.fixture
def settings(tmp_path) -> Settings:
    return replace(Settings(), output_dir=tmp_path / "output", min_request_interval=0.0,
                   activity_start_limit=20, activity_max_limit=100, activity_max_batches=4)
