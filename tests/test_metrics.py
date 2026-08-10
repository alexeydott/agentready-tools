from __future__ import annotations

import time

from agentready.metrics import (
    ExternalMetric,
    MetricKind,
    ProviderConfig,
    ProviderStatus,
    cached_result,
    ga4_adapter,
    sample_cwv,
)


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
