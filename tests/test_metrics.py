from __future__ import annotations

import time

from agentready.audit_core.store import (
    MemorySiteStore,
    RunRecord,
    RunUrlRecord,
    RunUrlState,
)
from agentready.metrics import (
    ExternalMetric,
    MetricKind,
    ProviderConfig,
    ProviderJob,
    ProviderScheduler,
    ProviderStatus,
    cached_result,
    evaluate_cross_facts,
    ga4_adapter,
    sample_cwv,
)
from agentready.query_service import QueryService


def _metric(name: str = "sessions") -> ExternalMetric:
    return ExternalMetric("ga4", name, 12, "count", "fixture", "data-api-v1beta", "2026-08-10T00:00:00+00:00")


def test_provider_requires_explicit_opt_in_and_does_not_call_operation() -> None:
    called = False

    def operation(_: str | None):
        nonlocal called
        called = True
        return (_metric(),)

    result = ga4_adapter(ProviderConfig()).run(operation)

    assert result.status is ProviderStatus.NOT_REQUESTED
    assert called is False


def test_provider_quota_timeout_and_failure_are_diagnosable() -> None:
    quota = ga4_adapter(ProviderConfig(enabled=True, explicit_operation=True, quota=0)).run(lambda _: (_metric(),))
    timeout = ga4_adapter(ProviderConfig(enabled=True, explicit_operation=True, timeout_seconds=0.01)).run(
        lambda _: (time.sleep(0.05),)[0]  # type: ignore[return-value]
    )
    unavailable = ga4_adapter(ProviderConfig(enabled=True, explicit_operation=True)).run(lambda _: (_ for _ in ()).throw(RuntimeError("boom")))

    assert quota.status is ProviderStatus.QUOTA_EXCEEDED
    assert timeout.status is ProviderStatus.TIMEOUT
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
    result = ProviderScheduler(max_workers=1).run([ProviderJob(adapter, lambda _: (_metric(),))])
    assert result[0].status is ProviderStatus.AVAILABLE


def test_provider_scheduler_isolates_timeout_and_quota_from_successful_facts():
    slow = ga4_adapter(
        ProviderConfig(enabled=True, explicit_operation=True, timeout_seconds=0.01)
    )
    quota_exhausted = ga4_adapter(
        ProviderConfig(enabled=True, explicit_operation=True, quota=0)
    )
    healthy = ga4_adapter(ProviderConfig(enabled=True, explicit_operation=True))

    results = ProviderScheduler(max_workers=3).run(
        [
            ProviderJob(slow, lambda _: (time.sleep(0.05),)[0]),  # type: ignore[return-value]
            ProviderJob(quota_exhausted, lambda _: (_metric("quota"),)),
            ProviderJob(healthy, lambda _: (_metric("sessions"),)),
        ]
    )

    assert [result.status for result in results] == [
        ProviderStatus.TIMEOUT,
        ProviderStatus.QUOTA_EXCEEDED,
        ProviderStatus.AVAILABLE,
    ]
    assert results[2].metrics[0].observed_at == "2026-08-10T00:00:00+00:00"


def test_provider_scheduler_selects_urls_and_persists_metrics():
    store = MemorySiteStore()
    store.begin_run(RunRecord("run-provider", "config", "tool", "rules"))
    store.put_run_url(RunUrlRecord("run-provider", "https://example.test/", RunUrlState.PARSED))
    adapter = ga4_adapter(ProviderConfig(enabled=True, explicit_operation=True))
    results = ProviderScheduler(max_workers=1).run_for_urls(
        "run-provider",
        adapter,
        lambda url, _: (ExternalMetric("ga4", "sessions", len(url), "count", "fixture", "1", "now"),),
        query_service=QueryService(store),
        store=store,
    )
    assert results[0].status is ProviderStatus.AVAILABLE
    assert next(iter(store.iter_metrics("run-provider"))).value > 0
    assert ("run-provider", "provider:ga4:https://example.test/") in store._evidence


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
