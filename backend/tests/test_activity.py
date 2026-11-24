from scraper.activity_scraper import fetch_recent_activity, merge_activity
from services.data_processor import clean_activity
from tests.conftest import BASE_TS, FakeLeetCode, make_ac, make_all_from_ac


def run(fake, settings):
    x = fetch_recent_activity(fake, "alice", settings)
    records, warnings = clean_activity(x.records, x.difficulties)
    return x, records, warnings


def test_server_cap_is_detected_and_probing_stops(settings):
    ac = make_ac(50)
    fake = FakeLeetCode(ac=ac, all_status=make_all_from_ac(ac), cap=20)
    x, records, _ = run(fake, settings)
    assert fake.limits["recentAcSubmissions"] == [20, 40]  # grew once, saw no new data, stopped
    ac_src = next(s for s in x.sources if s.name == "recentAcSubmissionList")
    assert ac_src.stop_reason == "server_cap_reached" and ac_src.detected_cap == 20
    assert len(records) == 20 and x.status == "completed"
    assert x.batches == 4  # 2 per list


def test_fewer_records_than_limit(settings):
    ac = make_ac(7)
    fake = FakeLeetCode(ac=ac, all_status=make_all_from_ac(ac))
    x, records, _ = run(fake, settings)
    assert fake.limits["recentAcSubmissions"] == [20]
    assert len(records) == 7


def test_larger_cap_collects_everything_exposed(settings):
    ac = make_ac(130)
    fake = FakeLeetCode(ac=ac, all_status=make_all_from_ac(ac), cap=1000)
    x, records, _ = run(fake, settings)
    assert fake.limits["recentAcSubmissions"] == [20, 40, 80, 100]
    assert len(records) == 100
    assert next(s for s in x.sources if s.name == "recentAcSubmissionList").stop_reason == "max_limit_reached"
    assert x.status == "partial"  # stopped by our own safety limit, so not claimed complete


def test_repeated_submissions_of_same_problem_are_kept(settings):
    ac = make_ac(20, repeat_every=5)  # two-sum appears 4 times at different times
    fake = FakeLeetCode(ac=ac, all_status=make_all_from_ac(ac, wrong_every=5))
    _, records, _ = run(fake, settings)
    two_sum = [r for r in records if r.problem_slug == "two-sum"]
    assert len(two_sum) == 8  # 4 accepted + 4 wrong answers, none merged
    assert {r.status for r in two_sum} == {"Accepted", "Wrong Answer"}
    assert len({r.submission_id for r in two_sum if r.status == "Accepted"}) == 4


def test_order_is_newest_first(settings):
    ac = make_ac(20)
    fake = FakeLeetCode(ac=ac, all_status=make_all_from_ac(ac, wrong_every=3))
    _, records, _ = run(fake, settings)
    stamps = [r.submission_timestamp for r in records]
    assert stamps == sorted(stamps, reverse=True)


def test_fields_merged_from_both_lists(settings):
    ac = make_ac(3)
    fake = FakeLeetCode(ac=ac, all_status=make_all_from_ac(ac), difficulties={"problem-0": "Easy", "problem-1": "Hard"})
    _, records, _ = run(fake, settings)
    r0 = records[0]
    assert r0.submission_id == ac[0]["id"] and r0.language == "python3" and r0.status == "Accepted"
    assert r0.difficulty == "Easy" and r0.problem_url == "https://leetcode.com/problems/problem-0/"
    assert r0.submission_date.endswith("Z")
    assert set(r0.sources) == {"recentSubmissionList", "recentAcSubmissionList"}


def test_all_status_list_unavailable_falls_back_to_accepted_only(settings):
    ac = make_ac(5)
    fake = FakeLeetCode(ac=ac, all_status=None)
    x, records, warnings = run(fake, settings)
    assert len(records) == 5 and all(r.status == "Accepted" and r.language is None for r in records)
    assert x.status == "partial"
    assert any("only accepted" in w for w in x.warnings)
    assert any("Language not exposed" in w for w in warnings)


def test_both_lists_fail(settings):
    fake = FakeLeetCode(fail_ops={"recentAcSubmissions", "recentSubmissions"})
    x, records, _ = run(fake, settings)
    assert x.status == "failed" and records == []


def test_pagination_failure_after_first_batch_keeps_data(settings):
    ac = make_ac(50)
    fake = FakeLeetCode(ac=ac, all_status=make_all_from_ac(ac), fail_on_call={"recentAcSubmissions": 2})
    x, records, _ = run(fake, settings)
    src = next(s for s in x.sources if s.name == "recentAcSubmissionList")
    assert src.stop_reason == "error_after_partial_data" and src.records == 20
    assert x.status == "partial" and len(records) == 20


def test_difficulty_missing_and_failed(settings):
    ac = make_ac(15)
    fake = FakeLeetCode(ac=ac, all_status=make_all_from_ac(ac), difficulties={"problem-3": "MISSING"},
                        fail_on_call={"questionDifficulties": 2})
    settings2 = settings.__class__(**{**settings.__dict__, "difficulty_batch_size": 10})
    x, records, _ = run(fake, settings2)
    by_slug = {r.problem_slug: r for r in records}
    assert by_slug["problem-3"].difficulty is None
    assert by_slug["problem-12"].difficulty is None  # second batch failed
    assert by_slug["problem-0"].difficulty == "Medium"
    assert x.status == "partial" and any("Difficulty lookup failed" in e for e in x.errors)


def test_exact_duplicates_removed_but_not_distinct_ones():
    rec = {"title": "A", "titleSlug": "a", "timestamp": str(BASE_TS), "statusDisplay": "Wrong Answer", "lang": "java"}
    merged = merge_activity([], [rec, dict(rec), dict(rec, lang="cpp")])
    records, warnings = clean_activity(merged, {})
    assert len(records) == 2
    assert any("Exact duplicate" in w for w in warnings)


def test_empty_activity(settings):
    x, records, _ = run(FakeLeetCode(ac=[], all_status=[]), settings)
    assert records == [] and x.status == "completed"
