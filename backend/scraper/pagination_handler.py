"""Pagination strategies for activity-style lists.

What LeetCode actually exposes publicly (as of this project's writing):
`recentAcSubmissionList` and `recentSubmissionList` take only a `limit` argument. There
is no page number, offset or cursor, and the server silently caps how many records it
returns. `LimitProbePaginator` is the strategy used for those: it asks for growing
batches and stops as soon as a larger request brings nothing new, which is how the cap is
detected at run time instead of being hard-coded.

`CursorPaginator` and `OffsetPaginator` are complete, tested strategies for sources that
do paginate (for example, a future LeetCode change or another site). They are not used
against LeetCode's public profile today because LeetCode offers no such public endpoint;
its full submission history requires being logged in as that user.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Hashable

log = logging.getLogger(__name__)

Record = dict[str, Any]
KeyFn = Callable[[Record], Hashable]


@dataclass
class PaginationOutcome:
    records: list[Record]
    batches: int
    stop_reason: str
    errors: list[str] = field(default_factory=list)
    duplicates_skipped: int = 0
    detected_cap: int | None = None

    @property
    def complete(self) -> bool:
        """True when pagination ended normally (not because of an error or a safety limit)."""
        return not self.errors and self.stop_reason in {
            "returned_fewer_than_requested",
            "server_cap_reached",
            "no_more_pages",
        }


class _Deduper:
    """Drops records whose key was already seen; keeps first occurrence and order."""

    def __init__(self, key: KeyFn):
        self.key = key
        self.seen: set[Hashable] = set()
        self.records: list[Record] = []
        self.skipped = 0

    def add_all(self, batch: list[Record]) -> int:
        added = 0
        for record in batch:
            k = self.key(record)
            if k in self.seen:
                self.skipped += 1
                continue
            self.seen.add(k)
            self.records.append(record)
            added += 1
        return added


class LimitProbePaginator:
    """For list endpoints that accept only `limit` and always return the newest N records."""

    def __init__(
        self,
        fetch: Callable[[int], list[Record]],
        key: KeyFn,
        *,
        start_limit: int = 20,
        growth: int = 2,
        max_limit: int = 100,
        max_batches: int = 4,
        on_batch: Callable[[int, int], None] | None = None,
    ):
        if start_limit < 1 or growth < 2:
            raise ValueError("start_limit must be >= 1 and growth >= 2")
        self.fetch, self.key = fetch, key
        self.start_limit, self.growth = start_limit, growth
        self.max_limit, self.max_batches = max(max_limit, start_limit), max_batches
        self.on_batch = on_batch

    def run(self) -> PaginationOutcome:
        limit, batches = self.start_limit, 0
        best: list[Record] = []
        errors: list[str] = []
        while True:
            try:
                batch = list(self.fetch(limit) or [])
            except Exception as exc:
                if batches == 0:
                    raise  # nothing collected: let the caller report the failure
                errors.append(f"Batch with limit={limit} failed: {exc}")
                return self._outcome(best, batches, "error_after_partial_data", errors)
            batches += 1
            if self.on_batch:
                self.on_batch(batches, len(batch))

            if len(batch) < limit:
                # The server gave back fewer than asked. Either the user has no more
                # records, or this is the server cap. If a previous smaller request
                # returned the same count, it is the cap.
                if best and len(batch) <= len(best):
                    return self._outcome(best, batches, "server_cap_reached", errors, cap=len(best))
                return self._outcome(batch, batches, "returned_fewer_than_requested", errors)

            best = batch
            if limit >= self.max_limit:
                return self._outcome(best, batches, "max_limit_reached", errors)
            if batches >= self.max_batches:
                return self._outcome(best, batches, "max_batches_reached", errors)
            limit = min(limit * self.growth, self.max_limit)

    def _outcome(self, records, batches, reason, errors, cap=None) -> PaginationOutcome:
        deduper = _Deduper(self.key)
        deduper.add_all(records)
        return PaginationOutcome(deduper.records, batches, reason, errors, deduper.skipped, cap)


class CursorPaginator:
    """fetch(cursor) -> (records, next_cursor, has_next). Starts with cursor=None."""

    def __init__(self, fetch: Callable[[Any], tuple[list[Record], Any, bool]], key: KeyFn, *, max_pages: int = 500,
                 on_batch: Callable[[int, int], None] | None = None):
        self.fetch, self.key, self.max_pages, self.on_batch = fetch, key, max_pages, on_batch

    def run(self) -> PaginationOutcome:
        deduper, cursor, pages, errors = _Deduper(self.key), None, 0, []
        seen_cursors: set[Any] = set()
        while pages < self.max_pages:
            try:
                records, next_cursor, has_next = self.fetch(cursor)
            except Exception as exc:
                if pages == 0:
                    raise
                errors.append(f"Page {pages + 1} failed: {exc}")
                return PaginationOutcome(deduper.records, pages, "error_after_partial_data", errors, deduper.skipped)
            pages += 1
            added = deduper.add_all(list(records or []))
            if self.on_batch:
                self.on_batch(pages, added)
            if not has_next or next_cursor is None:
                return PaginationOutcome(deduper.records, pages, "no_more_pages", errors, deduper.skipped)
            if next_cursor in seen_cursors or next_cursor == cursor:
                errors.append(f"Cursor {next_cursor!r} repeated; stopped to avoid an infinite loop.")
                return PaginationOutcome(deduper.records, pages, "cursor_loop_detected", errors, deduper.skipped)
            seen_cursors.add(next_cursor)
            cursor = next_cursor
        return PaginationOutcome(deduper.records, pages, "max_pages_reached", errors, deduper.skipped)


class OffsetPaginator:
    """fetch(offset, page_size) -> records. Stops on a short or empty page."""

    def __init__(self, fetch: Callable[[int, int], list[Record]], key: KeyFn, *, page_size: int = 20,
                 max_pages: int = 500, on_batch: Callable[[int, int], None] | None = None):
        self.fetch, self.key, self.page_size, self.max_pages, self.on_batch = fetch, key, page_size, max_pages, on_batch

    def run(self) -> PaginationOutcome:
        deduper, pages, errors = _Deduper(self.key), 0, []
        while pages < self.max_pages:
            try:
                batch = list(self.fetch(pages * self.page_size, self.page_size) or [])
            except Exception as exc:
                if pages == 0:
                    raise
                errors.append(f"Page {pages + 1} failed: {exc}")
                return PaginationOutcome(deduper.records, pages, "error_after_partial_data", errors, deduper.skipped)
            pages += 1
            deduper.add_all(batch)
            if self.on_batch:
                self.on_batch(pages, len(batch))
            if len(batch) < self.page_size:
                return PaginationOutcome(deduper.records, pages, "no_more_pages", errors, deduper.skipped)
        return PaginationOutcome(deduper.records, pages, "max_pages_reached", errors, deduper.skipped)
