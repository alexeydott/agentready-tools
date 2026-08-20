from agentready.audit_core import (
    FactEnvelope,
    FactCompatibility,
    FactSchemaRegistry,
    FactSchemaRequirement,
)
from agentready.audit_core.urls import UrlIdentity


def test_fact_schema_versions_handle_missing_old_new_and_unknown() -> None:
    registry = FactSchemaRegistry({"page": "2", "transport": "x"})

    assert registry.check(FactSchemaRequirement("page", "2")).compatibility is FactCompatibility.COMPATIBLE
    assert registry.check(FactSchemaRequirement("page", "1")).compatibility is FactCompatibility.COMPATIBLE
    assert registry.check(FactSchemaRequirement("page", "3")).compatibility is FactCompatibility.TOO_OLD
    assert registry.check(FactSchemaRequirement("missing", "1")).compatibility is FactCompatibility.MISSING
    assert registry.check(FactSchemaRequirement("transport", "1")).compatibility is FactCompatibility.UNKNOWN


def test_fact_schema_registry_can_declare_new_version_incompatible() -> None:
    registry = FactSchemaRegistry({"page": "2"}, incompatible=frozenset({("page", "2")}))
    result = registry.check(FactSchemaRequirement("page", "1"))
    assert result.compatibility is FactCompatibility.INCOMPATIBLE
    assert not result.usable


def test_fact_envelope_schema_identity_round_trips_and_conflicts_are_unknown() -> None:
    target = UrlIdentity.parse("https://example.test/")
    first = FactEnvelope("1", "title", target, "A", "2026-01-01", schema_family="page", schema_version="2")
    second = FactEnvelope("2", "title", target, "B", "2026-01-01", schema_family="page", schema_version="2")
    payload = first.to_dict()
    assert payload["schema_family"] == "page"
    assert payload["schema_version"] == "2"
    assert FactSchemaRegistry.from_envelopes((first, second)).versions == {"page": "2"}
    conflicting = FactEnvelope("3", "title", target, "C", "2026-01-01", schema_family="page", schema_version="3")
    assert FactSchemaRegistry.from_envelopes((first, conflicting)).versions == {"page": "unknown"}
    legacy = FactEnvelope("4", "legacy-title", target, "D", "2026-01-01")
    assert FactSchemaRegistry.from_envelopes((legacy,)).versions == {"legacy-title": "unknown"}
