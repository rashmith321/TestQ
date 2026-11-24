import json

from scraper.profile_validator import validate_profile_url
from services.analyzer import run_analysis
from services.json_generator import resolve_download, safe_filename
from tests.conftest import FakeLeetCode, make_ac, make_all_from_ac


def analyse(fake, settings, url="https://leetcode.com/u/alice/"):
    return run_analysis(validate_profile_url(url), settings, client_factory=lambda s: fake)


def test_json_file_valid_utf8_and_structured(settings):
    ac = make_ac(25)
    doc, filename = analyse(FakeLeetCode(ac=ac, all_status=make_all_from_ac(ac, wrong_every=4)), settings)
    path = settings.output_dir / filename
    text = path.read_text(encoding="utf-8")
    data = json.loads(text)
    assert filename == "alice_leetcode_data.json"
    assert set(data) == {"profile", "skills", "recent_activity", "metadata"}
    assert set(data["skills"]) == {"fundamentals", "intermediate", "advanced"}
    assert "Ünïcode" in text  # ensure_ascii=False keeps UTF-8 readable
    assert text.startswith("{\n  ")  # indented
    m = data["metadata"]
    assert m["total_skills"] == 10 and m["skills_by_category"] == {"fundamentals": 4, "intermediate": 3, "advanced": 3}
    # Both lists are capped at 20: 20 from the all-status list (16 accepted + 4 wrong answers)
    # plus 4 older accepted submissions that only the accepted list still shows.
    assert m["total_activity_records"] == len(data["recent_activity"]) == 24
    assert m["scraping_status"] == "completed"
    assert "NOT the user's complete submission history" in m["history_coverage"]
    expected_keys = {"problem_name", "problem_url", "submission_id", "submission_date", "status", "language", "difficulty"}
    assert expected_keys <= set(data["recent_activity"][0])
    wrong = next(r for r in data["recent_activity"] if r["status"] == "Wrong Answer")
    assert wrong["submission_id"] is None  # not exposed -> null, never invented
    assert (settings.output_dir / "raw" / "alice_raw.json").exists()


def test_empty_arrays_preserved(settings):
    fake = FakeLeetCode(skills={"data": {"matchedUser": {"tagProblemCounts": {"fundamental": [], "intermediate": [], "advanced": []}}}},
                        ac=[], all_status=[])
    doc, filename = analyse(fake, settings)
    data = json.loads((settings.output_dir / filename).read_text(encoding="utf-8"))
    assert data["skills"] == {"fundamentals": [], "intermediate": [], "advanced": []}
    assert data["recent_activity"] == []


def test_partial_status_when_a_section_fails(settings):
    fake = FakeLeetCode(fail_ops={"skillStats"}, ac=make_ac(3), all_status=make_all_from_ac(make_ac(3)))
    doc, _ = analyse(fake, settings)
    assert doc.metadata.scraping_status == "partially_completed"
    assert doc.metadata.sections["skills"].status == "failed"
    assert doc.metadata.errors


def test_safe_filename_and_download_guard(settings, tmp_path):
    assert safe_filename("a/../b c") == "a_.._b_c_leetcode_data.json"
    analyse(FakeLeetCode(ac=[], all_status=[]), settings)
    assert resolve_download(settings.output_dir, "alice_leetcode_data.json") is not None
    assert resolve_download(settings.output_dir, "../config.py") is None
    assert resolve_download(settings.output_dir, "nobody_leetcode_data.json") is None
