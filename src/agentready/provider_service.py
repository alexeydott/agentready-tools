"""Unified application boundary for opt-in external provider enrichment."""
from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlsplit

from .audit_core.store import SiteStore
from .metrics import (
    ExternalMetric,
    ProviderAdapter,
    ProviderConfig,
    ProviderJob,
    ProviderResult,
    ProviderRunBudget,
    ProviderScheduler,
    ProviderStatus,
    ga4_adapter,
    gsc_adapter,
    pagespeed_adapter,
    url_inspection_adapter,
)
from .query_service import MetricQuery, QueryService

logger = logging.getLogger(__name__)

Operation = Callable[[str | None], Awaitable[tuple[ExternalMetric, ...]]]


@dataclass(frozen=True, slots=True)
class ProviderCapability:
    provider: str
    version: str
    capabilities: tuple[str, ...]
    opt_in: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {"provider": self.provider, "version": self.version, "capabilities": list(self.capabilities), "opt_in": self.opt_in}


@dataclass(frozen=True, slots=True)
class ProviderServiceResult:
    result: ProviderResult
    collected_at: str
    expires_at: str
    stale: bool = False
    credential_ref: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = self.result.to_dict()
        payload["provenance"] = {"provider": self.result.provider, "version": self._version(), "collected_at": self.collected_at, "expires_at": self.expires_at, "fresh": not self.stale}
        if self.credential_ref:
            payload["credential_ref"] = self.credential_ref
        return payload

    def _version(self) -> str | None:
        return self.result.metrics[0].version if self.result.metrics else None


class ProviderService:
    """Own provider capabilities, budgets, cache policy, persistence and queries."""

    _FACTORIES = {
        "ga4": ga4_adapter,
        "gsc": gsc_adapter,
        "pagespeed": pagespeed_adapter,
        "url-inspection": url_inspection_adapter,
    }
    _CAPABILITIES = {
        "ga4": ("traffic", "engagement"),
        "gsc": ("search-performance",),
        "pagespeed": ("core-web-vitals",),
        "url-inspection": ("index-state",),
    }

    def __init__(self, store: SiteStore, *, cache_ttl_seconds: int = 900, scheduler: ProviderScheduler | None = None) -> None:
        if cache_ttl_seconds <= 0 or cache_ttl_seconds > 86_400:
            raise ValueError("provider cache TTL must be between 1 and 86400 seconds")
        self.store = store
        self.cache_ttl_seconds = cache_ttl_seconds
        self.scheduler = scheduler or ProviderScheduler(max_workers=2)

    @classmethod
    def capabilities(cls) -> tuple[ProviderCapability, ...]:
        return tuple(ProviderCapability(provider, "adapter-v1", capabilities) for provider, capabilities in sorted(cls._CAPABILITIES.items()))

    def adapter(self, provider: str, config: ProviderConfig) -> ProviderAdapter:
        try:
            return self._FACTORIES[provider](config)
        except KeyError as exc:
            raise ValueError("unsupported provider") from exc

    @classmethod
    def validate_scope(cls, provider: str, scope: str | None) -> str | None:
        """Validate a GA property or Search Console site scope without secrets."""
        if provider == "ga4":
            if scope is None or not (scope.isdigit() or (scope.startswith("properties/") and scope[10:].isdigit())):
                raise ValueError("GA4 scope must be a numeric property ID")
            return scope if scope.startswith("properties/") else f"properties/{scope}"
        if provider in {"gsc", "url-inspection"}:
            if scope is None:
                raise ValueError("Search Console scope is required")
            parsed = urlsplit(scope)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.username or parsed.password:
                raise ValueError("Search Console scope must be an HTTP(S) site URL without credentials")
            return f"{parsed.scheme.lower()}://{parsed.netloc.lower()}{parsed.path.rstrip('/')}" or f"{parsed.scheme.lower()}://{parsed.netloc.lower()}"
        return scope

    def enrich(
        self,
        run_id: str,
        provider: str,
        *,
        config: ProviderConfig,
        operation: Operation | None = None,
        cached: tuple[ExternalMetric, ...] | None = None,
        sample_urls: tuple[str, ...] = (),
        scope: str | None = None,
        metric_url_keys: tuple[str | None, ...] = (),
    ) -> ProviderServiceResult:
        normalized_scope = self.validate_scope(provider, scope) if provider in {"ga4", "gsc", "url-inspection"} else scope
        adapter = self.adapter(provider, config)
        scope_hash = hashlib.sha256(json.dumps({"provider": provider, "scope": normalized_scope, "urls": sorted(set(sample_urls))}, sort_keys=True).encode()).hexdigest()[:24]
        now = datetime.now(UTC)
        persisted = self._load_cache(run_id, provider, scope_hash, now)
        if persisted is not None and cached is None and operation is None:
            return persisted
        if cached is not None:
            operation = self._fixture_operation(cached)
        if operation is None:
            result = ProviderResult(provider, ProviderStatus.NOT_REQUESTED, detail="explicit provider operation is required")
        else:
            result = self.scheduler.run((ProviderJob(adapter, operation, cached=cached),), run_id=run_id)[0]
        collected = now.isoformat(timespec="seconds")
        expires = (now + timedelta(seconds=self.cache_ttl_seconds)).isoformat(timespec="seconds")
        service_result = ProviderServiceResult(result, collected, expires, credential_ref=config.credential_ref)
        self._persist(run_id, provider, scope_hash, service_result, metric_url_keys)
        logger.info("provider service completed provider=%s run_id=%s status=%s metrics=%d cache_ttl=%d", provider, run_id, result.status.value, len(result.metrics), self.cache_ttl_seconds)
        return service_result

    def query(self, run_id: str, *, provider: str | None = None, limit: int = 100, cursor: str | None = None) -> dict[str, Any]:
        page = QueryService(self.store).metrics(MetricQuery(run_id, provider=provider, limit=limit, cursor=cursor))
        return {"items": [item.__dict__ if hasattr(item, "__dict__") else {field: getattr(item, field) for field in item.__dataclass_fields__} for item in page.items], "next_cursor": page.next_cursor, "total": page.total}

    def _fixture_operation(self, metrics: tuple[ExternalMetric, ...]) -> Operation:
        async def operation(_: str | None) -> tuple[ExternalMetric, ...]:
            return metrics
        return operation

    def _load_cache(self, run_id: str, provider: str, scope_hash: str, now: datetime) -> ProviderServiceResult | None:
        payload = self.store.get_evidence(run_id, f"provider-cache:{provider}:{scope_hash}")
        if not payload or str(payload.get("expires_at", "")) <= now.isoformat(timespec="seconds"):
            return None
        metrics = tuple(ExternalMetric(item["provider"], item["name"], item.get("value"), item.get("unit"), item["source"], item["version"], item["observed_at"]) for item in payload.get("metrics", ()) if isinstance(item, Mapping))
        result = ProviderResult(provider, ProviderStatus(str(payload.get("status", ProviderStatus.AVAILABLE.value))), metrics, payload.get("detail"), payload.get("quota_remaining"), from_cache=True)
        return ProviderServiceResult(result, str(payload.get("collected_at")), str(payload.get("expires_at")), credential_ref=payload.get("credential_ref"))

    def _persist(self, run_id: str, provider: str, scope_hash: str, value: ProviderServiceResult, metric_url_keys: tuple[str | None, ...] = ()) -> None:
        for index, metric in enumerate(value.result.metrics):
            self.store.put_metric(metric.to_record(run_id, url_key=metric_url_keys[index] if index < len(metric_url_keys) else None))
        payload = value.result.to_dict()
        payload.update({"collected_at": value.collected_at, "expires_at": value.expires_at, "metrics": [item.to_dict() for item in value.result.metrics]})
        if value.credential_ref:
            payload["credential_ref"] = value.credential_ref
        self.store.put_evidence(run_id, f"provider-cache:{provider}:{scope_hash}", payload)
