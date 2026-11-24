import pytest
import requests

from scraper.exceptions import AccessBlocked, GraphQLQueryError, NetworkError, RateLimited
from scraper.leetcode_client import LeetCodeClient


class Resp:
    def __init__(self, status=200, body=None, text=None, headers=None):
        self.status_code, self._body, self.text, self.headers = status, body, text or "", headers or {}

    def json(self):
        if self._body is None:
            raise ValueError("not json")
        return self._body


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.headers, self.cookies, self.posts = {}, {"csrftoken": "tok"}, []

    def post(self, url, json=None, headers=None, timeout=None):
        self.posts.append((url, json, headers))
        r = self.responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return r

    def get(self, *a, **k):
        return Resp(200, text="<html></html>")


def client(responses):
    sleeps = []
    c = LeetCodeClient(session=FakeSession(responses), sleep=sleeps.append, min_interval=0, max_retries=2)
    return c, sleeps


def test_success_sends_expected_request():
    c, _ = client([Resp(200, {"data": {"matchedUser": {"username": "a"}}})])
    res = c.graphql("query", {"username": "a"}, "op")
    assert res.data["matchedUser"]["username"] == "a"
    url, payload, headers = c.session.posts[0]
    assert url == "https://leetcode.com/graphql/" and payload["operationName"] == "op"
    assert headers["x-csrftoken"] == "tok" and headers["Content-Type"] == "application/json"


def test_429_retries_with_retry_after_then_succeeds():
    c, sleeps = client([Resp(429, headers={"Retry-After": "3"}), Resp(200, {"data": {}})])
    assert c.graphql("q", {}, "op").data == {}
    assert 3.0 in sleeps


def test_429_exhausted_raises_rate_limited():
    c, _ = client([Resp(429)] * 3)
    with pytest.raises(RateLimited):
        c.graphql("q", {}, "op")


def test_403_is_not_retried():
    c, _ = client([Resp(403)])
    with pytest.raises(AccessBlocked):
        c.graphql("q", {}, "op")


def test_html_challenge_page_is_access_blocked():
    c, _ = client([Resp(200, None, text="<html>Just a moment...</html>")])
    with pytest.raises(AccessBlocked):
        c.graphql("q", {}, "op")


def test_timeouts_retry_then_network_error():
    c, sleeps = client([requests.Timeout(), requests.ConnectionError(), requests.Timeout()])
    with pytest.raises(NetworkError):
        c.graphql("q", {}, "op")
    assert len(sleeps) == 2


def test_server_error_then_success():
    c, _ = client([Resp(502), Resp(200, {"data": {"x": 1}})])
    assert c.graphql("q", {}, "op").data == {"x": 1}


def test_graphql_errors_without_data():
    c, _ = client([Resp(400, {"data": None, "errors": [{"message": "Cannot query field"}]})])
    with pytest.raises(GraphQLQueryError, match="Cannot query field"):
        c.graphql("q", {}, "op")


def test_partial_graphql_errors_are_kept():
    c, _ = client([Resp(200, {"data": {"a": 1}, "errors": [{"message": "minor"}]})])
    assert c.graphql("q", {}, "op").error_messages == ["minor"]
