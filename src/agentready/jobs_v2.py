"""Bounded in-process v2 audit job lifecycle."""

from __future__ import annotations

import logging
import threading
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Callable

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

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "status": self.status.value, "result": self.result, "error": self.error}


class AuditJobManager:
    def __init__(self, *, max_jobs: int = 8) -> None:
        if max_jobs <= 0:
            raise ValueError("max_jobs must be positive")
        self._max_jobs = max_jobs
        self._executor = ThreadPoolExecutor(max_workers=max_jobs)
        self._jobs: dict[str, tuple[Future[Any], JobStatus]] = {}
        self._lock = threading.Lock()

    def submit(self, operation: Callable[[], Any]) -> str:
        with self._lock:
            active = sum(status in {JobStatus.PENDING, JobStatus.RUNNING} for _, status in self._jobs.values())
            if active >= self._max_jobs:
                raise RuntimeError("job capacity reached")
            job_id = uuid.uuid4().hex
            future = self._executor.submit(operation)
            self._jobs[job_id] = (future, JobStatus.RUNNING)
            logger.info("v2 audit job submitted id=%s", job_id)
            return job_id

    def cancel(self, job_id: str) -> bool:
        with self._lock:
            item = self._jobs.get(job_id)
            if item is None:
                return False
            future, _ = item
            cancelled = future.cancel()
            if cancelled:
                self._jobs[job_id] = (future, JobStatus.CANCELLED)
            return cancelled

    def get(self, job_id: str) -> JobSnapshot:
        with self._lock:
            item = self._jobs.get(job_id)
        if item is None:
            raise KeyError(job_id)
        future, status = item
        if status is JobStatus.CANCELLED:
            return JobSnapshot(job_id, status)
        if future.running():
            return JobSnapshot(job_id, JobStatus.RUNNING)
        if not future.done():
            return JobSnapshot(job_id, JobStatus.PENDING)
        try:
            return JobSnapshot(job_id, JobStatus.COMPLETED, future.result())
        except Exception:
            return JobSnapshot(job_id, JobStatus.FAILED, error="audit job failed")
