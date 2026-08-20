"""Bounded in-process v2 audit job lifecycle."""

from __future__ import annotations

import inspect
import logging
import threading
import time
import uuid
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

logger = logging.getLogger(__name__)


class JobStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(frozen=True, slots=True)
class JobSnapshot:
    id: str
    status: JobStatus
    result: Any = None
    error: str | None = None
    progress: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "status": self.status.value, "result": self.result, "error": self.error, "progress": self.progress or {}}


class AuditJobManager:
    def __init__(self, *, max_jobs: int = 8) -> None:
        if max_jobs <= 0:
            raise ValueError("max_jobs must be positive")
        self._max_jobs = max_jobs
        self._executor = ThreadPoolExecutor(max_workers=max_jobs)
        self._jobs: dict[str, tuple[Future[Any], JobStatus, threading.Event]] = {}
        self._progress: dict[str, dict[str, Any]] = {}
        self._started_at: dict[str, float] = {}
        self._updated_at: dict[str, float] = {}
        self._lock = threading.Lock()

    def submit(self, operation: Callable[[], Any]) -> str:
        with self._lock:
            active = sum(status in {JobStatus.PENDING, JobStatus.RUNNING} for _, status, _ in self._jobs.values())
            if active >= self._max_jobs:
                raise RuntimeError("job capacity reached")
            job_id = uuid.uuid4().hex
            cancel_event = threading.Event()
            if _accepts_cancel_event(operation):
                future = self._executor.submit(operation, cancel_event)  # type: ignore[arg-type]
            else:
                future = self._executor.submit(operation)
            self._jobs[job_id] = (future, JobStatus.RUNNING, cancel_event)
            self._progress[job_id] = {"phase": "queued", "fetched": 0, "discovered": 0}
            now = time.time()
            self._started_at[job_id] = now
            self._updated_at[job_id] = now
            logger.info("v2 audit job submitted id=%s", job_id)
            return job_id

    def cancel(self, job_id: str) -> bool:
        with self._lock:
            item = self._jobs.get(job_id)
            if item is None:
                return False
            future, _, cancel_event = item
            cancel_event.set()
            cancelled = future.cancel()
            # Drop bookkeeping immediately. A running operation receives the
            # cooperative event and may finish current I/O, but it no longer
            # occupies a capacity slot or appears in the task monitor.
            self._jobs.pop(job_id, None)
            self._progress.pop(job_id, None)
            self._started_at.pop(job_id, None)
            self._updated_at.pop(job_id, None)
            logger.info("v2 audit job cancelled and removed id=%s running=%s", job_id, not cancelled)
            return cancelled

    def get(self, job_id: str) -> JobSnapshot:
        with self._lock:
            item = self._jobs.get(job_id)
        if item is None:
            raise KeyError(job_id)
        future, status, cancel_event = item
        if status is JobStatus.CANCELLED:
            return JobSnapshot(job_id, status, progress=self._progress.get(job_id))
        if future.running():
            return JobSnapshot(job_id, JobStatus.RUNNING, {"cancel_requested": cancel_event.is_set()}, progress=self._progress.get(job_id))
        if not future.done():
            return JobSnapshot(job_id, JobStatus.PENDING, {"cancel_requested": cancel_event.is_set()}, progress=self._progress.get(job_id))
        try:
            return JobSnapshot(job_id, JobStatus.COMPLETED, future.result(), progress=self._progress.get(job_id))
        except Exception as exc:  # noqa: BLE001 - job boundary must normalize operation failures
            logger.exception("v2 audit job failed id=%s error_type=%s", job_id, type(exc).__name__)
            return JobSnapshot(job_id, JobStatus.FAILED, error=f"{type(exc).__name__}: {exc}" if str(exc) else type(exc).__name__, progress=self._progress.get(job_id))

    def update_progress(self, job_id: str, **values: Any) -> None:
        with self._lock:
            if job_id in self._progress:
                self._progress[job_id].update(values)
                self._updated_at[job_id] = time.time()

    def list(self) -> list[dict[str, Any]]:
        """Return bounded status-only snapshots for the local task monitor."""
        now = time.time()
        with self._lock:
            items = []
            for job_id, (future, status, cancel_event) in self._jobs.items():
                current = status
                if status in {JobStatus.PENDING, JobStatus.RUNNING} and future.done():
                    current = JobStatus.FAILED if future.exception() is not None else JobStatus.COMPLETED
                items.append({
                    "id": job_id,
                    "status": current.value,
                    "error": "audit job failed" if current is JobStatus.FAILED else None,
                    "progress": dict(self._progress.get(job_id, {})),
                    "cancel_requested": cancel_event.is_set(),
                    "age_seconds": max(0, int(now - self._started_at.get(job_id, now))),
                    "updated_age_seconds": max(0, int(now - self._updated_at.get(job_id, now))),
                })
        return sorted(items, key=lambda item: item["age_seconds"], reverse=True)[:50]


def _accepts_cancel_event(operation: Callable[..., Any]) -> bool:
    try:
        parameters = tuple(inspect.signature(operation).parameters.values())
    except (TypeError, ValueError):
        return False
    return any(parameter.kind in {parameter.POSITIONAL_ONLY, parameter.POSITIONAL_OR_KEYWORD} for parameter in parameters)
