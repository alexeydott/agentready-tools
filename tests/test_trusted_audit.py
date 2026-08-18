import pytest

from agentready.audit_service import AuditRequest
from agentready.egress import TrustedLocalCredentialContext
from agentready.trusted_audit import TrustedLocalAuditConfig


def test_trusted_origin_is_explicit_loopback_and_vault_reference(monkeypatch):
    monkeypatch.setattr("agentready.trusted_audit.load_secret", lambda reference: "fixture-secret")
    headers, context = TrustedLocalAuditConfig("http://127.0.0.1:8765", "fixture-ref").resolve()
    assert headers == {"Authorization": "Bearer fixture-secret"}
    assert context.permits("http://127.0.0.1:8765/")
    assert not context.permits("http://127.0.0.1:8766/")


def test_trusted_origin_rejects_public_and_path_targets():
    with pytest.raises(ValueError, match="loopback"):
        TrustedLocalAuditConfig("https://example.test", "ref")
    with pytest.raises(ValueError, match="must not contain"):
        TrustedLocalAuditConfig("http://127.0.0.1:8765/private", "ref")


def test_audit_request_requires_resolved_context_and_disallows_render():
    context = TrustedLocalCredentialContext(
        credential_ref="ref",
        allowed_headers=frozenset({"authorization"}),
        allowed_origins=frozenset({"http://127.0.0.1:8765"}),
    )
    with pytest.raises(ValueError, match="headers"):
        AuditRequest("http://127.0.0.1:8765/", trusted_origin="http://127.0.0.1:8765", security_context=context)
    with pytest.raises(ValueError, match="rendered"):
        AuditRequest("http://127.0.0.1:8765/", render=True, trusted_origin="http://127.0.0.1:8765", credential_headers={"Authorization": "x"}, security_context=context)


def test_audit_request_configuration_contains_reference_only():
    request = AuditRequest(
        "http://127.0.0.1:8765/",
        trusted_origin="http://127.0.0.1:8765",
        credential_ref="fixture-ref",
        credential_headers={"Authorization": "Bearer fixture-secret"},
        security_context=TrustedLocalCredentialContext(
            credential_ref="fixture-ref",
            allowed_headers=frozenset({"authorization"}),
            allowed_origins=frozenset({"http://127.0.0.1:8765"}),
        ),
    )
    configuration = request.configuration()
    assert configuration["credential_ref"] == "fixture-ref"
    assert "fixture-secret" not in str(configuration)
