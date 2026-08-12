"""Opt-in WP6A scale regression tests.

Run with ``AGENTREADY_SCALE_TESTS=1 pytest -q tests/test_scale_budgets.py``.
The default suite keeps these expensive checks skipped while retaining a
deterministic fixture contract test.
"""
from __future__ import annotations

import logging
import os
import time
import tracemalloc

import pytest

from agentready.duplicates import cluster_signatures
from agentready.exports import export_jsonl
from agentready.link_graph import build_link_graph, diagnose_graph
from agentready.query_service import PageQuery, QueryService
from agentready.report_v2 import diff_inventory

try:
    from .scale_fixtures import (
        content_signatures,
        inventory_rows,
        link_records,
        page_records,
        resource_records,
    )
except ImportError:  # pragma: no cover - direct pytest collection fallback
    from scale_fixtures import (
        content_signatures,
        inventory_rows,
        link_records,
        page_records,
        resource_records,
    )

logger = logging.getLogger(__name__)
SIZES = (1_000, 10_000, 100_000)
SCALE_ENABLED = os.environ.get("AGENTREADY_SCALE_TESTS") == "1"
MAX_DURATION_SECONDS = 60
MAX_PEAK_BYTES = 512 * 1024 * 1024


def test_scale_fixtures_are_deterministic_and_bounded():
    assert page_records(3) == page_records(3)
    assert link_records(3) == link_records(3)
    assert resource_records(3) == resource_records(3)
    assert len(inventory_rows(3)) == 3


@pytest.mark.skipif(not SCALE_ENABLED, reason="set AGENTREADY_SCALE_TESTS=1 to run scale budgets")
@pytest.mark.parametrize("size", SIZES)
def test_scale_budget_operations(size: int):
    operations = (
        ("query", lambda: _query_pages(size)),
        ("graph", lambda: _graph(size)),
        ("duplicates", lambda: cluster_signatures(content_signatures(size))),
        ("diff", lambda: diff_inventory({"pages": inventory_rows(size)}, {"pages": inventory_rows(size)})),
        ("export", lambda: export_jsonl(inventory_rows(size), limit=size)),
    )
    for operation, callback in operations:
        started = time.perf_counter()
        tracemalloc.start()
        result = callback()
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        duration_ms = int((time.perf_counter() - started) * 1000)
        rows = _row_count(result)
        logger.info("scale operation=%s size=%d duration_ms=%d peak_bytes=%d rows=%d truncated=%s", operation, size, duration_ms, peak, rows, False)
        assert rows >= 0
        if size == 100_000:
            assert duration_ms <= MAX_DURATION_SECONDS * 1000, f"{operation} exceeded wall-time budget"
            assert peak <= MAX_PEAK_BYTES, f"{operation} exceeded peak-memory budget"


def _query_pages(size: int):
    class FixtureStore:
        def query_pages(self, run_id: str, *, status_code: int | None = None):
            rows = page_records(size)
            return [row for row in rows if status_code is None or row.status_code == status_code]

    store = FixtureStore()
    return QueryService(store).pages(PageQuery("scale-run", status_code=200, sort_by="depth", limit=1000))


def _graph(size: int):
    occurrences = link_records(size)
    graph = build_link_graph(occurrences, origin="https://scale.example")
    return diagnose_graph(graph, known_pages=tuple(item.source_key for item in occurrences))


def _row_count(value: object) -> int:
    if hasattr(value, "items") and not isinstance(value, dict):
        return len(value.items)
    if isinstance(value, dict):
        return sum(len(item) if isinstance(item, dict) else 1 for item in value.values())
    if isinstance(value, (tuple, list, str, bytes)):
        return len(value)
    return 0
