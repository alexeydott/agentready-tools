"""Bounded in-process v2 audit job lifecycle."""

from __future__ import annotations

import inspect
import logging
import threading
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

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "status": self.status.value, "result": self.result, "error": self.error}


class AuditJobManager:
    def __init__(self, *, max_jobs: int = 8) -> None:
        if max_jobs <= 0:
            raise ValueError("max_jobs must be positive")
        self._max_jobs = max_jobs
        self._executor = ThreadPoolExecutor(max_workers=max_jobs)
        self._jobs: dict[str, tuple[Future[Any], JobStatus, threading.Event]] = {}
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
            if cancelled:
                self._jobs[job_id] = (future, JobStatus.CANCELLED, cancel_event)
            else:
                logger.info("v2 audit job cancellation requested id=%s", job_id)
            return cancelled

    def get(self, job_id: str) -> JobSnapshot:
        with self._lock:
            item = self._jobs.get(job_id)
        if item is None:
            raise KeyError(job_id)
        future, status, cancel_event = item
        if status is JobStatus.CANCELLED:
            return JobSnapshot(job_id, status)
        if future.running():
            return JobSnapshot(job_id, JobStatus.RUNNING, {"cancel_requested": cancel_event.is_set()})
        if not future.done():
            return JobSnapshot(job_id, JobStatus.PENDING, {"cancel_requested": cancel_event.is_set()})
        try:
            return JobSnapshot(job_id, JobStatus.COMPLETED, future.result())
        except Exception as exc:  # noqa: BLE001 - job boundary must normalize operation failures
            logger.warning("v2 audit job failed id=%s error_type=%s", job_id, type(exc).__name__)
            return JobSnapshot(job_id, JobStatus.FAILED, error="audit job failed")


def _accepts_cancel_event(operation: Callable[..., Any]) -> bool:
    try:
        parameters = tuple(inspect.signature(operation).parameters.values())
    except (TypeError, ValueError):
        return False
    return any(parameter.kind in {parameter.POSITIONAL_ONLY, parameter.POSITIONAL_OR_KEYWORD} for parameter in parameters)
