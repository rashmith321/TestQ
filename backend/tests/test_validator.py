import pytest

from scraper.exceptions import InvalidProfileURL, ProfileNotFound
from scraper.profile_validator import check_profile_exists, extract_username, validate_profile_url
from tests.conftest import FakeLeetCode


@pytest.mark.parametrize("url,expected", [
    ("https://leetcode.com/u/alice_01/", "alice_01"),
    ("https://leetcode.com/u/alice_01", "alice_01"),
    ("http://www.leetcode.com/u/Bob-Smith/?tab=solutions#x", "Bob-Smith"),
    ("leetcode.com/u/carol.dev/", "carol.dev"),
    ("  https://leetcode.com/dave/  ", "dave"),  # legacy profile URL form
])
def test_valid_urls(url, expected):
    assert extract_username(url) == expected


@pytest.mark.parametrize("url", [
    "", "   ", "https://google.com/u/alice/", "https://leetcode.cn/u/alice/",
    "https://leetcode.com/problems/two-sum/", "https://leetcode.com/u/", "https://leetcode.com/",
    "https://leetcode.com/contest/", "https://leetcode.com/u/bad name/", "https://leetcode.com/u/a/b/",
    "ftp://leetcode.com/u/alice/", "https://leetcode.com/u/%3Cscript%3E/", "https://leetcode.com.evil.io/u/x/",
])
def test_invalid_urls(url):
    with pytest.raises(InvalidProfileURL):
        extract_username(url)


def test_canonical_url():
    assert validate_profile_url("leetcode.com/erin").profile_url == "https://leetcode.com/u/erin/"


def test_profile_not_found():
    with pytest.raises(ProfileNotFound):
        check_profile_exists(FakeLeetCode(user_exists=False), "ghost")


def test_profile_exists_returns_user():
    assert check_profile_exists(FakeLeetCode(), "alice")["username"] == "alice"
