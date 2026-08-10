"""Versioned SEO evidence and atomic-rule engine."""

from .evidence import SeoPageEvidence, collect_page_evidence
from .engine import aggregate_v1, run_atomic_rules

__all__ = ["SeoPageEvidence", "aggregate_v1", "collect_page_evidence", "run_atomic_rules"]
