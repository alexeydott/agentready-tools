"""GOOGLE-HREF-001..005 binding tests (#28)."""
from __future__ import annotations

import pytest

from agentready.audit_core import (
    GOOGLE_HREF_EVALUATOR_REGISTRY,
    GOOGLE_HREF_RULE_IDS,
    GOOGLE_HREF_RULE_VERSION,
)
from agentready.audit_core.evaluator_registry import bind_frozen_rule
from agentready.audit_core.google_href_evaluators import evaluate_google_href
from tests.test_canon_evaluators import ORIGIN, TARGET, T0

from agentready.audit_core.collection import (
    links_fact_envelope,
    page_fact_envelope,
    parsed_facts_from_dict,
)


def _make_bundle(*, canonicals=None, hreflang=None, meta_robots=None):
    page = page_fact_envelope(
        subject_url=TARGET,
        facts=parsed_facts_from_dict({
            "canonicals": canonicals or [],
            "hreflang": hreflang or [],
            "meta_robots": meta_robots or [],
            "links": [],
        }),
        observed_at=T0,
    )
    links_env = links_fact_envelope(subject_url=TARGET, links=(), observed_at=T0)
    return (page, links_env)


@pytest.mark.parametrize("rule_id", GOOGLE_HREF_RULE_IDS)
def test_each_href_rule_binds_against_the_frozen_catalog(rule_id):
    binding = bind_frozen_rule(
        rule_id, GOOGLE_HREF_RULE_VERSION, registry=GOOGLE_HREF_EVALUATOR_REGISTRY
    )
    assert binding.rule_id == rule_id
    assert binding.version == GOOGLE_HREF_RULE_VERSION


# --- HREF-001: valid language codes ---

def test_href001_pass_valid_codes():
    bundle = _make_bundle(hreflang=[{"lang": "en", "href": ORIGIN + "/page"}])
    r = evaluate_google_href(TARGET, bundle, rule_id="GOOGLE-HREF-001")
    assert r.finding.status.value == "pass"


def test_href001_fail_invalid_code():
    bundle = _make_bundle(hreflang=[{"lang": "INVALID-CODE!", "href": ORIGIN + "/page"}])
    r = evaluate_google_href(TARGET, bundle, rule_id="GOOGLE-HREF-001")
    assert r.finding.status.value == "fail"
    assert "invalid" in r.report.findings[0].reason.lower()


# --- HREF-002: cluster consistency ---

def test_href002_pass_consistent():
    bundle = _make_bundle(hreflang=[
        {"lang": "en", "href": ORIGIN + "/page"},
        {"lang": "fr", "href": ORIGIN + "/fr"},
    ])
    r = evaluate_google_href(TARGET, bundle, rule_id="GOOGLE-HREF-002")
    assert r.finding.status.value == "pass"


def test_href002_fail_duplicate_codes():
    bundle = _make_bundle(hreflang=[
        {"lang": "en", "href": ORIGIN + "/page"},
        {"lang": "en", "href": ORIGIN + "/en"},
    ])
    r = evaluate_google_href(TARGET, bundle, rule_id="GOOGLE-HREF-002")
    assert r.finding.status.value == "fail"
    assert "duplicate" in r.report.findings[0].reason.lower()


def test_href002_fail_relative_href():
    bundle = _make_bundle(hreflang=[{"lang": "en", "href": "/relative"}])
    r = evaluate_google_href(TARGET, bundle, rule_id="GOOGLE-HREF-002")
    assert r.finding.status.value == "fail"
    assert "relative" in r.report.findings[0].reason.lower()


# --- HREF-003: self-reference ---

def test_href003_pass_self_ref():
    bundle = _make_bundle(hreflang=[{"lang": "en", "href": ORIGIN + "/page"}])
    r = evaluate_google_href(TARGET, bundle, rule_id="GOOGLE-HREF-003")
    assert r.finding.status.value == "pass"


def test_href003_fail_no_self_ref():
    bundle = _make_bundle(hreflang=[{"lang": "en", "href": ORIGIN + "/other"}])
    r = evaluate_google_href(TARGET, bundle, rule_id="GOOGLE-HREF-003")
    assert r.finding.status.value == "fail"
    assert "references the current url" in r.report.findings[0].reason.lower()


# --- HREF-004: x-default present (diagnostic) ---

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


# --- HREF-005: target canonical + indexable ---

def test_href005_pass_targets_canonical():
    bundle = _make_bundle(
        canonicals=[ORIGIN + "/page"],
        hreflang=[{"lang": "en", "href": ORIGIN + "/page"}],
    )
    r = evaluate_google_href(TARGET, bundle, rule_id="GOOGLE-HREF-005")
    assert r.finding.status.value == "pass"


def test_href005_fail_target_not_canonical():
    bundle = _make_bundle(
        canonicals=[ORIGIN + "/page"],
        hreflang=[{"lang": "de", "href": ORIGIN + "/de"}],
    )
    r = evaluate_google_href(TARGET, bundle, rule_id="GOOGLE-HREF-005")
    assert r.finding.status.value == "fail"
    assert "not in declared canonical" in r.report.findings[0].reason.lower()


def test_href005_fail_blocked_from_indexing():
    bundle = _make_bundle(
        canonicals=[ORIGIN + "/page"],
        hreflang=[{"lang": "en", "href": ORIGIN + "/page"}],
        meta_robots=["noindex"],
    )
    r = evaluate_google_href(TARGET, bundle, rule_id="GOOGLE-HREF-005")
    assert r.finding.status.value == "fail"
    assert "blocked from indexing" in r.report.findings[0].reason.lower()
