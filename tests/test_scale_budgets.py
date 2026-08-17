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

from agentready.audit_core.store import PageStorageQuery, RunRecord, SQLiteSiteStore
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


@pytest.mark.scale
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


@pytest.mark.scale
@pytest.mark.skipif(not SCALE_ENABLED, reason="set AGENTREADY_SCALE_TESTS=1 to run scale budgets")
@pytest.mark.parametrize("size", SIZES)
def test_sqlite_scale_query_write_and_pagination(size: int, tmp_path):
    """Exercise the real SQLite keyset path without retaining generated databases."""
    started = time.perf_counter()
    tracemalloc.start()
    store = SQLiteSiteStore(tmp_path / f"scale-{size}.sqlite")
    try:
        store.begin_run(RunRecord("scale-run", "config", "tool", "rules"))
        rows = [
            ("scale-run", f"https://scale.example/{index:06d}", f"https://scale.example/{index:06d}", 1, 200, None, None, None, None, None, None, None)
            for index in range(size)
        ]
        with store._transaction():
            store._connection.executemany(
                "INSERT INTO pages(run_id,url_key,requested_url,final_url,depth,status_code,content_type,title,canonical,locally_indexable,content_hash,content) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                rows,
            )
        cursor = None
        seen = 0
        while True:
            page = store.query_pages_storage(PageStorageQuery("scale-run", limit=1000, cursor=cursor))
            seen += len(page.items)
            if page.next_cursor is None:
                break
            cursor = page.next_cursor
        _, peak = tracemalloc.get_traced_memory()
        duration_ms = int((time.perf_counter() - started) * 1000)
        logger.info("scale operation=sqlite-query-write-pagination size=%d duration_ms=%d peak_bytes=%d rows=%d threshold_ms=%d threshold_bytes=%d", size, duration_ms, peak, seen, MAX_DURATION_SECONDS * 1000, MAX_PEAK_BYTES)
        assert seen == size
        if size == 100_000:
            assert duration_ms <= MAX_DURATION_SECONDS * 1000
            assert peak <= MAX_PEAK_BYTES
    finally:
        tracemalloc.stop()
        store.close()


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
