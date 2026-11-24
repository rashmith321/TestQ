"""Check LeetCode's live data sources for one public profile, and optionally save fixtures.

Run this on your own machine (it needs internet access to leetcode.com):

    python scripts/inspect_leetcode.py <username>            # report only
    python scripts/inspect_leetcode.py <username> --save     # also save responses to tests/fixtures/live/

It reports, for each query the scraper depends on, whether it answered, which fields came
back, and how many records LeetCode returns for growing limits (the Recent Activity cap).
It also checks whether the profile HTML embeds skills data for the HTML fallback.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scraper import queries  # noqa: E402
from scraper.exceptions import ScraperError  # noqa: E402
from scraper.html_fallback import extract_next_data, find_first  # noqa: E402
from scraper.leetcode_client import LeetCodeClient  # noqa: E402


def show(title: str, ok: bool, detail: str) -> None:
    print(f"[{'OK ' if ok else 'FAIL'}] {title}: {detail}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("username")
    parser.add_argument("--save", action="store_true")
    args = parser.parse_args()
    client = LeetCodeClient(min_interval=1.0)
    saved: dict[str, object] = {}

    def run(name, query, variables, op):
        try:
            res = client.graphql(query, variables, op)
            saved[name] = {"data": res.data, "errors": res.errors}
            return res
        except ScraperError as exc:
            show(name, False, f"{exc.code}: {exc.message}")
            return None

    res = run("profile", queries.USER_PROFILE, {"username": args.username}, "userPublicProfile")
    if res:
        show("profile", bool(res.data.get("matchedUser")), json.dumps(res.data.get("matchedUser"))[:200])

    res = run("skills", queries.SKILL_STATS, {"username": args.username}, "skillStats")
    if res:
        counts = ((res.data.get("matchedUser") or {}).get("tagProblemCounts")) or {}
        show("skills", bool(counts), ", ".join(f"{k}={len(v or [])}" for k, v in counts.items()) or "no tagProblemCounts")

    for name, query, op, key in (
        ("recent_ac", queries.RECENT_AC_SUBMISSIONS, "recentAcSubmissions", "recentAcSubmissionList"),
        ("recent_all", queries.RECENT_SUBMISSIONS, "recentSubmissions", "recentSubmissionList"),
    ):
        sizes = []
        for limit in (10, 20, 50, 100):
            res = run(f"{name}_limit{limit}", query, {"username": args.username, "limit": limit}, op)
            if res is None:
                break
            items = res.data.get(key) or []
            sizes.append(f"limit {limit} -> {len(items)}")
            if items and limit == 10:
                print(f"       fields: {sorted(items[0])}")
        if sizes:
            show(name, True, "; ".join(sizes))

    try:
        html = client.get_profile_html(args.username)
        nd = extract_next_data(html)
        has = find_first(nd, "tagProblemCounts") is not None if nd else False
        show("html_fallback", bool(nd), f"__NEXT_DATA__ {'found' if nd else 'absent'}; skills inside: {has}")
    except ScraperError as exc:
        show("html_fallback", False, exc.message)

    print(f"\nRequests made: {client.request_count}")
    if args.save:
        out = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "live"
        out.mkdir(parents=True, exist_ok=True)
        (out / f"{args.username}.json").write_text(json.dumps(saved, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Saved responses to {out / (args.username + '.json')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
