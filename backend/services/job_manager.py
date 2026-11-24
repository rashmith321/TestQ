"""In-memory background jobs with progress, so the UI can poll while scraping runs."""
from __future__ import annotations

import logging
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable

from scraper.exceptions import ScraperError

log = logging.getLogger(__name__)
MAX_JOBS_KEPT = 200


class JobManager:
    def __init__(self, max_workers: int = 2):
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="scrape")
        self._jobs: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

    def submit(self, username: str, work: Callable[[Callable[[int, str], None]], tuple[Any, str]]) -> str:
        job_id = uuid.uuid4().hex
        with self._lock:
            if len(self._jobs) >= MAX_JOBS_KEPT:  # drop the oldest finished jobs
                for old in [k for k, v in self._jobs.items() if v["status"] in ("done", "error")][:50]:
                    del self._jobs[old]
            self._jobs[job_id] = {
                "job_id": job_id, "username": username, "status": "queued", "progress": 0,
                "stage": "Waiting to start", "log": [], "result": None, "download_filename": None, "error": None,
            }
        self._executor.submit(self._run, job_id, work)
        return job_id

    def _update(self, job_id: str, **fields: Any) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            if "stage" in fields and fields["stage"]:
                job["log"].append(fields["stage"])
                job["log"] = job["log"][-50:]
            job.update(fields)

    def _run(self, job_id: str, work) -> None:
        self._update(job_id, status="running", stage="Starting")

        def progress(pct: int, message: str) -> None:
            self._update(job_id, progress=max(0, min(100, int(pct))), stage=message)

        try:
            result, filename = work(progress)
            self._update(job_id, status="done", progress=100, result=result, download_filename=filename)
        except ScraperError as exc:
            log.warning("Job %s failed: %s", job_id, exc.message)
            self._update(job_id, status="error", stage="Failed", error=exc.to_dict())
        except Exception as exc:  # unexpected bug: report without leaking internals
            log.exception("Job %s crashed", job_id)
            self._update(job_id, status="error", stage="Failed",
                         error={"code": "internal_error", "message": f"Unexpected error: {exc.__class__.__name__}", "details": {}})

    def get(self, job_id: str) -> dict[str, Any] | None:
        with self._lock:
            job = self._jobs.get(job_id)
            return dict(job, log=list(job["log"])) if job else None

    def shutdown(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)
