"""Deterministic built-in SEO atomic rules."""
from __future__ import annotations

import logging
from collections.abc import Callable

from ..evidence import SeoPageEvidence
from .models import AtomicFinding, RuleKind, SeoRuleSpec, finding

logger = logging.getLogger(__name__)

SEO_ATOMIC_RULES: tuple[SeoRuleSpec, ...] = (
    SeoRuleSpec("page-available", "HTML page availability", "technical", RuleKind.STANDARD, True),
    SeoRuleSpec("metadata", "Title, description and headings", "metadata", RuleKind.STANDARD, True),
    SeoRuleSpec("indexability", "Page indexability directives", "indexability", RuleKind.STANDARD, True),
    SeoRuleSpec("canonical", "Canonical URL", "indexability", RuleKind.STANDARD, True),
    SeoRuleSpec("hreflang", "Hreflang annotations", "indexability", RuleKind.CAPABILITY, True),
    SeoRuleSpec("jsonld", "Connected JSON-LD", "structured-data", RuleKind.CAPABILITY, False),
    SeoRuleSpec("title-length", "Title length heuristic", "metadata", RuleKind.HEURISTIC, False),
)


def run_rules(evidence: SeoPageEvidence) -> tuple[AtomicFinding, ...]:
    findings = [
        _availability(evidence),
        _metadata(evidence),
        _indexability(evidence),
        _canonical(evidence),
        _hreflang(evidence),
        _jsonld(evidence),
        _title_length(evidence),
    ]
    logger.info("[WP6.3] atomic SEO rules evaluated target=%s findings=%d", evidence.final_url, len(findings))
    return tuple(findings)


def _availability(e: SeoPageEvidence) -> AtomicFinding:
    rule = SEO_ATOMIC_RULES[0]
    ok = e.status_code == 200 and e.html and not e.fetch_error
    return finding(rule, e.url, "pass" if ok else "error", "HTML page is available" if ok else (e.fetch_error or "page is not HTTP 200 HTML"), e.evidence_ids, impact="high", priority=90)


def _metadata(e: SeoPageEvidence) -> AtomicFinding:
    rule = SEO_ATOMIC_RULES[1]
    if not e.html:
        return finding(rule, e.url, "error", "metadata is not applicable because the response is not HTML", e.evidence_ids)
    issues = []
    if not e.title:
        issues.append("missing title")
    if not e.description:
        issues.append("missing meta description")
    if len(e.h1) != 1:
        issues.append(f"expected one H1, found {len(e.h1)}")
    return finding(rule, e.url, "fail" if issues else "pass", "; ".join(issues) if issues else "title, description and one H1 are present", e.evidence_ids, impact="medium" if issues else "low", priority=75 if issues else 50)


def _indexability(e: SeoPageEvidence) -> AtomicFinding:
    rule = SEO_ATOMIC_RULES[2]
    directives = " ".join((*e.meta_robots, e.x_robots)).lower()
    blocked = "noindex" in directives or "none" in directives
    return finding(rule, e.url, "fail" if blocked else "pass", "noindex directive detected" if blocked else "no noindex directive detected", e.evidence_ids, impact="high" if blocked else "low", priority=95 if blocked else 40)


def _canonical(e: SeoPageEvidence) -> AtomicFinding:
    rule = SEO_ATOMIC_RULES[3]
    expected = e.final_url.rstrip("/")
    valid = len(e.canonicals) == 1 and e.canonicals[0].rstrip("/") == expected
    return finding(rule, e.url, "pass" if valid else "fail", "one canonical matches the final URL" if valid else "canonical is missing, duplicated or points elsewhere", e.evidence_ids, impact="high" if not valid else "low", priority=85 if not valid else 40)


def _hreflang(e: SeoPageEvidence) -> AtomicFinding:
    rule = SEO_ATOMIC_RULES[4]
    if not e.hreflangs:
        return finding(rule, e.url, "skip", "no hreflang annotations; single-language applicability is not scored", e.evidence_ids)
    codes = [code for code, _ in e.hreflangs]
    issues = []
    if len(codes) != len(set(codes)):
        issues.append("duplicate language codes")
    if not any(href.rstrip("/") == e.final_url.rstrip("/") for _, href in e.hreflangs):
        issues.append("no self-referencing language link")
    return finding(rule, e.url, "warn" if issues else "pass", "; ".join(issues) if issues else "hreflang set is internally consistent", e.evidence_ids, impact="medium" if issues else "low", priority=60 if issues else 40)


def _jsonld(e: SeoPageEvidence) -> AtomicFinding:
    rule = SEO_ATOMIC_RULES[5]
    if not e.jsonld_nodes and not e.jsonld_errors:
        return finding(rule, e.url, "skip", "JSON-LD is optional and no block was present", e.evidence_ids)
    if e.jsonld_errors:
        return finding(rule, e.url, "fail", f"{len(e.jsonld_errors)} invalid JSON-LD block(s)", e.evidence_ids, impact="medium", priority=55)
    connected = any(isinstance(node.get("@id"), str) for node in e.jsonld_nodes)
    return finding(rule, e.url, "pass" if connected else "warn", "JSON-LD graph contains linked node identifiers" if connected else "valid JSON-LD has no connected @id graph", e.evidence_ids, impact="low", priority=30)


def _title_length(e: SeoPageEvidence) -> AtomicFinding:
    rule = SEO_ATOMIC_RULES[6]
    if not e.title:
        return finding(rule, e.url, "skip", "title-length heuristic is not applicable without a title", e.evidence_ids)
    valid = 30 <= len(e.title) <= 65
    return finding(rule, e.url, "pass" if valid else "warn", f"title length is {len(e.title)} characters", e.evidence_ids, impact="low", priority=20)


RuleFunction = Callable[[SeoPageEvidence], AtomicFinding]
