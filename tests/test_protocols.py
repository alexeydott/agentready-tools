from __future__ import annotations

from agentready.protocols import (
    PROTOCOL_MANIFEST,
    ProtocolStatus,
    audit_documents,
    to_agent_findings,
)


def test_manifest_pins_current_and_legacy_profiles_explicitly() -> None:
    versions = {(profile.id, profile.version): profile for profile in PROTOCOL_MANIFEST}

    assert ("openapi", "3.0") in versions
    assert ("openapi", "3.1") in versions
    assert ("openapi", "3.2") in versions
    assert versions[("a2a", "0.3")].deprecated is True
    assert versions[("a2a", "0.3")].compatibility_of == "a2a:1.0.0"
    assert versions[("webmcp", "experimental")].experimental is True


def test_protocol_findings_are_versioned_and_have_source_locators() -> None:
    findings = audit_documents(
        {
            "openapi@3.1": {"openapi": "3.1.0", "info": {}, "paths": {}},
            "oauth-protected-resource@RFC9728": {"resource": "https://example.test"},
        }
    )

    assert [item.status for item in findings] == [ProtocolStatus.PASS, ProtocolStatus.PASS]
    assert all(item.version for item in findings)
    assert all(item.evidence[0].source_id for item in findings)
    assert all(item.evidence[0].locator == "$" for item in findings)
    assert all(item.fingerprint == item.fingerprint for item in findings)


def test_legacy_profile_is_not_silently_current_and_missing_is_unavailable() -> None:
    findings = audit_documents({"a2a@0.3": {"name": "legacy", "url": "https://example.test"}, "mcp": None})

    legacy, unavailable = findings
    assert legacy.deprecated is True
    assert legacy.status is ProtocolStatus.PASS
    assert unavailable.status is ProtocolStatus.UNAVAILABLE
    assert unavailable.status not in {ProtocolStatus.FAIL, ProtocolStatus.WARN}


def test_protocol_audit_does_not_mutate_supplied_documents() -> None:
    document = {"openapi": "3.1.0", "info": {}, "paths": {}}
    before = document.copy()

    audit_documents({"openapi@3.1": document})

    assert document == before


def test_agent_adapter_is_additive_and_version_aware() -> None:
    findings = audit_documents({"mcp": {"protocolVersion": "2026-07-28"}})

    payload = to_agent_findings(findings)

    assert payload["schema"] == "agentready.protocol-findings.v1"
    assert payload["findings_count"] == 1
    assert payload["findings"][0]["profile_id"] == "mcp"
    assert payload["findings"][0]["version"] == "2026-07-28"
