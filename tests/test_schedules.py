from datetime import UTC, datetime, timedelta

import pytest

from agentready.audit_core.store import MemorySiteStore, ProjectRecord, ScheduleRecord, SQLiteSiteStore
from agentready.schedules import ScheduleService, ScheduleWorker


class Clock:
    def __init__(self):
        self.value = datetime(2026, 1, 1, tzinfo=UTC)

    def __call__(self):
        return self.value

    def advance(self, seconds):
        self.value += timedelta(seconds=seconds)


@pytest.mark.parametrize("store_factory", [lambda tmp_path: MemorySiteStore(), lambda tmp_path: SQLiteSiteStore(tmp_path / "schedule.sqlite")])
def test_schedule_claims_once_and_runs_at_most_one_catchup(tmp_path, store_factory):
    store = store_factory(tmp_path)
    store.put_project(ProjectRecord("p1", "One", "https://example.test"))
    clock = Clock()
    calls = []
    service = ScheduleService(store, clock=clock, runner=lambda project: calls.append(project.project_id) or "run-1")
    service.create(ScheduleRecord("s1", "p1", 60, "2025-12-31T23:59:00+00:00"))
    assert service.run_once("worker-a") is True
    assert service.run_once("worker-b") is False
    assert calls == ["p1"]
    assert service.get("s1").failure_count == 0
    assert service.get("s1").next_run_at == "2026-01-01T00:01:00+00:00"


def test_schedule_failure_uses_bounded_backoff_and_disabled_schedule_does_not_run():
    store = MemorySiteStore()
    store.put_project(ProjectRecord("p1", "One", "https://example.test"))
    clock = Clock()
    service = ScheduleService(store, clock=clock, runner=lambda _: (_ for _ in ()).throw(RuntimeError("boom")), max_backoff_seconds=90)
    service.create(ScheduleRecord("s1", "p1", 60, "2025-12-31T23:59:00+00:00"))
    assert service.run_once() is True
    failed = service.get("s1")
    assert failed.failure_count == 1
    assert failed.next_run_at == "2026-01-01T00:01:00+00:00"
    service.set_enabled("s1", False)
    clock.advance(3600)
    assert service.run_once() is False


def test_worker_is_idle_until_explicitly_started():
    store = MemorySiteStore()
    store.put_project(ProjectRecord("p1", "One", "https://example.test"))
    clock = Clock()
    calls = []
    service = ScheduleService(store, clock=clock, runner=lambda _: calls.append(1) or "run-1")
    service.create(ScheduleRecord("s1", "p1", 60, "2025-12-31T23:59:00+00:00"))
    worker = ScheduleWorker(service, poll_seconds=0.01)
    assert not worker.running
    assert calls == []
    worker.start()
    for _ in range(20):
        if calls:
            break
        clock.advance(1)
        __import__("time").sleep(0.01)
    worker.stop()
    assert calls == [1]
