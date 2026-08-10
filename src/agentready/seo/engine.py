"""SEO atomic-rule execution and compatibility aggregation."""
from __future__ import annotations

import logging

from ..http import HttpClient
from ..seo_models import SeoCheckResult
from .evidence import SeoPageEvidence, collect_page_evidence
from .rules.builtin import run_rules
from .rules.models import AtomicFinding

logger = logging.getLogger(__name__)


def run_atomic_rules(evidence: SeoPageEvidence) -> tuple[AtomicFinding, ...]:
    """Evaluate all built-in rules from one immutable evidence snapshot."""
    return run_rules(evidence)


def aggregate_v1(findings: tuple[AtomicFinding, ...] | list[AtomicFinding]) -> list[SeoCheckResult]:
    """Adapt v2 atomic findings to v1 result shape without changing legacy checks."""
    ordered = sorted(findings, key=lambda item: (item.rule.category, item.rule.id, item.target))
    results = [item.to_v1() for item in ordered]
    logger.debug("[WP6.4] aggregated atomic findings into v1 results=%d", len(results))
    return results


def audit_atomic_page(url: str, client: HttpClient) -> tuple[SeoPageEvidence, tuple[AtomicFinding, ...]]:
    evidence = collect_page_evidence(url, client)
    return evidence, run_atomic_rules(evidence)
