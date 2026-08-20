"""Trusted local execution for Google provider enrichment.

The HTTP API and MCP surfaces intentionally accept only saved observations.
This module is the narrow CLI/loopback boundary that may resolve a vault
reference and invoke the optional Google clients.  The secret itself never
crosses the ProviderService result or is written to the SiteStore.
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from .audit_core.store import SiteStore
from .ga_gsc import ga_pages_without_traffic, gsc_pages_without_clicks
from .metrics import ExternalMetric, ProviderConfig
from .provider_service import ProviderService, ProviderServiceResult
from .trusted_audit import TrustedLocalAuditConfig

MetricOperation = Callable[[str | None], Awaitable[tuple[ExternalMetric, ...]]]
CredentialResolver = Callable[[TrustedLocalAuditConfig], Any]


@dataclass(frozen=True, slots=True)
class TrustedProviderExecutor:
    """Execute one bounded GA4/GSC operation from a trusted local caller."""

    store: SiteStore
    trusted_origin: str = "http://127.0.0.1"
    credential_resolver: CredentialResolver | None = None
    service: ProviderService | None = None

    def execute(
        self,
        run_id: str,
        provider: str,
        *,
        scope: str,
        credential_ref: str,
        days: int = 28,
        operation: MetricOperation | None = None,
    ) -> ProviderServiceResult:
        """Run and persist a provider operation after trusted-boundary checks.

        ``operation`` is intentionally injectable for deterministic tests and
        local wrappers.  Production callers omit it and use the existing
        Google clients, which resolve the same vault reference internally.
        """
        if provider not in {"ga4", "gsc"}:
            raise ValueError("trusted Google executor supports only ga4 and gsc")
        if days <= 0 or days > 365:
            raise ValueError("provider lookback must be between 1 and 365 days")
        config = TrustedLocalAuditConfig(self.trusted_origin, credential_ref)
        resolver = self.credential_resolver or (lambda item: item.resolve())
        # Resolving here proves this code is on the trusted local path.  The
        # returned headers/context are deliberately discarded.
        resolver(config)
        selected_operation = operation or self._operation(provider, scope, days)
        service = self.service or ProviderService(self.store)
        return service.enrich(
            run_id,
            provider,
            config=ProviderConfig(enabled=True, explicit_operation=True, quota=1, credential_ref=credential_ref),
            operation=selected_operation,
            scope=scope,
        )

    @staticmethod
    def _operation(provider: str, scope: str, days: int) -> MetricOperation:
        async def operation(credential_ref: str | None) -> tuple[ExternalMetric, ...]:
            if provider == "ga4":
                rows = ga_pages_without_traffic(scope.removeprefix("properties/"), days, credential_ref=credential_ref)
                return tuple(
                    ExternalMetric("ga4", "sessions", row.get("sessions", 0), "count", "ga4-data-api", "data-api-v1beta", "now")
                    for row in rows
                )
            rows = gsc_pages_without_clicks(scope, days, credential_ref=credential_ref)
            return tuple(
                metric
                for row in rows
                for metric in (
                    ExternalMetric("gsc", "impressions", row.get("impressions", 0), "count", "search-console", "search-console-v1", "now"),
                    ExternalMetric("gsc", "clicks", row.get("clicks", 0), "count", "search-console", "search-console-v1", "now"),
                )
            )

        return operation
