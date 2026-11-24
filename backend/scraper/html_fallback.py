"""Fallback extraction from the profile page HTML.

The profile page is a Next.js app. When server-side rendered, it may embed its initial
data in <script id="__NEXT_DATA__">. Whether that blob contains skills or recent
submissions depends on LeetCode's rendering choices and is NOT guaranteed, so this module
only searches for known keys and reports clearly when they are absent.
"""
from __future__ import annotations

import json
from typing import Any, Iterator

from bs4 import BeautifulSoup


def extract_next_data(html: str) -> dict | None:
    soup = BeautifulSoup(html, "html.parser")
    tag = soup.find("script", id="__NEXT_DATA__")
    if not tag or not tag.string:
        return None
    try:
        data = json.loads(tag.string)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def iter_key(obj: Any, key: str) -> Iterator[Any]:
    """Depth-first search for every value stored under `key` anywhere in a JSON tree."""
    stack = [obj]
    while stack:
        current = stack.pop()
        if isinstance(current, dict):
            for k, v in current.items():
                if k == key:
                    yield v
                if isinstance(v, (dict, list)):
                    stack.append(v)
        elif isinstance(current, list):
            stack.extend(reversed(current))


def find_first(obj: Any, key: str) -> Any:
    for value in iter_key(obj, key):
        if value is not None:
            return value
    return None
