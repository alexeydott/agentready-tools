"""GOOGLE-HREF-001/003/004 binding tests (#28, deferred 002/005)."""
from __future__ import annotations

import pytest

from agentready.audit_core import (
    GOOGLE_HREF_EVALUATOR_REGISTRY,
    GOOGLE_HREF_RULE_IDS,
    GOOGLE_HREF_RULE_VERSION,
)
from agentready.audit_core.contracts import FactEnvelope
from agentready.audit_core.evaluator_registry import bind_frozen_rule
from agentready.audit_core.google_href_evaluators import evaluate_google_href
from agentready.audit_core.urls import UrlIdentity
from tests.test_canon_evaluators import ORIGIN, TARGET, T0

from agentready.audit_core.collection import (
    links_fact_envelope,
    page_fact_envelope,
    parsed_facts_from_dict,
)

BOUND_RULES = ("GOOGLE-HREF-001", "GOOGLE-HREF-003", "GOOGLE-HREF-004")
DEFERRED_RULES = ("GOOGLE-HREF-002", "GOOGLE-HREF-005")

_identity = UrlIdentity.parse(TARGET)


def _make_bundle(*, canonicals=None, hreflang=None, meta_robots=None):
    page = page_fact_envelope(
        subject_url=TARGET,
        facts=parsed_facts_from_dict({
            "canonicals": canonicals or [],
            "hreflang": hreflang if hreflang is not None else [],
            "meta_robots": meta_robots or [],
            "links": [],
        }),
        observed_at=T0,
    )
    links_env = links_fact_envelope(subject_url=TARGET, links=(), observed_at=T0)
    return (page, links_env)


def _make_bundle_no_hreflang(*, canonicals=None, meta_robots=None):
    """Build a page envelope where the hreflang key is absent from the dict."""
    payload = {
        "canonicals": canonicals or [],
        "meta_robots": meta_robots or [],
        "links": [],
    }
    page = FactEnvelope(
        id="test-no-hreflang",
        kind="page",
        target=_identity,
        value=payload,
        observed_at=T0,
        schema_family="page",
    )
    links_env = links_fact_envelope(subject_url=TARGET, links=(), observed_at=T0)
    return (page, links_env)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

def test_href_rule_ids_are_bound_only():
    assert set(GOOGLE_HREF_RULE_IDS) == set(BOUND_RULES)


@pytest.mark.parametrize("rule_id", BOUND_RULES)
def test_each_bound_rule_binds_against_the_frozen_catalog(rule_id):
    binding = bind_frozen_rule(
        rule_id, GOOGLE_HREF_RULE_VERSION, registry=GOOGLE_HREF_EVALUATOR_REGISTRY
    )
    assert binding.rule_id == rule_id
    assert binding.version == GOOGLE_HREF_RULE_VERSION


# ---------------------------------------------------------------------------
# HREF-001: valid language codes
# ---------------------------------------------------------------------------

def test_href001_pass_valid_codes():
    bundle = _make_bundle(hreflang=[{"lang": "en", "href": ORIGIN + "/page"}])
    r = evaluate_google_href(TARGET, bundle, rule_id="GOOGLE-HREF-001")
    assert r.finding.status.value == "pass"


def test_href001_fail_invalid_code():
    bundle = _make_bundle(hreflang=[{"lang": "INVALID-CODE!", "href": ORIGIN + "/page"}])
    r = evaluate_google_href(TARGET, bundle, rule_id="GOOGLE-HREF-001")
    assert r.finding.status.value == "fail"
    assert "invalid" in r.report.findings[0].reason.lower()


def test_href001_skip_empty_hreflang():
    bundle = _make_bundle(hreflang=[])
    r = evaluate_google_href(TARGET, bundle, rule_id="GOOGLE-HREF-001")
    assert r.finding.status.value == "skip"
    assert r.finding.outcome.value == "not_applicable"


def test_href001_unknown_hreflang_key_missing():
    """Raw evaluator returns UNKNOWN; evaluate_google_href escalates to error."""
    from agentready.audit_core.google_href_evaluators import _href_001_valid_codes
    bundle = _make_bundle_no_hreflang()
    raw = _href_001_valid_codes(TARGET, {"page": bundle[0].value})
    assert raw.outcome.value == "unknown"
    r = evaluate_google_href(TARGET, bundle, rule_id="GOOGLE-HREF-001")
    assert r.finding.status.value == "error"


# ---------------------------------------------------------------------------
# HREF-003: self-reference
# ---------------------------------------------------------------------------

def test_href003_pass_self_ref():
    bundle = _make_bundle(hreflang=[{"lang": "en", "href": ORIGIN + "/page"}])
    r = evaluate_google_href(TARGET, bundle, rule_id="GOOGLE-HREF-003")
    assert r.finding.status.value == "pass"


def test_href003_fail_no_self_ref():
    bundle = _make_bundle(hreflang=[{"lang": "en", "href": ORIGIN + "/other"}])
    r = evaluate_google_href(TARGET, bundle, rule_id="GOOGLE-HREF-003")
    assert r.finding.status.value == "fail"
    assert "references the current url" in r.report.findings[0].reason.lower()


def test_href003_skip_empty_hreflang():
    bundle = _make_bundle(hreflang=[])
    r = evaluate_google_href(TARGET, bundle, rule_id="GOOGLE-HREF-003")
    assert r.finding.status.value == "skip"
    assert r.finding.outcome.value == "not_applicable"


def test_href003_unknown_hreflang_key_missing():
    from agentready.audit_core.google_href_evaluators import _href_003_self_reference
    bundle = _make_bundle_no_hreflang()
    raw = _href_003_self_reference(TARGET, {"page": bundle[0].value})
    assert raw.outcome.value == "unknown"
    r = evaluate_google_href(TARGET, bundle, rule_id="GOOGLE-HREF-003")
    assert r.finding.status.value == "error"


# ---------------------------------------------------------------------------
# HREF-004: x-default present (diagnostic)
# ---------------------------------------------------------------------------

def test_href004_pass_x_default_present():
    bundle = _make_bundle(hreflang=[
        {"lang": "en", "href": ORIGIN + "/page"},
        {"lang": "x-default", "href": ORIGIN + "/page"},
    ])
    r = evaluate_google_href(TARGET, bundle, rule_id="GOOGLE-HREF-004")
    assert r.finding.status.value == "pass"


def test_href004_fail_x_default_missing():
    bundle = _make_bundle(hreflang=[{"lang": "en", "href": ORIGIN + "/page"}])
    r = evaluate_google_href(TARGET, bundle, rule_id="GOOGLE-HREF-004")
    assert r.finding.status.value == "fail"
    assert "x-default" in r.report.findings[0].reason.lower()


def test_href004_skip_empty_hreflang():
    bundle = _make_bundle(hreflang=[])
    r = evaluate_google_href(TARGET, bundle, rule_id="GOOGLE-HREF-004")
    assert r.finding.status.value == "skip"
    assert r.finding.outcome.value == "not_applicable"


def test_href004_unknown_hreflang_key_missing():
    from agentready.audit_core.google_href_evaluators import _href_004_x_default
    bundle = _make_bundle_no_hreflang()
    raw = _href_004_x_default(TARGET, {"page": bundle[0].value})
    assert raw.outcome.value == "unknown"
    r = evaluate_google_href(TARGET, bundle, rule_id="GOOGLE-HREF-004")
    assert r.finding.status.value == "error"


# ---------------------------------------------------------------------------
# Deferred rules (declared_not_producible)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("rule_id", DEFERRED_RULES)
def test_deferred_rules_are_not_registered(rule_id):
    assert rule_id not in GOOGLE_HREF_EVALUATOR_REGISTRY.registered_targets
