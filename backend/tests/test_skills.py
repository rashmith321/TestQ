import pytest

from scraper.exceptions import ProfileNotFound
from scraper.skills_scraper import fetch_skills
from services.data_processor import clean_skills
from tests.conftest import FakeLeetCode, load_fixture


def test_three_sections_kept_separate():
    x = fetch_skills(FakeLeetCode(), "alice")
    assert x.status == "completed"
    assert [s["skill_name"] for s in x.sections["fundamentals"]] == ["Array", "String", "Two Pointers", "Sorting"]
    assert [s["skill_name"] for s in x.sections["intermediate"]] == ["Hash Table", "Math", "Depth-First Search"]
    assert [s["skill_name"] for s in x.sections["advanced"]] == ["Dynamic Programming", "Backtracking", "Union Find"]
    for category, items in x.sections.items():
        assert all(i["category"] == category for i in items)
    assert x.sections["advanced"][0]["problems_solved"] == 14
    assert x.sections["advanced"][0]["source_section"] == "Advanced"


def test_missing_and_empty_sections():
    x = fetch_skills(FakeLeetCode(skills=load_fixture("skill_stats_missing.json")), "alice")
    assert x.status == "partial"
    assert x.missing_sections == ["intermediate"]
    assert x.sections["intermediate"] == [] and x.sections["advanced"] == []
    skills, warnings = clean_skills(x.sections)
    assert [s.skill_name for s in skills.fundamentals] == ["Array"]
    assert skills.fundamentals[0].problems_solved == 3  # "3" string normalised
    assert any("no name" in w for w in warnings)


def test_structure_change_then_html_fallback():
    fake = FakeLeetCode(skills={"data": {"matchedUser": {"somethingElse": 1}}},
                        html=load_fixture("profile_page_next_data.html"))
    x = fetch_skills(fake, "alice")
    assert x.source == "html:__NEXT_DATA__"
    assert [s["skill_name"] for s in x.sections["advanced"]] == ["Trie"]
    assert x.errors and "skillStats failed" in x.errors[0]
    assert x.status == "partial"  # fallback used: reported, not hidden


def test_total_failure_reports_failed():
    fake = FakeLeetCode(fail_ops={"skillStats"})
    x = fetch_skills(fake, "alice")
    assert x.status == "failed"
    assert x.sections == {"fundamentals": [], "intermediate": [], "advanced": []}


def test_profile_not_found_propagates():
    with pytest.raises(ProfileNotFound):
        fetch_skills(FakeLeetCode(skills={"data": {"matchedUser": None}}), "ghost")
