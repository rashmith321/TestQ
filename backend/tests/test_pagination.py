import pytest

from scraper.exceptions import NetworkError
from scraper.pagination_handler import CursorPaginator, LimitProbePaginator, OffsetPaginator

KEY = lambda r: r["id"]  # noqa: E731


def make_pages(total, size):
    data = [{"id": i} for i in range(total)]
    return data, [data[i:i + size] for i in range(0, total, size)]


def test_cursor_multiple_pages_no_loss():
    data, pages = make_pages(95, 20)

    def fetch(cursor):
        i = cursor or 0
        return pages[i], i + 1, i + 1 < len(pages)

    out = CursorPaginator(fetch, KEY).run()
    assert out.records == data and out.batches == 5 and out.complete


def test_cursor_large_volume():
    data, pages = make_pages(5000, 50)
    out = CursorPaginator(lambda c: (pages[c or 0], (c or 0) + 1, (c or 0) + 1 < len(pages)), KEY).run()
    assert len(out.records) == 5000 and out.batches == 100


def test_cursor_overlapping_pages_deduplicated():
    pages = [[{"id": 1}, {"id": 2}], [{"id": 2}, {"id": 3}], [{"id": 4}]]
    out = CursorPaginator(lambda c: (pages[c or 0], (c or 0) + 1, (c or 0) < 2), KEY).run()
    assert [r["id"] for r in out.records] == [1, 2, 3, 4] and out.duplicates_skipped == 1


def test_cursor_loop_guard():
    out = CursorPaginator(lambda c: ([{"id": c}], "same", True), KEY).run()
    assert out.stop_reason == "cursor_loop_detected" and not out.complete


def test_cursor_failure_midway_keeps_partial():
    def fetch(c):
        if c == 2:
            raise NetworkError("boom")
        return [{"id": c or 0}], (c or 0) + 1, True

    out = CursorPaginator(fetch, KEY).run()
    assert len(out.records) == 2 and out.stop_reason == "error_after_partial_data" and not out.complete


def test_cursor_failure_on_first_page_raises():
    with pytest.raises(NetworkError):
        CursorPaginator(lambda c: (_ for _ in ()).throw(NetworkError("down")), KEY).run()


def test_offset_paginator():
    data, _ = make_pages(45, 20)
    out = OffsetPaginator(lambda off, n: data[off:off + n], KEY, page_size=20).run()
    assert out.records == data and out.batches == 3


def test_limit_probe_cap_vs_exhausted():
    data = [{"id": i} for i in range(50)]
    capped = LimitProbePaginator(lambda n: data[:min(n, 10)], KEY, start_limit=10).run()
    assert capped.stop_reason == "server_cap_reached" and capped.detected_cap == 10 and len(capped.records) == 10
    between = LimitProbePaginator(lambda n: data[:min(n, 15)], KEY, start_limit=10).run()
    assert between.stop_reason == "returned_fewer_than_requested" and len(between.records) == 15
    small = LimitProbePaginator(lambda n: data[:min(n, 7)], KEY, start_limit=10).run()
    assert small.stop_reason == "returned_fewer_than_requested" and len(small.records) == 7


def test_limit_probe_keeps_largest_batch():
    data = [{"id": i} for i in range(25)]
    out = LimitProbePaginator(lambda n: data[:min(n, 25)], KEY, start_limit=10).run()
    assert len(out.records) == 25 and out.stop_reason == "returned_fewer_than_requested"
