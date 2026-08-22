"""Accepted-contract tests for the CORE-LINK wave (#47, Option B for 002/005).

Fixture model: page@1 envelopes are built through the sanctioned
``page_fact_envelope`` adapter; representation facts use the documented
store-record shape (PageRecord status/content_type columns). CORE-LINK-002/005
are declared_not_produced: evaluator functions stay covered via direct
invocation, but no registry binding exists until resources@1 production lands
(Option A upgrade path).

Targeted exact-HEAD suite:

    python -m pytest tests/test_link_evaluators.py -q

"""

from __future__ import annotations

import ast
import dataclasses
import pathlib

import pytest

from agentready.audit_core.collection import (
    page_fact_envelope,
    parsed_facts_from_dict,
)
from agentready.audit_core.contracts import FactEnvelope
from agentready.audit_core.evaluator_registry import (
    FrozenRuleBindingError,
    UnregisteredRuleError,
)
from agentready.audit_core.link_evaluators import (
    CORE_LINK_RULE_VERSION,
    LINK_EVALUATOR_REGISTRY,
    LINK_EXPECTED_CONTRACTS,
    _core_link_002,
    _core_link_005,
    bind_link_rule,
    evaluate_link_rule,
)
from agentready.audit_core.rule_catalog import load_rule_catalog_snapshot
from agentready.audit_core.urls import UrlIdentity

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
TARGET = "https://example.test/page"
ORIGIN = "https://example.test"
T0 = "2026-08-22T00:00:00Z"

BOUND_RULES = ("CORE-LINK-001", "CORE-LINK-003", "CORE-LINK-004", "CORE-LINK-006")
DEFERRED_RULES = ("CORE-LINK-002", "CORE-LINK-005")


def _row(ordinal, raw_href, resolved_url=None, rel=""):
    return {
        "source_representation_id": "static-html",
        "ordinal": ordinal,
        "raw_href": raw_href,
        "resolved_url": resolved_url,
        "rel": rel,
    }


INTERNAL = _row(0, "/next", f"{ORIGIN}/next")
EXTERNAL = _row(1, "https://other.test/x", "https://other.test/x")


def _page_env(target=TARGET, rows=(), version="1"):
    payload_links = [
        {
            "source_representation_id": r["source_representation_id"],
            "ordinal": i,
            "raw_href": r["raw_href"],
            "resolved_url": r.get("resolved_url"),
            "rel": r.get("rel", ""),
        }
        for i, r in enumerate(rows)
    ]
    envelope = page_fact_envelope(
        subject_url=target,
        facts=parsed_facts_from_dict({"links": payload_links}),
        observed_at=T0,
    )
    if version != "1":
        envelope = dataclasses.replace(envelope, schema_version=version)
    return envelope


def _representation_env(status=200, content_type="text/html"):
    return FactEnvelope(
        f"rep-{status}-{content_type}",
        "representation",
        UrlIdentity.parse(TARGET),
        {"status_code": status, "content_type": content_type},
        T0,
        schema_family="representation",
        schema_version="1",
    )


def _facts_for(rule_id, *, target=TARGET, rows=(INTERNAL,), rep=None):
    bundles = [_page_env(target=target, rows=rows)]
    if rule_id in {"CORE-LINK-001", "CORE-LINK-004"}:
        bundles.append(rep or _representation_env())
    return tuple(bundles)


# ---------------------------------------------------------------------------
# registry scope (Option B: 002/005 declared_not_produced)
# ---------------------------------------------------------------------------


def test_catalog_requirements_match_evaluator_contracts():
    """Regression (review 5001208124): amended catalog rows == evaluator expectations."""
    snapshot = load_rule_catalog_snapshot()
    for rid in BOUND_RULES + DEFERRED_RULES:
        entry = snapshot.entry(rid)
        catalog = tuple(
            (f.family, f.min_schema_version) for f in entry.fact_requirements
        )
        expected = tuple(LINK_EXPECTED_CONTRACTS[rid]["facts"])
        assert catalog == expected, rid


def test_registry_scoped_to_bound_rules_only():
    assert {rid for rid, _v in LINK_EVALUATOR_REGISTRY.registered_targets} == set(
        BOUND_RULES
    )


def test_contract_prep_rules_are_not_registered_frozen_bindings():
    """Direct-invocation coverage (contract preparation) must never leak into bindings."""
    bound = {rid for rid, _v in LINK_EVALUATOR_REGISTRY.registered_targets}
    assert set(DEFERRED_RULES).isdisjoint(bound)


@pytest.mark.parametrize("rule_id", DEFERRED_RULES)
def test_declared_not_produced_rules_are_not_bindable(rule_id):
    with pytest.raises(UnregisteredRuleError):
        LINK_EVALUATOR_REGISTRY.resolve(rule_id, CORE_LINK_RULE_VERSION)


@pytest.mark.parametrize("rule_id", DEFERRED_RULES)
def test_deferred_contracts_keep_resources_family(rule_id):
    entry = load_rule_catalog_snapshot().entry(rule_id)
    assert {f.family for f in entry.fact_requirements} == {"page", "resources"}
    obj = LINK_EVALUATOR_REGISTRY._expected_contracts[(rule_id, CORE_LINK_RULE_VERSION)]
    assert ("resources", "1") in obj.facts


# ---------------------------------------------------------------------------
# bound-rule behaviour
# ---------------------------------------------------------------------------


def test_link001_pass_with_internal_link():
    result = evaluate_link_rule(TARGET, _facts_for("CORE-LINK-001"), ("CORE-LINK-001"))
    assert result.readiness.can_evaluate is True
    assert result.finding.status.value == "pass"


def test_link001_fails_without_internal_links():
    result = evaluate_link_rule(TARGET, _facts_for("CORE-LINK-001", rows=()), ("CORE-LINK-001"))
    assert result.finding.status.value == "fail"


def test_link001_unknown_when_html_success_undetermined():
    facts = _facts_for("CORE-LINK-001", rep=_representation_env(status=None))
    result = evaluate_link_rule(TARGET, facts, "CORE-LINK-001")
    # block_on_missing_facts escalates an indeterminate HTML-success to error
    assert result.finding.status.value == "error"


def test_link003_passes_when_any_link_declared():
    result = evaluate_link_rule(TARGET, _facts_for("CORE-LINK-003"), ("CORE-LINK-003"))
    assert result.finding.status.value == "pass"


def test_link003_fails_on_empty_links():
    result = evaluate_link_rule(TARGET, _facts_for("CORE-LINK-003", rows=()), ("CORE-LINK-003"))
    assert result.finding.status.value == "fail"


def test_link004_warns_diagnostically_without_internal_links():
    result = evaluate_link_rule(TARGET, _facts_for("CORE-LINK-004", rows=()), ("CORE-LINK-004"))
    assert result.finding.status.value == "warn"


def test_link006_census_passes_with_external_row():
    result = evaluate_link_rule(TARGET, _facts_for("CORE-LINK-006", rows=(EXTERNAL,)), ("CORE-LINK-006"))
    assert result.finding.status.value == "pass"


@pytest.mark.parametrize("rule_id", BOUND_RULES)
def test_binding_title_matches_catalog(rule_id):
    entry = load_rule_catalog_snapshot().entry(rule_id)
    binding = bind_link_rule(rule_id)
    assert binding.title == entry.title


@pytest.mark.parametrize("rule_id", BOUND_RULES)
def test_stale_catalog_versions_rejected(rule_id):
    snap = load_rule_catalog_snapshot()

    class _Snap:
        def __getattr__(self, name):
            return getattr(snap, name)

        @staticmethod
        def entry(rid):
            return dataclasses.replace(snap.entry(rid), version="0.9.0")

    with pytest.raises(FrozenRuleBindingError):
        bind_link_rule(rule_id, snapshot=_Snap())


def test_other_target_page_facts_do_not_satisfy_readiness():
    result = evaluate_link_rule(TARGET, _facts_for("CORE-LINK-001", target="https://other.test/p"), "CORE-LINK-001")
    assert result.readiness.can_evaluate is False


def test_purity_module_has_no_io_imports():
    tree = ast.parse(
        (REPO_ROOT / "src" / "agentready" / "audit_core" / "link_evaluators.py").read_text(
            encoding="utf-8"
        )
    )
    roots = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.add(node.names[0].name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split(".")[0])
    forbidden = {"requests", "httpx", "sqlite3", "socket", "subprocess"}
    assert roots & forbidden == set(), roots & forbidden

def _direct_002_facts(rows, resources):
    page_rows = [
        {
            "source_representation_id": "static-html",
            "ordinal": i,
            "raw_href": r["raw_href"],
            "resolved_url": r.get("resolved_url"),
        }
        for i, r in enumerate(rows)
    ]
    return {
        "page": {"links": page_rows},
        "links": {"links": page_rows},
        "resources": {"resources": resources},
    }


def test_contract_prep_link002_consistent_resolution_passes():
    rows = [_row(0, "/a.css", f"{ORIGIN}/a.css")]
    resources = [{"url": "/a.css", "resolved_url": f"{ORIGIN}/a.css"}]
    result = _core_link_002(TARGET, _direct_002_facts(rows, resources))
    assert result.outcome.value == "pass"


def test_contract_prep_link002_mismatch_fails():
    rows = [_row(0, "/a.css", f"{ORIGIN}/other.css")]
    resources = [{"url": "/a.css", "resolved_url": f"{ORIGIN}/a.css"}]
    result = _core_link_002(TARGET, _direct_002_facts(rows, resources))
    assert result.outcome.value == "fail"


def test_contract_prep_link005_orphan_resource_fails():
    rows = []
    resources = [{"url": "/orphan.css", "resolved_url": f"{ORIGIN}/orphan.css"}]
    result = _core_link_005(TARGET, _direct_002_facts(rows, resources))
    assert result.outcome.value == "fail"
