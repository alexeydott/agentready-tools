import json
from pathlib import Path

import pytest

from agentready.audit_core import (
    Applicability,
    AuditCoverage,
    AuthorityLevel,
    EvaluationCompleteness,
    Evidence,
    RequirementLevel,
    RuleSpec,
    RuleVersion,
    ScoreParticipation,
    UrlIdentity,
    fingerprint,
)


def test_rule_contract_separates_authority_and_score_participation():
    rule = RuleSpec(
        id="robots-txt",
        title="robots.txt",
        category="discoverability",
        authority=AuthorityLevel.STANDARD,
        requirement=RequirementLevel.REQUIRED,
        version=RuleVersion("1.0.0", "2026-08-10"),
    )
    assert rule.to_dict()["score_participation"] == ScoreParticipation.INCLUDED.value
    with pytest.raises(ValueError, match="heuristic"):
        RuleSpec(
            id="heuristic",
            title="heuristic",
            category="quality",
            authority=AuthorityLevel.HEURISTIC,
            requirement=RequirementLevel.SUPPLEMENTAL,
            version=RuleVersion("1.0.0", "2026-08-10"),
        )


def test_url_identity_preserves_original_and_normalizes_host():
    identity = UrlIdentity.parse("HTTPS://Example.com:443/docs?a=1#part")
    assert identity.lossless() == "HTTPS://Example.com:443/docs?a=1#part"
    assert identity.normalized() == "https://example.com:443/docs?a=1#part"
    assert identity.origin.to_string() == "https://example.com:443"


def test_url_identity_covers_encoding_default_port_and_fetch_fragment_split():
    identity = UrlIdentity.parse("https://EXAMPLE.com:443/a%2Fb?x=1#section")
    assert identity.origin.to_string() == "https://example.com:443"
    assert identity.normalized() == "https://example.com:443/a%2Fb?x=1#section"
    assert identity.normalized().split("#", 1)[0] == "https://example.com:443/a%2Fb?x=1"


def test_fingerprint_is_deterministic_and_redacts_secret_inputs():
    target = UrlIdentity.parse("https://example.com/a")
    first = fingerprint("robots-txt", "1.0.0", target, {"authorization": "secret", "status": 200})
    second = fingerprint("robots-txt", "1.0.0", target, {"status": 200, "authorization": "other"})
    assert first == second


def test_coverage_rejects_ambiguous_denominators():
    with pytest.raises(ValueError, match="monotonically"):
        AuditCoverage(total_rules=1, evaluated_rules=2, applicable_rules=1, complete_rules=1)


def test_evidence_serialization_contains_header_names_only():
    evidence = Evidence(
        action="fetch",
        target=UrlIdentity.parse("https://example.com"),
        finding="ok",
        header_names=("Authorization", "Content-Type"),
    )
    payload = evidence.to_dict()
    assert payload["header_names"] == ["Authorization", "Content-Type"]
    assert "headers" not in payload


def test_v2_schema_is_valid_json_and_declares_stable_id():
    schema_path = Path(__file__).parents[1] / "schemas" / "agentready.audit.v2.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    assert schema["$id"].endswith("agentready.audit.v2.schema.json")
    assert schema["properties"]["schema"]["const"] == "agentready.audit.v2"


def test_canonical_audit_payload_validates_against_published_schema():
    jsonschema = pytest.importorskip("jsonschema")
    from agentready.report_v2 import AuditReport, Coverage, Finding, FindingStatus

    schema_path = Path(__file__).parents[1] / "schemas" / "agentready.audit.v2.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    payload = AuditReport(
        "https://example.test",
        (Finding("robots", "Robots", FindingStatus.PASS, "ok"),),
        Coverage(1, 1, 1, 1),
    ).to_dict()

    jsonschema.Draft202012Validator(schema).validate(payload)


def test_published_seo_and_mobile_schemas_validate_current_serializers():
    jsonschema = pytest.importorskip("jsonschema")
    from agentready.mobile_models import MobileReport
    from agentready.seo_models import SeoReport

    root = Path(__file__).parents[1] / "schemas"
    payloads = (
        (root / "agentready.seo.v2.schema.json", SeoReport(
            "agentready.seo.v2",
            "https://example.test/",
            "https://example.test",
            [],
            0,
            [],
            [],
            "2026-01-01T00:00:00Z",
            "2026-01-01T00:00:01Z",
        ).to_dict()),
        (root / "agentready.mobile.v2.schema.json", MobileReport(
            "agentready.mobile.v2",
            ["https://example.test/"],
            [],
            0,
            [],
            [],
            "2026-01-01T00:00:00Z",
            "2026-01-01T00:00:01Z",
        ).to_dict()),
    )

    for schema_path, payload in payloads:
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        jsonschema.Draft202012Validator(schema).validate(payload)


def test_core_modules_do_not_import_transport_adapters():
    package = Path(__file__).parents[1] / "src" / "agentready" / "audit_core"
    forbidden = ("agentready.cli", "agentready.server", "agentready.mcp_server", "tests.")
    for path in package.glob("*.py"):
        source = path.read_text(encoding="utf-8")
        assert not any(item in source for item in forbidden), path


def test_contract_enums_keep_applicability_and_completeness_separate():
    assert Applicability.UNKNOWN != EvaluationCompleteness.NOT_EVALUATED
