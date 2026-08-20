from agentready.audit_core.store import MemorySiteStore, RunRecord
from agentready.metrics import ExternalMetric
from agentready.provider_executor import TrustedProviderExecutor
from agentready.provider_service import ProviderService
from agentready import credentials
import pytest


def test_trusted_executor_runs_injected_operation_and_persists_provenance():
    store = MemorySiteStore()
    store.begin_run(RunRecord("run-1", "config", "tool", "rules"))
    service = ProviderService(store, cache_ttl_seconds=60)
    resolved = []

    def resolve(config):
        resolved.append((config.origin, config.credential_ref))
        return ({}, object())

    async def operation(ref):
        assert ref == "vault:google"
        return (ExternalMetric("gsc", "clicks", 3, "count", "fixture", "v1", "2026-08-20T00:00:00+00:00"),)

    result = TrustedProviderExecutor(store, service=service, credential_resolver=resolve).execute(
        "run-1", "gsc", scope="https://example.test", credential_ref="vault:google", operation=operation
    )
    assert result.result.status.value == "available"
    assert result.to_dict()["credential_ref"] == "vault:google"
    assert any(key[0] == "run-1" and key[1].startswith("provider-cache:gsc:") for key in store._evidence)
    assert resolved == [("http://127.0.0.1", "vault:google")]


def test_trusted_executor_rejects_non_loopback_origin_before_operation():
    called = False

    async def operation(_):
        nonlocal called
        called = True
        return ()

    try:
        TrustedProviderExecutor(MemorySiteStore(), trusted_origin="https://remote.example").execute(
            "run-1", "ga4", scope="123", credential_ref="vault:google", operation=operation
        )
    except ValueError as exc:
        assert "loopback" in str(exc)
    else:
        raise AssertionError("remote origin must be rejected")
    assert not called


def test_remote_provider_request_has_no_credential_ref_field():
    from agentready.server import ProviderEnrichmentRequest

    assert "credential_ref" not in ProviderEnrichmentRequest.model_fields


def test_explicit_credential_ref_never_falls_back_to_default_credentials(monkeypatch):
    monkeypatch.setattr(credentials, "load_secret", lambda _reference: None)

    class FallbackKeyring:
        def get_password(self, _service, _account):
            return '{"type":"service_account","client_email":"fallback@example.test"}'

    monkeypatch.setattr(credentials, "_keyring", lambda: FallbackKeyring())
    with pytest.raises(credentials.CredentialsError, match="referenced credential was not found"):
        credentials.load_service_account_info("vault:missing")
