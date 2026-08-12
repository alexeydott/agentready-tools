"""SEO atomic-rule execution and canonical v2 aggregation."""
from __future__ import annotations

import logging

from ..http import HttpClient
from ..report_v2 import Finding
from .evidence import SeoPageEvidence, collect_page_evidence
from .rules.builtin import run_rules
from .rules.models import AtomicFinding

logger = logging.getLogger(__name__)


def run_atomic_rules(evidence: SeoPageEvidence) -> tuple[AtomicFinding, ...]:
    """Evaluate all built-in rules from one immutable evidence snapshot."""
    return run_rules(evidence)


def aggregate_v2(findings: tuple[AtomicFinding, ...] | list[AtomicFinding]) -> list[Finding]:
    """Aggregate atomic rule findings into canonical v2 report findings."""
    ordered = sorted(findings, key=lambda item: (item.rule.category, item.rule.id, item.target))
    results = [item.to_v2() for item in ordered]
    logger.debug("[WP6.4] aggregated atomic findings into v2 findings=%d", len(results))
    return results


def audit_atomic_page(url: str, client: HttpClient) -> tuple[SeoPageEvidence, tuple[AtomicFinding, ...]]:
    evidence = collect_page_evidence(url, client)
    return evidence, run_atomic_rules(evidence)
