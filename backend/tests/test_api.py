import time

from fastapi.testclient import TestClient

from main import create_app
from tests.conftest import FakeLeetCode, make_ac, make_all_from_ac


def wait_for(client, job_id, timeout=10):
    deadline = time.time() + timeout
    while time.time() < deadline:
        body = client.get(f"/api/jobs/{job_id}").json()
        if body["status"] in ("done", "error"):
            return body
        time.sleep(0.05)
    raise AssertionError("job did not finish")


def make_client(settings, fake):
    return TestClient(create_app(settings, client_factory=lambda s: fake))


def test_health(settings):
    with make_client(settings, FakeLeetCode()) as c:
        assert c.get("/api/health").json()["status"] == "ok"


def test_full_flow_analyze_poll_download(settings):
    ac = make_ac(30)
    with make_client(settings, FakeLeetCode(ac=ac, all_status=make_all_from_ac(ac))) as c:
        r = c.post("/api/analyze", json={"profile_url": "https://leetcode.com/u/alice/"})
        assert r.status_code == 202
        job = wait_for(c, r.json()["job_id"])
        assert job["status"] == "done" and job["progress"] == 100
        assert job["result"]["metadata"]["total_activity_records"] == 20
        d = c.get(f"/api/download/{job['download_filename']}")
        assert d.status_code == 200 and d.json()["profile"]["username"] == "alice"
        assert "attachment" in d.headers["content-disposition"]


def test_invalid_url_is_400(settings):
    with make_client(settings, FakeLeetCode()) as c:
        r = c.post("/api/analyze", json={"profile_url": "https://example.com/u/x"})
        assert r.status_code == 400 and r.json()["error"]["code"] == "invalid_url"


def test_profile_not_found_job_error(settings):
    with make_client(settings, FakeLeetCode(user_exists=False)) as c:
        job = wait_for(c, c.post("/api/analyze", json={"profile_url": "leetcode.com/u/ghost"}).json()["job_id"])
        assert job["status"] == "error" and job["error"]["code"] == "profile_not_found"


def test_network_failure_job_error(settings):
    with make_client(settings, FakeLeetCode(fail_ops={"userPublicProfile"})) as c:
        job = wait_for(c, c.post("/api/analyze", json={"profile_url": "leetcode.com/u/alice"}).json()["job_id"])
        assert job["status"] == "error" and job["error"]["code"] == "network_error"


def test_everything_fails_is_reported_failed(settings):
    fake = FakeLeetCode(fail_ops={"skillStats", "recentAcSubmissions", "recentSubmissions"})
    with make_client(settings, fake) as c:
        job = wait_for(c, c.post("/api/analyze", json={"profile_url": "leetcode.com/u/alice"}).json()["job_id"])
        assert job["status"] == "error" and job["error"]["code"] == "analysis_failed"


def test_download_rejects_traversal_and_unknown(settings):
    with make_client(settings, FakeLeetCode()) as c:
        assert c.get("/api/download/..%2Fmain.py").status_code == 404
        assert c.get("/api/download/x_leetcode_data.json").status_code == 404
        assert c.get("/api/jobs/nope").status_code == 404
