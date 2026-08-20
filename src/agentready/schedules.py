"""Restart-safe local scheduling for bounded v2 audits.

Scheduling is deliberately opt-in: constructing :class:`ScheduleWorker` does
not execute anything.  The worker owns only a lease loop; the audit itself is
still executed by ``AuditService`` through the injected runner.
"""
from __future__ import annotations

import logging
import threading
import time
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from .audit_core.store import ProjectRecord, ScheduleExecutionRecord, ScheduleRecord, SiteStore

logger = logging.getLogger(__name__)

Clock = Callable[[], datetime]
AuditRunner = Callable[[ProjectRecord], str | None]


def utc_now() -> datetime:
    return datetime.now(UTC)


def _stamp(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="seconds")


class ScheduleService:
    """Manage durable schedules and execute at most one missed occurrence."""

    def __init__(self, store: SiteStore, *, clock: Clock = utc_now, runner: AuditRunner | None = None, lease_seconds: int = 60, max_backoff_seconds: int = 3600) -> None:
        if lease_seconds <= 0 or max_backoff_seconds <= 0:
            raise ValueError("lease and backoff bounds must be positive")
        self.store = store
        self.clock = clock
        self.runner = runner or self._audit_project
        self.lease_seconds = lease_seconds
        self.max_backoff_seconds = max_backoff_seconds

    def _audit_project(self, project: ProjectRecord) -> str | None:
        from .audit_service import AuditRequest, AuditService
        from .projects import ProjectService

        result = AuditService().run(AuditRequest(target=project.target, profile=project.default_profile, ruleset=project.default_ruleset, store=self.store))
        run_id = result.run.context.run_id
        ProjectService(self.store).attach_run(project.project_id, run_id, target=project.target, trigger="scheduled")
        logger.info("[FIX:schedule-project-history] attached scheduled run project_id=%s run_id=%s", project.project_id, run_id)
        return run_id

    def create(self, schedule: ScheduleRecord) -> ScheduleRecord:
        self.store.get_project(schedule.project_id)
        logger.info("schedule create schedule_id=%s project_id=%s next_run_at=%s", schedule.schedule_id, schedule.project_id, schedule.next_run_at)
        return self.store.put_schedule(schedule)

    def get(self, schedule_id: str) -> ScheduleRecord:
        return self.store.get_schedule(schedule_id)

    def list(self, project_id: str | None = None) -> tuple[ScheduleRecord, ...]:
        return tuple(self.store.iter_schedules(project_id))

    def set_enabled(self, schedule_id: str, enabled: bool) -> ScheduleRecord:
        current = self.get(schedule_id)
        now = _stamp(self.clock())
        values = {field: getattr(current, field) for field in current.__dataclass_fields__}
        values.update(enabled=enabled, updated_at=now)
        return self.store.update_schedule(ScheduleRecord(**values))

    def run_once(self, worker_id: str = "local-worker") -> bool:
        now = self.clock()
        now_text = _stamp(now)
        lease_until = _stamp(now + timedelta(seconds=self.lease_seconds))
        schedule = self.store.claim_due_schedule(now_text, worker_id, lease_until)
        if schedule is None:
            return False
        execution_id = f"{schedule.schedule_id}:{uuid.uuid4().hex}"
        started = _stamp(now)
        self.store.put_schedule_execution(ScheduleExecutionRecord(execution_id, schedule.schedule_id, None, started))
        try:
            run_id = self.runner(self.store.get_project(schedule.project_id)) if self.runner else None
            completed = self.clock()
            updated = ScheduleRecord(**{**{field: getattr(schedule, field) for field in schedule.__dataclass_fields__}, "next_run_at": _stamp(completed + timedelta(seconds=schedule.interval_seconds)), "lease_owner": None, "lease_until": None, "failure_count": 0, "last_run_id": run_id, "updated_at": _stamp(completed)})
            self.store.update_schedule(updated)
            self.store.put_schedule_execution(ScheduleExecutionRecord(execution_id, schedule.schedule_id, run_id, started, _stamp(completed), "succeeded"))
            logger.info("schedule completed schedule_id=%s run_id=%s next_run_at=%s", schedule.schedule_id, run_id or "none", updated.next_run_at)
        except Exception as exc:  # noqa: BLE001 - sanitized error is persisted
            completed = self.clock()
            delay = min(self.max_backoff_seconds, schedule.interval_seconds * (2 ** min(schedule.failure_count, 10)))
            updated = ScheduleRecord(**{**{field: getattr(schedule, field) for field in schedule.__dataclass_fields__}, "next_run_at": _stamp(completed + timedelta(seconds=delay)), "lease_owner": None, "lease_until": None, "failure_count": schedule.failure_count + 1, "updated_at": _stamp(completed)})
            self.store.update_schedule(updated)
            self.store.put_schedule_execution(ScheduleExecutionRecord(execution_id, schedule.schedule_id, None, started, _stamp(completed), "failed", type(exc).__name__))
            logger.warning("schedule failed schedule_id=%s error=%s next_run_at=%s", schedule.schedule_id, type(exc).__name__, updated.next_run_at)
        return True


class ScheduleWorker:
    """Explicitly started local worker; no background work before ``start``."""

    def __init__(self, service: ScheduleService, *, worker_id: str = "local-worker", poll_seconds: float = 1.0) -> None:
        if poll_seconds <= 0:
            raise ValueError("poll interval must be positive")
        self.service = service
        self.worker_id = worker_id
        self.poll_seconds = poll_seconds
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if self.running:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name=f"agentready-schedule-{self.worker_id}", daemon=True)
        self._thread.start()
        logger.info("schedule worker started worker_id=%s", self.worker_id)

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout)
        self._thread = None
        logger.info("schedule worker stopped worker_id=%s", self.worker_id)

    def _loop(self) -> None:
        while not self._stop.is_set():
            self.service.run_once(self.worker_id)
            self._stop.wait(self.poll_seconds)
