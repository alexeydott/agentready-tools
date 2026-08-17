from __future__ import annotations

from agentready.protocols import (
    PROTOCOL_MANIFEST,
    ProtocolStatus,
    audit_documents,
    to_agent_findings,
)
from agentready.protocols.models import ProtocolEvidence, ProtocolFinding


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
    assert findings[0].to_contract("https://example.test/").key.rule_version == findings[0].version


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

    payload = to_agent_findings(findings, target="https://example.com/")

    assert payload["schema"] == "agentready.protocol-findings.v2"
    assert payload["findings_count"] == 1
    assert payload["findings"][0]["profile_id"] == "mcp"
    assert payload["findings"][0]["version"] == "2026-07-28"
    assert "canonical_findings" not in payload


def test_protocol_fingerprint_is_stable_across_localized_copy() -> None:
    evidence_en = ProtocolEvidence("source", "$.paths", "English summary")
    evidence_ru = ProtocolEvidence("source", "$.paths", "Russian summary")
    finding_en = ProtocolFinding(
        "openapi",
        "3.1",
        ProtocolStatus.FAIL,
        "English title",
        "English reason",
        (evidence_en,),
    )
    finding_ru = ProtocolFinding(
        "openapi",
        "3.1",
        ProtocolStatus.FAIL,
        "Russian title",
        "Russian reason",
        (evidence_ru,),
    )

    assert finding_en.fingerprint == finding_ru.fingerprint
