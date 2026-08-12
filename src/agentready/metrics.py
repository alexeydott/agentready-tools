"""Opt-in external metrics and performance integration contracts.

This module deliberately does not participate in the normal scan path.
Provider calls require explicit configuration and an explicit operation from
the caller; credentials are represented only by an OS-vault reference.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Mapping
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Protocol

from .audit_core.store import MetricRecord
from .query_service import QueryService, RunUrlQuery

logger = logging.getLogger(__name__)


class ProviderStatus(StrEnum):
    AVAILABLE = "available"
    PARTIAL = "partial"
    NOT_REQUESTED = "not_requested"
    UNAVAILABLE = "unavailable"
    QUOTA_EXCEEDED = "quota_exceeded"
    TIMEOUT = "timeout"
    ERROR = "error"


class MetricKind(StrEnum):
    OBSERVED = "observed"
    ENRICHMENT = "enrichment"


@dataclass(frozen=True, slots=True)
class ProviderConfig:
    enabled: bool = False
    explicit_operation: bool = False
    timeout_seconds: float = 10.0
    quota: int = 1
    credential_ref: str | None = None

    def __post_init__(self) -> None:
        if self.timeout_seconds <= 0:
            raise ValueError("provider timeout must be positive")
        if self.quota < 0:
            raise ValueError("provider quota cannot be negative")


@dataclass(frozen=True, slots=True)
class ExternalMetric:
    provider: str
    name: str
    value: float | int | str | None
    unit: str | None
    source: str
    version: str
    observed_at: str
    kind: MetricKind = MetricKind.ENRICHMENT

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "name": self.name,
            "value": self.value,
            "unit": self.unit,
            "source": self.source,
            "version": self.version,
            "observed_at": self.observed_at,
            "kind": self.kind.value,
        }

    def to_record(self, run_id: str, *, url_key: str | None = None) -> MetricRecord:
        return MetricRecord(
            run_id=run_id,
            url_key=url_key,
            provider=self.provider,
            name=self.name,
            value=self.value,
            unit=self.unit,
            source=self.source,
            version=self.version,
            observed_at=self.observed_at,
            kind=self.kind.value,
        )


@dataclass(frozen=True, slots=True)
class ProviderResult:
    provider: str
    status: ProviderStatus
    metrics: tuple[ExternalMetric, ...] = ()
    detail: str | None = None
    quota_remaining: int | None = None
    from_cache: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "status": self.status.value,
            "detail": self.detail,
            "quota_remaining": self.quota_remaining,
            "from_cache": self.from_cache,
            "metrics": [metric.to_dict() for metric in self.metrics],
        }


class ExternalMetricProvider(Protocol):
    """Normalized provider contract for opt-in external enrichment."""

    provider: str
    version: str
    config: ProviderConfig

    def run(
        self,
        operation: Callable[[str | None], tuple[ExternalMetric, ...]],
        *,
        cached: tuple[ExternalMetric, ...] | None = None,
    ) -> ProviderResult:
        ...


@dataclass(frozen=True, slots=True)
class ProviderAdapter:
    provider: str
    version: str
    config: ProviderConfig

    def run(
        self,
        operation: Callable[[str | None], tuple[ExternalMetric, ...]],
        *,
        cached: tuple[ExternalMetric, ...] | None = None,
    ) -> ProviderResult:
        """Run one explicitly requested provider operation under hard limits."""
        logger.debug(
            "provider operation start provider=%s enabled=%s explicit=%s cached=%s",
            self.provider,
            self.config.enabled,
            self.config.explicit_operation,
            cached is not None,
        )
        if cached is not None:
            return ProviderResult(self.provider, ProviderStatus.AVAILABLE, cached, from_cache=True)
        if not self.config.enabled or not self.config.explicit_operation:
            return ProviderResult(self.provider, ProviderStatus.NOT_REQUESTED, detail="explicit opt-in is required")
        if self.config.quota == 0:
            return ProviderResult(self.provider, ProviderStatus.QUOTA_EXCEEDED, detail="provider quota exhausted", quota_remaining=0)
        started = time.monotonic()
        try:
            with ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(operation, self.config.credential_ref)
                metrics = future.result(timeout=self.config.timeout_seconds)
        except FutureTimeout:
            logger.warning("provider operation timed out provider=%s", self.provider)
            return ProviderResult(self.provider, ProviderStatus.TIMEOUT, detail="provider operation timed out")
        except Exception as exc:  # noqa: BLE001 - provider adapters are a defensive trust boundary
            logger.warning("provider operation failed provider=%s type=%s", self.provider, type(exc).__name__)
            return ProviderResult(self.provider, ProviderStatus.UNAVAILABLE, detail="provider operation unavailable")
        if not isinstance(metrics, tuple) or not all(isinstance(item, ExternalMetric) for item in metrics):
            return ProviderResult(self.provider, ProviderStatus.ERROR, detail="provider returned invalid metric contract")
        status = ProviderStatus.AVAILABLE if metrics else ProviderStatus.PARTIAL
        logger.info(
            "provider operation complete provider=%s status=%s metrics=%d elapsed_ms=%d",
            self.provider,
            status,
            len(metrics),
            int((time.monotonic() - started) * 1000),
        )
        return ProviderResult(self.provider, status, metrics, quota_remaining=max(0, self.config.quota - 1))


@dataclass(frozen=True, slots=True)
class ProviderJob:
    adapter: ProviderAdapter
    operation: Callable[[str | None], tuple[ExternalMetric, ...]]


@dataclass(frozen=True, slots=True)
class CrossFactResult:
    """Deterministic result produced by joining local and provider facts."""

    id: str
    url: str
    status: str
    reason: str


def evaluate_cross_facts(
    records: Mapping[str, Mapping[str, Any]],
    *,
    limit: int = 100_000,
) -> tuple[CrossFactResult, ...]:
    """Evaluate bounded local-indexability, traffic, and provider mismatches."""
    if limit <= 0 or limit > 100_000:
        raise ValueError("cross-fact limit must be between 1 and 100000")
    findings: list[CrossFactResult] = []
    for url in sorted(records)[:limit]:
        facts = records[url]
        if facts.get("locally_indexable") is True and facts.get("provider_indexed") is False:
            findings.append(CrossFactResult(
                "indexability-provider-mismatch",
                url,
                "warn",
                "local signals allow indexing but the provider reports the URL as not indexed",
            ))
        if facts.get("noindex") is True and float(facts.get("traffic", 0) or 0) > 0:
            findings.append(CrossFactResult(
                "noindex-with-traffic",
                url,
                "warn",
                "the URL has a noindex signal while observed traffic is non-zero",
            ))
        if float(facts.get("impressions", 0) or 0) > 0 and float(facts.get("clicks", 0) or 0) == 0:
            findings.append(CrossFactResult(
                "impressions-without-clicks",
                url,
                "info",
                "the provider reports impressions but no clicks",
            ))
        if facts.get("sitemap_present") is True and facts.get("provider_indexed") is False:
            findings.append(CrossFactResult(
                "sitemap-provider-mismatch",
                url,
                "warn",
                "the URL is present in the sitemap but absent from the provider index",
            ))
    return tuple(findings)


class ProviderScheduler:
    """Run explicitly requested provider jobs outside crawler workers."""

    def __init__(self, *, max_workers: int = 2) -> None:
        if max_workers <= 0 or max_workers > 16:
            raise ValueError("provider scheduler workers must be between 1 and 16")
        self.max_workers = max_workers

    def run(self, jobs: tuple[ProviderJob, ...] | list[ProviderJob]) -> tuple[ProviderResult, ...]:
        with ThreadPoolExecutor(max_workers=min(self.max_workers, max(1, len(jobs)))) as pool:
            futures = [pool.submit(job.adapter.run, job.operation) for job in jobs]
            return tuple(future.result() for future in futures)

    def run_for_urls(
        self,
        run_id: str,
        adapter: ProviderAdapter,
        operation: Callable[[str, str | None], tuple[ExternalMetric, ...]],
        *,
        query_service: QueryService,
        store: Any,
    ) -> tuple[ProviderResult, ...]:
        """Select bounded URLs through QueryService and persist provider metrics."""
        cursor: str | None = None
        urls: list[str] = []
        while True:
            page = query_service.run_urls(RunUrlQuery(run_id, cursor=cursor, limit=1000))
            urls.extend(item.url_key for item in page.items)
            if page.next_cursor is None:
                break
            cursor = page.next_cursor
        jobs = [
            ProviderJob(adapter, lambda credential, url=url: operation(url, credential))
            for url in urls
        ]
        results = self.run(jobs)
        for url, result in zip(urls, results):
            for metric in result.metrics:
                store.put_metric(metric.to_record(run_id, url_key=url))
            store.put_evidence(
                run_id,
                f"provider:{result.provider}:{url}",
                {
                    "provider": result.provider,
                    "status": result.status.value,
                    "quota_remaining": result.quota_remaining,
                    "from_cache": result.from_cache,
                    "detail": result.detail,
                },
            )
        return results


def _adapter(provider: str, version: str, config: ProviderConfig) -> ProviderAdapter:
    return ProviderAdapter(provider, version, config)


def ga4_adapter(config: ProviderConfig) -> ProviderAdapter:
    return _adapter("ga4", "data-api-v1beta", config)


def gsc_adapter(config: ProviderConfig) -> ProviderAdapter:
    return _adapter("gsc", "search-console-v1", config)


def url_inspection_adapter(config: ProviderConfig) -> ProviderAdapter:
    return _adapter("url-inspection", "search-console-v1", config)


def pagespeed_adapter(config: ProviderConfig) -> ProviderAdapter:
    return _adapter("pagespeed", "psi-v5", config)


_CWV_NAMES = frozenset({"lcp", "inp", "cls"})


def sample_cwv(
    samples: Mapping[str, float | int],
    *,
    source: str,
    version: str,
    observed_at: str | None = None,
) -> ProviderResult:
    """Convert bounded CWV samples into evidence-bearing enrichment metrics."""
    timestamp = observed_at or datetime.now(UTC).isoformat()
    metrics = tuple(
        ExternalMetric("pagespeed", name.lower(), value, "ms" if name.lower() != "cls" else None, source, version, timestamp)
        for name, value in sorted(samples.items())
        if name.lower() in _CWV_NAMES
    )
    status = ProviderStatus.AVAILABLE if len(metrics) == len(_CWV_NAMES) else ProviderStatus.PARTIAL
    return ProviderResult("pagespeed", status, metrics, detail="CWV is external enrichment; core score unchanged")


def cached_result(provider: str, metrics: tuple[ExternalMetric, ...]) -> ProviderResult:
    """Create a deterministic provider result from an offline fixture."""
    return ProviderResult(provider, ProviderStatus.AVAILABLE, metrics, from_cache=True)
