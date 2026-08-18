from datetime import UTC, datetime

from agentready.audit_core.store import MemorySiteStore, RunRecord
from agentready.metrics import ExternalMetric, ProviderConfig
from agentready.provider_service import ProviderService


def test_provider_service_capabilities_are_explicit_and_sorted():
    capabilities = ProviderService.capabilities()
    assert [item.provider for item in capabilities] == ["ga4", "gsc", "pagespeed", "url-inspection"]
    assert all(item.opt_in for item in capabilities)


def test_provider_service_persists_provenance_and_reuses_fresh_cache():
    store = MemorySiteStore()
    store.begin_run(RunRecord("run-1", "config", "tool", "rules"))
    metric = ExternalMetric("pagespeed", "lcp", 1200, "ms", "fixture", "psi-v5", datetime.now(UTC).isoformat())
    service = ProviderService(store, cache_ttl_seconds=60)
    first = service.enrich("run-1", "pagespeed", config=ProviderConfig(), cached=(metric,), sample_urls=("https://example.test/",))
    second = service.enrich("run-1", "pagespeed", config=ProviderConfig(), sample_urls=("https://example.test/",))
    assert first.result.from_cache
    assert second.result.from_cache
    assert second.to_dict()["provenance"]["fresh"]
    assert service.query("run-1", provider="pagespeed")["items"][0]["name"] == "lcp"


def test_provider_service_requires_explicit_operation_and_never_persists_secret_value():
    store = MemorySiteStore()
    store.begin_run(RunRecord("run-1", "config", "tool", "rules"))
    service = ProviderService(store)
    result = service.enrich("run-1", "gsc", config=ProviderConfig(credential_ref="vault:gsc"))
    assert result.result.status.value == "not_requested"
    assert result.to_dict()["credential_ref"] == "vault:gsc"
    assert "secret_value" not in str(result.to_dict())
