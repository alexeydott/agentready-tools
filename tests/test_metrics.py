from __future__ import annotations

import asyncio
import time
from concurrent.futures import ThreadPoolExecutor
from threading import Event, Lock

from agentready.audit_core.store import (
    EVIDENCE_CLAIM_STALE_SECONDS,
    MemorySiteStore,
    RunRecord,
    RunUrlRecord,
    RunUrlState,
    SQLiteSiteStore,
)
from agentready.metrics import (
    ExternalMetric,
    MetricKind,
    ProviderConfig,
    ProviderJob,
    ProviderRunBudget,
    ProviderScheduler,
    ProviderStatus,
    cached_result,
    evaluate_cross_facts,
    ga4_adapter,
    gsc_adapter,
    sample_cwv,
)
from agentready.query_service import QueryService


def _metric(name: str = "sessions") -> ExternalMetric:
    return ExternalMetric("ga4", name, 12, "count", "fixture", "data-api-v1beta", "2026-08-10T00:00:00+00:00")


def test_provider_scheduler_resumes_stale_pending_evidence() -> None:
    store = MemorySiteStore()
    run_id = "run-stale-provider"
    url = "https://example.test/stale"
    store.begin_run(RunRecord(run_id, "config", "tool", "rules"))
    store.put_run_url(RunUrlRecord(run_id, url, RunUrlState.DISCOVERED))
    evidence_id = f"provider:ga4:{url}"
    store.claim_evidence(run_id, evidence_id)
    store.put_evidence(run_id, evidence_id, {"provider": "ga4", "status": "pending"})
    store._evidence_claims[(run_id, evidence_id)] = time.monotonic() - EVIDENCE_CLAIM_STALE_SECONDS - 1
    calls = 0

    async def operation(_: str, __: str | None) -> tuple[ExternalMetric, ...]:
        nonlocal calls
        calls += 1
        return (_metric(),)

    adapter = ga4_adapter(ProviderConfig(enabled=True, explicit_operation=True))
    scheduler = ProviderScheduler()
    result = scheduler.run_for_urls(
        run_id,
        adapter,
        operation,
        query_service=QueryService(store),
        store=store,
    )

    assert calls == 1
    assert result[0].status is ProviderStatus.AVAILABLE


async def _one_metric(_: str | None) -> tuple[ExternalMetric, ...]:
    return (_metric(),)


async def _slow_metric(_: str | None) -> tuple[ExternalMetric, ...]:
    await asyncio.sleep(0.05)
    return ()


async def _failed_metric(_: str | None) -> tuple[ExternalMetric, ...]:
    raise RuntimeError("boom")


def test_provider_requires_explicit_opt_in_and_does_not_call_operation() -> None:
    called = False

    async def operation(_: str | None):
        nonlocal called
        called = True
        return (_metric(),)

    result = ga4_adapter(ProviderConfig()).run(operation)

    assert result.status is ProviderStatus.NOT_REQUESTED
    assert called is False


def test_provider_quota_timeout_and_failure_are_diagnosable() -> None:
    cancelled = False

    async def cancellable_operation(_: str | None) -> tuple[ExternalMetric, ...]:
        nonlocal cancelled
        try:
            await asyncio.sleep(1)
        finally:
            cancelled = True

    quota = ga4_adapter(ProviderConfig(enabled=True, explicit_operation=True, quota=0)).run(_one_metric)
    started = time.monotonic()
    timeout = ga4_adapter(ProviderConfig(enabled=True, explicit_operation=True, timeout_seconds=0.01)).run(
        cancellable_operation
    )
    unavailable = ga4_adapter(ProviderConfig(enabled=True, explicit_operation=True)).run(_failed_metric)

    assert quota.status is ProviderStatus.QUOTA_EXCEEDED
    assert timeout.status is ProviderStatus.TIMEOUT
    assert time.monotonic() - started < 0.1
    assert cancelled is True
    assert unavailable.status is ProviderStatus.UNAVAILABLE


def test_metrics_are_enrichment_and_cached_fixtures_are_deterministic() -> None:
    metric = _metric()
    first = cached_result("ga4", (metric,))
    second = cached_result("ga4", (metric,))

    assert first.to_dict() == second.to_dict()
    assert first.from_cache is True
    assert first.metrics[0].kind is MetricKind.ENRICHMENT
    assert "credential" not in str(first.to_dict()).lower()


def test_cwv_sampling_keeps_source_version_timestamp_and_partial_state() -> None:
    result = sample_cwv(
        {"LCP": 1200, "CLS": 0.03},
        source="pagespeed-fixture",
        version="psi-v5",
        observed_at="2026-08-10T00:00:00+00:00",
    )

    assert result.status is ProviderStatus.PARTIAL
    assert {metric.name for metric in result.metrics} == {"lcp", "cls"}
    assert all(metric.source == "pagespeed-fixture" for metric in result.metrics)
    assert all(metric.version == "psi-v5" for metric in result.metrics)
    assert all(metric.observed_at == "2026-08-10T00:00:00+00:00" for metric in result.metrics)
    assert "core score unchanged" in (result.detail or "")


def test_external_metric_projects_to_store_record() -> None:
    record = _metric("lcp").to_record("run-1", url_key="https://example.test/")
    assert record.run_id == "run-1"
    assert record.provider == "ga4"
    assert record.value == 12
    assert record.kind == "enrichment"


def test_provider_scheduler_runs_explicit_jobs_with_bounded_workers():
    adapter = ga4_adapter(ProviderConfig(enabled=True, explicit_operation=True))
    result = ProviderScheduler(max_workers=1).run([ProviderJob(adapter, _one_metric)])
    assert result[0].status is ProviderStatus.AVAILABLE


def test_provider_scheduler_isolates_timeout_and_quota_from_successful_facts():
    slow = ga4_adapter(
        ProviderConfig(enabled=True, explicit_operation=True, timeout_seconds=0.01)
    )
    quota_exhausted = ga4_adapter(
        ProviderConfig(enabled=True, explicit_operation=True, quota=0)
    )
    healthy = gsc_adapter(ProviderConfig(enabled=True, explicit_operation=True))

    results = ProviderScheduler(max_workers=3).run(
        [
            ProviderJob(slow, _slow_metric),
            ProviderJob(quota_exhausted, _one_metric),
            ProviderJob(healthy, _one_metric),
        ]
    )

    assert [result.status for result in results] == [
        ProviderStatus.TIMEOUT,
        ProviderStatus.QUOTA_EXCEEDED,
        ProviderStatus.AVAILABLE,
    ]
    assert results[2].metrics[0].observed_at == "2026-08-10T00:00:00+00:00"


def test_provider_scheduler_enforces_one_global_quota_across_concurrent_jobs():
    calls = 0

    async def operation(_: str | None):
        nonlocal calls
        calls += 1
        return (_metric(),)

    adapter = ga4_adapter(ProviderConfig(enabled=True, explicit_operation=True, quota=1))
    results = ProviderScheduler(max_workers=4).run(
        [ProviderJob(adapter, operation) for _ in range(8)]
    )

    assert calls == 1
    assert sum(result.status is ProviderStatus.AVAILABLE for result in results) == 1
    assert sum(result.status is ProviderStatus.QUOTA_EXCEEDED for result in results) == 7


def test_provider_scheduler_shares_quota_across_adapter_instances():
    calls = 0

    async def operation(_: str | None):
        nonlocal calls
        calls += 1
        return (_metric(),)

    adapters = [
        ga4_adapter(ProviderConfig(enabled=True, explicit_operation=True, quota=1)),
        ga4_adapter(ProviderConfig(enabled=True, explicit_operation=True, quota=1)),
    ]
    results = ProviderScheduler(max_workers=2).run([ProviderJob(adapter, operation) for adapter in adapters])
    assert calls == 1
    assert [item.status for item in results].count(ProviderStatus.AVAILABLE) == 1


def test_provider_run_budget_keeps_total_and_provider_limits_deterministic():
    budget = ProviderRunBudget(total=2, per_provider={"ga4": 1, "gsc": 2})

    assert budget.reserve("ga4") is True
    assert budget.reserve("ga4") is False
    assert budget.reserve("gsc") is True
    assert budget.reserve("gsc") is False
    budget.mark_started("ga4")
    budget.release("gsc")

    snapshot = budget.snapshot()
    assert snapshot.reserved == 1
    assert snapshot.started == 1
    assert snapshot.released == 1
    assert snapshot.exhausted == 2


def test_provider_scheduler_does_not_charge_cached_or_prestart_cancelled_jobs():
    calls = 0

    async def operation(_: str | None):
        nonlocal calls
        calls += 1
        return (_metric(),)

    adapter = ga4_adapter(ProviderConfig(enabled=True, explicit_operation=True, quota=1))
    cached = _metric("cached")
    results = ProviderScheduler(max_workers=2).run(
        [
            ProviderJob(adapter, operation, cached=(cached,)),
            ProviderJob(adapter, operation, cancelled=True),
            ProviderJob(adapter, operation),
        ]
    )

    assert calls == 1
    assert results[0].from_cache is True
    assert results[1].status is ProviderStatus.CANCELLED
    assert results[2].status is ProviderStatus.AVAILABLE


def test_provider_scheduler_selects_urls_and_persists_metrics():
    store = MemorySiteStore()
    store.begin_run(RunRecord("run-provider", "config", "tool", "rules"))
    store.put_run_url(RunUrlRecord("run-provider", "https://example.test/", RunUrlState.PARSED))
    adapter = ga4_adapter(ProviderConfig(enabled=True, explicit_operation=True))

    async def operation(url: str, _: str | None) -> tuple[ExternalMetric, ...]:
        return (ExternalMetric("ga4", "sessions", len(url), "count", "fixture", "1", "now"),)

    results = ProviderScheduler(max_workers=1).run_for_urls(
        "run-provider",
        adapter,
        operation,
        query_service=QueryService(store),
        store=store,
    )
    assert results[0].status is ProviderStatus.AVAILABLE
    assert next(iter(store.iter_metrics("run-provider"))).value > 0
    assert ("run-provider", "provider:ga4:https://example.test/") in store._evidence


def test_provider_scheduler_resume_is_idempotent_for_memory_and_sqlite(tmp_path):
    for store in (
        MemorySiteStore(),
        SQLiteSiteStore(tmp_path / "provider-idempotency.sqlite"),
    ):
        try:
            store.begin_run(RunRecord("run-provider-idempotent", "config", "tool", "rules"))
            for url in ("https://example.test/a", "https://example.test/b"):
                store.put_run_url(RunUrlRecord("run-provider-idempotent", url, RunUrlState.PARSED))
            calls = 0

            async def operation(url: str, _: str | None):
                nonlocal calls
                calls += 1
                return (ExternalMetric("ga4", "sessions", len(url), "count", "fixture", "1", "now"),)

            adapter = ga4_adapter(ProviderConfig(enabled=True, explicit_operation=True, quota=2))
            scheduler = ProviderScheduler(max_workers=2)
            first = scheduler.run_for_urls(
                "run-provider-idempotent", adapter, operation,
                query_service=QueryService(store), store=store,
            )
            second = scheduler.run_for_urls(
                "run-provider-idempotent", adapter, operation,
                query_service=QueryService(store), store=store,
            )

            assert calls == 2
            assert [result.from_cache for result in first] == [False, False]
            assert [result.from_cache for result in second] == [True, True]
            assert [(result.status, result.metrics, result.quota_remaining) for result in first] == [
                (result.status, result.metrics, result.quota_remaining) for result in second
            ]
            assert len(tuple(store.iter_metrics("run-provider-idempotent"))) == 2
        finally:
            store.close()


def test_provider_scheduler_claims_inflight_url_once(tmp_path):
    for store in (MemorySiteStore(), SQLiteSiteStore(tmp_path / "provider-concurrent.sqlite")):
        try:
            run_id = "run-provider-concurrent"
            store.begin_run(RunRecord(run_id, "config", "tool", "rules"))
            url = "https://example.test/concurrent"
            store.put_run_url(RunUrlRecord(run_id, url, RunUrlState.PARSED))
            started = Event()
            release = Event()
            lock = Lock()
            calls = 0

            async def operation(
                _: str,
                __: str | None,
                current_lock: Lock = lock,
                current_started: Event = started,
                current_release: Event = release,
            ):
                nonlocal calls
                with current_lock:
                    calls += 1
                current_started.set()
                deadline = time.monotonic() + 3
                while not current_release.is_set() and time.monotonic() < deadline:
                    await asyncio.sleep(0.01)
                return (ExternalMetric("ga4", "sessions", 1, "count", "fixture", "1", "now"),)

            adapter = ga4_adapter(ProviderConfig(enabled=True, explicit_operation=True, quota=2, timeout_seconds=3))
            scheduler = ProviderScheduler(max_workers=1)
            with ThreadPoolExecutor(max_workers=2) as pool:
                first = pool.submit(scheduler.run_for_urls, run_id, adapter, operation, query_service=QueryService(store), store=store)
                assert started.wait(timeout=2)
                second = pool.submit(scheduler.run_for_urls, run_id, adapter, operation, query_service=QueryService(store), store=store)
                release.set()
                first_result = first.result(timeout=5)
                second_result = second.result(timeout=5)
            assert calls == 1
            assert first_result[0].metrics == second_result[0].metrics
        finally:
            store.close()


def test_cross_fact_rules_join_local_and_provider_signals():
    findings = evaluate_cross_facts(
        {
            "https://example.test/a": {
                "locally_indexable": True,
                "provider_indexed": False,
                "sitemap_present": True,
            },
            "https://example.test/b": {
                "noindex": True,
                "traffic": 4,
                "impressions": 10,
                "clicks": 0,
            },
        }
    )

    assert {(item.id, item.url) for item in findings} == {
        ("indexability-provider-mismatch", "https://example.test/a"),
        ("sitemap-provider-mismatch", "https://example.test/a"),
        ("noindex-with-traffic", "https://example.test/b"),
        ("impressions-without-clicks", "https://example.test/b"),
    }
