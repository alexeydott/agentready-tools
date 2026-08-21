"""Stage D integrity/packaging/compatibility gates (#21).

Ties D1-D4 (#17-#20) together as one focused, deterministic, offline
catalog-integrity suite intended to run in the minimal CI profile (no
browser/provider extras) so catalog corruption or partial integration
cannot be merged unnoticed.

Negative fixtures below each construct an intentionally-invalid document
or snapshot and assert the appropriate loader/crosswalk validation raises,
proving every major validation rule can actually fail (not just pass on
the one golden catalog).
"""
from __future__ import annotations

import ast
import copy
from dataclasses import replace
from pathlib import Path

import pytest

from agentready.audit_core.rule_catalog import load_rule_catalog_snapshot
from agentready.seo.rules.catalog import (
    CATALOG_SCHEMA_ID,
    RuleCatalogValidationError,
    validate_catalog_document,
)
from agentready.seo.rule_crosswalk import validate_crosswalk_against_snapshot

ROOT = Path(__file__).parents[1]
SOURCE = ROOT / "src" / "agentready"


def _valid_document() -> dict[str, object]:
    return {
        "schema": CATALOG_SCHEMA_ID,
        "catalog_version": "2.1.0-draft.1",
        "generated_at": "2026-08-21T00:00:00Z",
        "rule_count": 2,
        "modules": [{"id": "demo", "count": 2}],
        "source_registry": {"demo-source": {"title": "Demo source", "url": "https://example.test/demo"}},
        "rules": [
            {
                "rule_id": "DEMO-001",
                "version": "1.0.0",
                "title": "Demo rule one",
                "module": "demo",
                "applicability": {"applies_to": "html-page", "condition": "always"},
                "fact_requirements": [{"family": "page", "min_schema_version": "1"}],
                "source_ids": ["demo-source"],
                "score_role": "scored",
                "failure_policy": "block_on_missing_facts",
                "summary": "Demo rule one summary.",
                "mechanism": "atomic_check",
                "rule_kind": "scored_rule",
                "automation_mode": "automated",
                "profiles": ["default"],
                "comparison_dimensions": ["page"],
                "verification_plan": "Collect page fact(s) and evaluate demo rule one.",
            },
            {
                "rule_id": "DEMO-002",
                "version": "1.0.0",
                "title": "Demo rule two",
                "module": "demo",
                "applicability": {"applies_to": "html-page", "condition": "always"},
                "fact_requirements": [{"family": "page", "min_schema_version": "1"}],
                "source_ids": ["demo-source"],
                "score_role": "scored",
                "failure_policy": "block_on_missing_facts",
                "summary": "Demo rule two summary.",
                "mechanism": "atomic_check",
                "rule_kind": "scored_rule",
                "automation_mode": "automated",
                "profiles": ["default"],
                "comparison_dimensions": ["page"],
                "verification_plan": "Collect page fact(s) and evaluate demo rule two.",
            },
        ],
    }


def test_baseline_fixture_document_is_valid():
    """Sanity check: the negative-fixture baseline itself passes before mutation."""
    validate_catalog_document(_valid_document())


def test_negative_fixture_duplicate_rule_id():
    document = _valid_document()
    document["rules"][1]["rule_id"] = "DEMO-001"  # type: ignore[index]
    with pytest.raises(RuleCatalogValidationError, match="duplicate rule_id"):
        validate_catalog_document(document)


def test_negative_fixture_malformed_rule_id_pattern():
    document = _valid_document()
    document["rules"][0]["rule_id"] = "demo-lowercase-not-allowed"  # type: ignore[index]
    with pytest.raises(RuleCatalogValidationError, match="does not match required pattern"):
        validate_catalog_document(document)


def test_negative_fixture_malformed_version_not_semver():
    document = _valid_document()
    document["rules"][0]["version"] = "v1"  # type: ignore[index]
    with pytest.raises(RuleCatalogValidationError, match="does not match required"):
        validate_catalog_document(document)


def test_negative_fixture_incorrect_total_rule_count():
    document = _valid_document()
    document["rule_count"] = 3
    with pytest.raises(RuleCatalogValidationError, match="does not match number of rules"):
        validate_catalog_document(document)


def test_negative_fixture_incorrect_module_count():
    document = _valid_document()
    document["modules"][0]["count"] = 1  # type: ignore[index]
    with pytest.raises(RuleCatalogValidationError, match="declares count"):
        validate_catalog_document(document)


def test_negative_fixture_unknown_source_id():
    document = _valid_document()
    document["rules"][0]["source_ids"] = ["no-such-source"]  # type: ignore[index]
    with pytest.raises(RuleCatalogValidationError, match="unknown source_id"):
        validate_catalog_document(document)


def test_negative_fixture_missing_fact_schema_version():
    document = _valid_document()
    del document["rules"][0]["fact_requirements"][0]["min_schema_version"]  # type: ignore[index]
    with pytest.raises(RuleCatalogValidationError, match="fact_requirements item must have"):
        validate_catalog_document(document)


def test_negative_fixture_invalid_score_role():
    document = _valid_document()
    document["rules"][0]["score_role"] = "not-a-real-role"  # type: ignore[index]
    with pytest.raises(RuleCatalogValidationError, match="score_role must be one of"):
        validate_catalog_document(document)


def test_negative_fixture_invalid_failure_policy():
    document = _valid_document()
    document["rules"][0]["failure_policy"] = "not-a-real-policy"  # type: ignore[index]
    with pytest.raises(RuleCatalogValidationError, match="failure_policy must be one of"):
        validate_catalog_document(document)


def test_negative_fixture_invalid_mechanism():
    document = _valid_document()
    document["rules"][0]["mechanism"] = "not-a-real-mechanism"  # type: ignore[index]
    with pytest.raises(RuleCatalogValidationError, match="mechanism must be one of"):
        validate_catalog_document(document)


def test_negative_fixture_invalid_rule_kind():
    document = _valid_document()
    document["rules"][0]["rule_kind"] = "not-a-real-kind"  # type: ignore[index]
    with pytest.raises(RuleCatalogValidationError, match="rule_kind must be one of"):
        validate_catalog_document(document)


def test_negative_fixture_invalid_automation_mode():
    document = _valid_document()
    document["rules"][0]["automation_mode"] = "not-a-real-mode"  # type: ignore[index]
    with pytest.raises(RuleCatalogValidationError, match="automation_mode must be one of"):
        validate_catalog_document(document)


def test_negative_fixture_unsupported_applicability_mode_yields_unknown_not_error():
    """Unsupported applicability *expressions* are a runtime projection concern
    (#19), not a catalog-schema validation failure: the catalog schema only
    requires applies_to/condition strings to be present. This fixture proves
    the projection layer treats an unrecognized condition as UNKNOWN rather
    than silently ALWAYS -- see test_rule_projection.py for the exhaustive
    coverage; this is the integrity-suite cross-check tying #19 into this
    gate."""
    from agentready.audit_core.models import Applicability
    from agentready.audit_core.rule_projection import (
        ApplicabilityContext,
        ApplicabilityMode,
        resolve_applicability,
    )
    from agentready.audit_core.rule_catalog import load_rule_catalog_snapshot
    from agentready.audit_core.rule_projection import parse_applicability_expression

    snapshot = load_rule_catalog_snapshot()
    entry = snapshot.entries[0]
    mutated_entry = replace(entry, condition="an unrecognized hand-authored condition string")
    expression = parse_applicability_expression(mutated_entry)
    assert expression.mode is ApplicabilityMode.UNSUPPORTED
    assert resolve_applicability(expression, ApplicabilityContext(subject_kind=entry.scope)) is Applicability.UNKNOWN


def test_negative_fixture_stale_crosswalk_reference():
    snapshot = load_rule_catalog_snapshot()
    stale_entries = tuple(entry for entry in snapshot.entries if entry.rule_id != "GOOGLE-TITLE-001")
    stale_snapshot = replace(snapshot, entries=stale_entries)
    with pytest.raises(ValueError, match="unknown frozen rule id"):
        validate_crosswalk_against_snapshot(stale_snapshot)


def test_negative_fixture_missing_top_level_key():
    document = _valid_document()
    del document["source_registry"]
    with pytest.raises(RuleCatalogValidationError, match="missing required top-level key"):
        validate_catalog_document(document)


def test_negative_fixture_undeclared_module_reference():
    document = _valid_document()
    document["rules"][0]["module"] = "undeclared-module"  # type: ignore[index]
    with pytest.raises(RuleCatalogValidationError, match="is not declared in modules"):
        validate_catalog_document(document)


# --- CI-time validation of the real packaged catalog (#21 work-plan item 4) --


def test_current_packaged_catalog_passes_full_integrity_gate():
    """One deterministic, offline pass validating the real packaged artifact
    against every rule the negative fixtures above individually attack:
    schema/version metadata, exact rule count, module counts, unique
    IDs/versions, source-registry references, fact-requirement versions,
    supported enum values, crosswalk references, and applicability support."""
    snapshot = load_rule_catalog_snapshot()
    assert snapshot.schema == CATALOG_SCHEMA_ID
    assert snapshot.catalog_version == "2.1.0-draft.1"
    assert snapshot.rule_count == 200
    assert sum(snapshot.module_counts.values()) == 200

    rule_ids = [entry.rule_id for entry in snapshot.entries]
    assert len(rule_ids) == len(set(rule_ids))

    from agentready.audit_core.rule_projection import (
        ApplicabilityMode,
        parse_applicability_expression,
    )

    for entry in snapshot.entries:
        assert entry.score_role in {"scored", "diagnostic", "observation_only"}
        assert entry.failure_policy in {"block_on_missing_facts", "unknown_on_missing_facts"}
        for requirement in entry.fact_requirements:
            assert requirement.min_schema_version
        expression = parse_applicability_expression(entry)
        assert expression.mode is ApplicabilityMode.ALWAYS_FOR_SUBJECT

    # Compatibility gate: crosswalk references only rule IDs present in the
    # exact snapshot just loaded -- a changed catalog digest/version cannot
    # ship with a stale crosswalk without this failing.
    validate_crosswalk_against_snapshot(snapshot)


# --- architecture gate: catalog code stays free of transport/browser/provider --


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    result: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            result.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            result.add(node.module.split(".", 1)[0])
    return result


CATALOG_STACK_PATHS = [
    SOURCE / "audit_core" / "rule_catalog.py",
    SOURCE / "audit_core" / "rule_projection.py",
    SOURCE / "seo" / "rule_crosswalk.py",
    SOURCE / "seo" / "rules" / "catalog" / "loader.py",
    SOURCE / "seo" / "rules" / "catalog" / "__init__.py",
]


def test_catalog_stack_has_no_transport_browser_or_provider_imports():
    forbidden = {"http", "httpx", "playwright", "sqlite3", "requests", "cli", "server", "mcp_server"}
    offenders = {
        path.relative_to(SOURCE).as_posix(): sorted(_imports(path) & forbidden)
        for path in CATALOG_STACK_PATHS
        if _imports(path) & forbidden
    }
    assert offenders == {}


def test_catalog_stack_tests_require_no_network_provider_or_browser_fixtures():
    """The whole D1-D4 integrity/negative-fixture suite must be collectible and
    runnable with no network/browser/provider extras -- i.e. everything this
    module imports is already part of the minimal install profile."""
    forbidden_test_modules = {"playwright", "httpx"}
    this_file = Path(__file__)
    assert not (_imports(this_file) & forbidden_test_modules)
