"""Opt-in external metrics and performance integration contracts.

This module deliberately does not participate in the normal scan path.
Provider calls require explicit configuration and an explicit operation from
the caller; credentials are represented only by an OS-vault reference.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from collections.abc import Awaitable, Callable, Mapping
from concurrent.futures import ThreadPoolExecutor
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
    CANCELLED = "cancelled"


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


@dataclass(frozen=True, slots=True)
class ProviderBudgetSnapshot:
    """Immutable counters exposed after one scheduler run."""

    reserved: int
    started: int
    released: int
    exhausted: int


class ProviderRunBudget:
    """Thread-safe reservation ledger owned by ``ProviderScheduler``."""

    def __init__(
        self,
        *,
        total: int | None = None,
        per_provider: Mapping[str, int] | None = None,
    ) -> None:
        if total is not None and total < 0:
            raise ValueError("provider total budget cannot be negative")
        limits = dict(per_provider or {})
        if any(not provider or limit < 0 for provider, limit in limits.items()):
            raise ValueError("provider budgets require non-empty providers and non-negative limits")
        self.total = total
        self.per_provider = limits
        self._lock = threading.Lock()
        self._reserved: dict[tuple[str, str], int] = {}
        self._started: dict[tuple[str, str], int] = {}
        self._released: dict[tuple[str, str], int] = {}
        self._exhausted: dict[str, int] = {}

    def reserve(self, provider: str, *, cached: bool = False, run_id: str = "") -> bool:
        """Reserve one external call atomically before worker submission."""
        if cached:
            return True
        with self._lock:
            scope = (run_id, provider)
            provider_reserved = self._reserved.get(scope, 0)
            provider_limit = self.per_provider.get(provider)
            total_reserved = sum(value for (scope_id, _), value in self._reserved.items() if scope_id == run_id)
            if provider_limit is not None and provider_reserved >= provider_limit:
                self._exhausted[run_id] = self._exhausted.get(run_id, 0) + 1
                return False
            if self.total is not None and total_reserved >= self.total:
                self._exhausted[run_id] = self._exhausted.get(run_id, 0) + 1
                return False
            self._reserved[scope] = provider_reserved + 1
            return True

    def mark_started(self, provider: str, *, run_id: str = "") -> None:
        with self._lock:
            scope = (run_id, provider)
            self._started[scope] = self._started.get(scope, 0) + 1

    def release(self, provider: str, *, run_id: str = "") -> None:
        """Return a reservation cancelled before the external call starts."""
        with self._lock:
            scope = (run_id, provider)
            current = self._reserved.get(scope, 0)
            if current <= 0:
                raise RuntimeError("cannot release an unreserved provider budget")
            self._reserved[scope] = current - 1
            self._released[scope] = self._released.get(scope, 0) + 1

    def remaining(self, provider: str, *, run_id: str = "") -> int | None:
        with self._lock:
            limits = [
                limit - self._reserved.get((run_id, provider), 0)
                for limit in (self.per_provider.get(provider), self.total)
                if limit is not None
            ]
            return max(0, min(limits)) if limits else None

    def snapshot(self) -> ProviderBudgetSnapshot:
        with self._lock:
            return ProviderBudgetSnapshot(
                reserved=sum(self._reserved.values()),
                started=sum(self._started.values()),
                released=sum(self._released.values()),
                exhausted=sum(self._exhausted.values()),
            )


class ExternalMetricProvider(Protocol):
    """Normalized provider contract for opt-in external enrichment."""

    provider: str
    version: str
    config: ProviderConfig

    def run(
        self,
        operation: Callable[[str | None], Awaitable[tuple[ExternalMetric, ...]]],
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
        operation: Callable[[str | None], Awaitable[tuple[ExternalMetric, ...]]],
        *,
        cached: tuple[ExternalMetric, ...] | None = None,
        quota_reserved: bool = False,
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
        if self.config.quota == 0 and not quota_reserved:
            return ProviderResult(self.provider, ProviderStatus.QUOTA_EXCEEDED, detail="provider quota exhausted", quota_remaining=0)
        started = time.monotonic()

        async def invoke() -> tuple[ExternalMetric, ...]:
            return await asyncio.wait_for(
                operation(self.config.credential_ref),
                timeout=self.config.timeout_seconds,
            )

        try:
            metrics = asyncio.run(invoke())
        except TimeoutError:
            logger.warning("[FIX:provider-timeout] provider operation exceeded timeout provider=%s timeout=%.3f", self.provider, self.config.timeout_seconds)
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
    operation: Callable[[str | None], Awaitable[tuple[ExternalMetric, ...]]]
    cached: tuple[ExternalMetric, ...] | None = None
    cancelled: bool = False


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

    def __init__(self, *, max_workers: int = 2, budget: ProviderRunBudget | None = None) -> None:
        if max_workers <= 0 or max_workers > 16:
            raise ValueError("provider scheduler workers must be between 1 and 16")
        self.max_workers = max_workers
        self.budget = budget

    def run(self, jobs: tuple[ProviderJob, ...] | list[ProviderJob], *, run_id: str = "") -> tuple[ProviderResult, ...]:
        ordered_jobs = tuple(jobs)
        if not ordered_jobs:
            return ()
        budget = self.budget or self._budget_for(ordered_jobs)
        results: dict[int, ProviderResult] = {}
        pending: list[tuple[int, ProviderJob]] = []
        for index, job in enumerate(ordered_jobs):
            if job.cancelled:
                results[index] = ProviderResult(
                    job.adapter.provider,
                    ProviderStatus.CANCELLED,
                    detail="cancelled before provider request",
                )
            elif job.cached is not None:
                results[index] = job.adapter.run(job.operation, cached=job.cached)
            elif job.adapter.config.quota == 0:
                results[index] = ProviderResult(
                    job.adapter.provider,
                    ProviderStatus.QUOTA_EXCEEDED,
                    detail="provider quota exhausted",
                    quota_remaining=0,
                )
            elif not budget.reserve(job.adapter.provider, run_id=run_id):
                results[index] = ProviderResult(
                    job.adapter.provider,
                    ProviderStatus.QUOTA_EXCEEDED,
                    detail="provider run budget exhausted",
                    quota_remaining=budget.remaining(job.adapter.provider, run_id=run_id),
                )
            else:
                pending.append((index, job))

        def execute(job: ProviderJob) -> ProviderResult:
            budget.mark_started(job.adapter.provider, run_id=run_id)
            result = job.adapter.run(job.operation, quota_reserved=True)
            return ProviderResult(
                result.provider,
                result.status,
                result.metrics,
                result.detail,
                budget.remaining(result.provider, run_id=run_id),
                result.from_cache,
            )

        with ThreadPoolExecutor(max_workers=min(self.max_workers, max(1, len(pending)))) as pool:
            futures = [(index, pool.submit(execute, job)) for index, job in pending]
            for index, future in futures:
                results[index] = future.result()
        snapshot = budget.snapshot()
        logger.info(
            "[FIX:provider-budget] provider scheduler complete run_id=%s jobs=%d started=%d exhausted=%d released=%d",
            run_id,
            len(ordered_jobs),
            snapshot.started,
            snapshot.exhausted,
            snapshot.released,
        )
        return tuple(results[index] for index in range(len(ordered_jobs)))

    @staticmethod
    def _budget_for(jobs: tuple[ProviderJob, ...]) -> ProviderRunBudget:
        limits: dict[str, int] = {}
        for job in jobs:
            if job.cancelled or job.cached is not None or job.adapter.config.quota == 0:
                continue
            current = limits.get(job.adapter.provider)
            quota = job.adapter.config.quota
            # The provider, not the adapter instance, owns the run quota.  A
            # caller may construct multiple adapters for the same provider;
            # those instances must still share one global cap.
            limits[job.adapter.provider] = quota if current is None else min(current, quota)
        return ProviderRunBudget(total=sum(limits.values()), per_provider=limits)

    def run_for_urls(
        self,
        run_id: str,
        adapter: ProviderAdapter,
        operation: Callable[[str, str | None], Awaitable[tuple[ExternalMetric, ...]]],
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
        cached_results: dict[str, ProviderResult] = {}
        pending_urls: list[str] = []
        stored_metrics = tuple(store.iter_metrics(run_id))
        for url in urls:
            evidence_id = f"provider:{adapter.provider}:{url}"
            payload = store.get_evidence(run_id, evidence_id)
            if payload is not None and payload.get("status") != "pending":
                cached_results[url] = self._cached_result(adapter.provider, payload, stored_metrics, url)
                continue
            if not store.claim_evidence(run_id, evidence_id):
                deadline = time.monotonic() + max(1.0, adapter.config.timeout_seconds + 1.0)
                while time.monotonic() < deadline:
                    payload = store.get_evidence(run_id, evidence_id)
                    if payload is not None and payload.get("status") != "pending":
                        cached_results[url] = self._cached_result(
                            adapter.provider, payload, tuple(store.iter_metrics(run_id)), url
                        )
                        break
                    time.sleep(0.01)
                else:
                    cached_results[url] = ProviderResult(
                        adapter.provider,
                        ProviderStatus.UNAVAILABLE,
                        detail="provider result is in flight",
                        from_cache=True,
                    )
                continue
            store.put_evidence(run_id, evidence_id, {"provider": adapter.provider, "status": "pending"})
            # A stale pending claim is reclaimed by claim_evidence(), which
            # removes the old payload.  It must follow the same fresh-work
            # path as a first-seen URL; otherwise fresh_by_url lacks the URL.
            pending_urls.append(url)
            logger.info("[FIX:provider-resume] scheduled fresh provider evidence url=%s", url)
        def job_for(url: str) -> ProviderJob:
            async def invoke(credential: str | None) -> tuple[ExternalMetric, ...]:
                return await operation(url, credential)

            return ProviderJob(adapter, invoke)

        jobs = [job_for(url) for url in pending_urls]
        try:
            fresh_results = self.run(jobs, run_id=run_id)
        except Exception:
            for url in pending_urls:
                store.release_evidence_claim(run_id, f"provider:{adapter.provider}:{url}")
            raise
        fresh_by_url = dict(zip(pending_urls, fresh_results))
        results: list[ProviderResult] = []
        for url in urls:
            result = cached_results.get(url) or fresh_by_url[url]
            results.append(result)
            if url in cached_results:
                continue
            evidence_id = f"provider:{result.provider}:{url}"
            try:
                for metric in result.metrics:
                    store.put_metric(metric.to_record(run_id, url_key=url))
                store.put_evidence(
                    run_id,
                    evidence_id,
                    {
                        "provider": result.provider,
                        "status": result.status.value,
                        "quota_remaining": result.quota_remaining,
                        "from_cache": result.from_cache,
                        "detail": result.detail,
                    },
                )
            finally:
                store.release_evidence_claim(run_id, evidence_id)
        return tuple(results)

    @staticmethod
    def _cached_result(
        provider: str,
        payload: Mapping[str, Any],
        stored_metrics: tuple[MetricRecord, ...],
        url: str,
    ) -> ProviderResult:
        metrics = tuple(metric for metric in stored_metrics if metric.url_key == url and metric.provider == provider)
        return ProviderResult(
            provider,
            ProviderStatus(str(payload.get("status", ProviderStatus.UNAVAILABLE.value))),
            tuple(
                ExternalMetric(
                    metric.provider, metric.name, metric.value, metric.unit, metric.source,
                    metric.version, metric.observed_at, MetricKind(metric.kind),
                )
                for metric in metrics
            ),
            detail=payload.get("detail"),
            quota_remaining=payload.get("quota_remaining"),
            from_cache=True,
        )


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
