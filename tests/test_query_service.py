from dataclasses import replace
from pathlib import Path

import pytest

from agentready.audit_core.store import (
    FindingStorageQuery,
    MemorySiteStore,
    MetricRecord,
    PageRecord,
    RedirectFact,
    RunRecord,
    RunUrlRecord,
    RunUrlState,
    SQLiteSiteStore,
    StorageCursor,
)
from agentready.exports import export_query
from agentready.query_service import (
    FindingQuery,
    LinkQuery,
    MetricQuery,
    PageQuery,
    QueryService,
    RedirectQuery,
    ResourceQuery,
    RunUrlQuery,
    validate_query_spec,
)


def _store() -> MemorySiteStore:
    store = MemorySiteStore()
    store.begin_run(RunRecord("run-1", "config", "tool", "rules"))
    for index in range(3):
        store.put_page(PageRecord("run-1", f"https://example.test/{index}", f"https://example.test/{index}", status_code=200))
        store.put_run_url(RunUrlRecord("run-1", f"https://example.test/{index}", RunUrlState.PARSED))
    return store


def test_query_spec_validation_accepts_only_allowlisted_typed_nodes(caplog):
    query = PageQuery("run-1")
    service = QueryService(_store())
    assert validate_query_spec(query) is query
    with caplog.at_level("DEBUG", logger="agentready.query_service"):
        assert service.count(query) == 3
    benchmark = service.benchmark(query, repeats=2)
    assert benchmark.total_items == 3
    assert benchmark.repeats == 2
    record = next(record for record in caplog.records if record.message.startswith("query view=pages"))
    assert "query_id=" in record.message
    assert "total=3" in record.message


def test_storage_cursor_is_opaque_and_bound_to_run_and_query():
    token = StorageCursor("run-1", "pages:v1", ("https://example.test/1",)).encode()
    decoded = StorageCursor.decode(token, run_id="run-1", query_hash="pages:v1")
    assert decoded.position == ("https://example.test/1",)
    with pytest.raises(Exception, match="cursor"):
        StorageCursor.decode(token, run_id="run-other", query_hash="pages:v1")


def test_typed_storage_queries_validate_bounds_and_filters():
    query = FindingStorageQuery("run-1", limit=10, status="fail")
    assert query.status == "fail"
    with pytest.raises(ValueError, match="limit"):
        FindingStorageQuery("run-1", limit=0)


def test_query_service_pages_has_stable_cursor_pagination():
    service = QueryService(_store())
    first = service.pages(PageQuery("run-1", limit=2))
    second = service.pages(PageQuery("run-1", cursor=first.next_cursor, limit=2))
    assert [item.url_key for item in first.items] == [
        "https://example.test/0",
        "https://example.test/1",
    ]
    assert [item.url_key for item in second.items] == ["https://example.test/2"]
    assert first.total == 3
    assert second.next_cursor is None
    assert QueryService(_store()).execute(PageQuery("run-1", limit=1)).items[0].url_key == "https://example.test/0"


def test_query_service_run_urls_filters_by_state():
    store = _store()
    store.put_run_url(RunUrlRecord("run-1", "https://example.test/fail", RunUrlState.FAILED))
    result = QueryService(store).run_urls(RunUrlQuery("run-1", state=RunUrlState.FAILED))
    assert [item.url_key for item in result.items] == ["https://example.test/fail"]


def test_query_service_memory_sqlite_parity(tmp_path: Path):
    memory = _store()
    sqlite = SQLiteSiteStore(tmp_path / "query.sqlite")
    try:
        sqlite.begin_run(RunRecord("run-1", "config", "tool", "rules"))
        for index in range(3):
            sqlite.put_page(PageRecord("run-1", f"https://example.test/{index}", f"https://example.test/{index}", status_code=200))
            sqlite.put_run_url(RunUrlRecord("run-1", f"https://example.test/{index}", RunUrlState.PARSED))
        memory_page = QueryService(memory).pages(PageQuery("run-1", limit=2))
        sqlite_page = QueryService(sqlite).pages(PageQuery("run-1", limit=2))
        assert sqlite_page == memory_page
    finally:
        sqlite.close()


def test_occurrence_queries_use_bounded_cursors_and_match_between_stores(tmp_path: Path):
    stores = [MemorySiteStore(), SQLiteSiteStore(tmp_path / "occurrences.sqlite")]
    try:
        for store in stores:
            store.begin_run(RunRecord("run-occ", "config", "tool", "rules"))
            store.put_link("run-occ", "https://example.test/", "/a", ordinal=0)
            store.put_link("run-occ", "https://example.test/", "/b", ordinal=1)
            store.put_resource("run-occ", "https://example.test/", "/app.js", "script", ordinal=0)
            store.put_resource("run-occ", "https://example.test/", "/style.css", "stylesheet", ordinal=1)

        first_results = []
        for store in stores:
            service = QueryService(store)
            links = service.links(LinkQuery("run-occ", limit=1))
            resources = service.resources(ResourceQuery("run-occ", limit=1))
            assert len(links.items) == len(resources.items) == 1
            assert service.links(LinkQuery("run-occ", cursor=links.next_cursor)).items[0].raw_href == "/b"
            assert service.resources(ResourceQuery("run-occ", cursor=resources.next_cursor)).items[0].resource_url == "/style.css"
            first_results.append((links.items[0].raw_href, resources.items[0].resource_url))
        assert first_results == [("/a", "/app.js"), ("/a", "/app.js")]
    finally:
        stores[1].close()


def test_metric_queries_filter_and_paginate_between_stores(tmp_path: Path):
    stores = [MemorySiteStore(), SQLiteSiteStore(tmp_path / "metrics.sqlite")]
    try:
        for store in stores:
            store.begin_run(RunRecord("run-metric", "config", "tool", "rules"))
            store.put_metric(MetricRecord("run-metric", "https://example.test/", "pagespeed", "lcp", 120, "ms", "fixture", "1", "now"))
            store.put_metric(MetricRecord("run-metric", "https://example.test/", "pagespeed", "cls", 0.1, None, "fixture", "1", "now"))
        for store in stores:
            page = QueryService(store).metrics(MetricQuery("run-metric", provider="pagespeed", limit=1))
            assert len(page.items) == 1
            assert QueryService(store).metrics(
                MetricQuery("run-metric", cursor=page.next_cursor)
            ).items[0].name == "lcp"
    finally:
        stores[1].close()


def test_redirect_and_finding_queries_have_cursor_filters_and_memory_sqlite_parity(tmp_path: Path):
    stores = [MemorySiteStore(), SQLiteSiteStore(tmp_path / "redirects-findings.sqlite")]
    try:
        for store in stores:
            store.begin_run(RunRecord("run-facts", "config", "tool", "rules"))
            store.put_redirect(RedirectFact("run-facts", "https://example.test/a", "/b", 301, "/b"))
            store.put_redirect(RedirectFact("run-facts", "https://example.test/a", "/c", 302, "/c"))
            store.put_redirect(RedirectFact("run-facts", "https://example.test/z", "/x", 301, "/x"))
            store.put_finding("run-facts", "f-a", {"status": "fail", "summary": "A"})
            store.put_finding("run-facts", "f-b", {"status": "pass", "summary": "B"})
            store.put_finding("run-facts", "f-c", {"status": "fail", "summary": "C"})
        results = []
        for store in stores:
            service = QueryService(store)
            redirects = service.redirects(RedirectQuery("run-facts", from_url="https://example.test/a", limit=1))
            findings = service.findings(FindingQuery("run-facts", status="fail", limit=1))
            results.append((
                redirects.items, service.redirects(
                    RedirectQuery("run-facts", from_url="https://example.test/a", cursor=redirects.next_cursor)
                ).items,
                findings.items, service.findings(
                    FindingQuery("run-facts", status="fail", cursor=findings.next_cursor)
                ).items,
            ))
        assert results[0] == results[1]
        assert [item.status_code for item in results[0][0]] == [301]
        assert [item.status_code for item in results[0][1]] == [302]
        assert [item.finding_id for item in results[0][2] + results[0][3]] == ["f-a", "f-c"]
    finally:
        stores[1].close()


def test_marketer_queries_support_allowlisted_filters_and_sorts():
    store = _store()
    store.put_page(PageRecord("run-1", "https://example.test/z", "https://example.test/z", status_code=404, depth=3, title="Product Z", locally_indexable=False))
    service = QueryService(store)
    pages = service.pages(PageQuery("run-1", locally_indexable=False, sort_by="depth", descending=True))
    assert [item.url_key for item in pages.items] == ["https://example.test/z"]
    store.put_link("run-1", "https://example.test/", "/docs", ordinal=3, target_key="https://example.test/docs", anchor_text="Docs", rel="nofollow")
    links = service.links(LinkQuery("run-1", rel="nofollow", anchor_contains="doc", internal=True))
    assert links.items[0].raw_href == "/docs"
    store.put_metric(MetricRecord("run-1", "https://example.test/", "ga4", "sessions", 42, "count", "fixture", "1", "now"))
    assert service.metrics(MetricQuery("run-1", min_value=40)).items[0].value == 42
    assert service.summary(PageQuery("run-1"), group_by="status_code")["200"] == 3


def _collect_query_pages(service: QueryService, query):
    items = []
    cursor = None
    for _ in range(20):
        page = service.execute(replace(query, cursor=cursor, limit=1))
        items.extend(page.items)
        if page.next_cursor is None:
            return items
        cursor = page.next_cursor
    raise AssertionError("cursor pagination did not terminate")


def test_sorted_page_cursors_preserve_typed_order_in_both_directions():
    store = MemorySiteStore()
    store.begin_run(RunRecord("run-sorted", "config", "tool", "rules"))
    for depth in (1, 2, 10, 20):
        url = f"https://example.test/{depth}"
        store.put_page(PageRecord("run-sorted", url, url, status_code=200, depth=depth))
    service = QueryService(store)

    ascending = _collect_query_pages(service, PageQuery("run-sorted", sort_by="depth"))
    descending = _collect_query_pages(service, PageQuery("run-sorted", sort_by="depth", descending=True))

    assert [item.depth for item in ascending] == [1, 2, 10, 20]
    assert [item.depth for item in descending] == [20, 10, 2, 1]
    assert len({item.url_key for item in ascending + descending}) == 4


def test_sorted_occurrence_cursors_use_the_requested_sort_key():
    store = MemorySiteStore()
    store.begin_run(RunRecord("run-occ-sorted", "config", "tool", "rules"))
    store.put_link("run-occ-sorted", "https://example.test/", "/a", ordinal=0, anchor_text="beta")
    store.put_link("run-occ-sorted", "https://example.test/", "/b", ordinal=1, anchor_text="alpha")
    store.put_link("run-occ-sorted", "https://example.test/", "/c", ordinal=2, anchor_text="gamma")
    service = QueryService(store)

    links = _collect_query_pages(service, LinkQuery("run-occ-sorted", sort_by="anchor"))

    assert [item.anchor_text for item in links] == ["alpha", "beta", "gamma"]


def test_all_sorted_inventory_cursors_preserve_order_and_terminate():
    store = MemorySiteStore()
    store.begin_run(RunRecord("run-all-sorted", "config", "tool", "rules"))
    store.put_resource("run-all-sorted", "https://example.test/", "/a.js", "script", status_code=200, ordinal=0)
    store.put_resource("run-all-sorted", "https://example.test/", "/b.css", "stylesheet", status_code=404, ordinal=1)
    store.put_metric(MetricRecord("run-all-sorted", "https://example.test/", "fixture", "small", 2, None, "fixture", "1", "now"))
    store.put_metric(MetricRecord("run-all-sorted", "https://example.test/", "fixture", "large", 10, None, "fixture", "1", "now"))
    store.put_redirect(RedirectFact("run-all-sorted", "https://example.test/a", "/b", 301, "/b"))
    store.put_redirect(RedirectFact("run-all-sorted", "https://example.test/z", "/x", 302, "/x"))
    store.put_finding("run-all-sorted", "finding-a", {"status": "fail", "summary": "A"})
    store.put_finding("run-all-sorted", "finding-b", {"status": "pass", "summary": "B"})
    service = QueryService(store)

    resources = _collect_query_pages(service, ResourceQuery("run-all-sorted", sort_by="status", descending=True))
    metrics = _collect_query_pages(service, MetricQuery("run-all-sorted", sort_by="value"))
    redirects = _collect_query_pages(service, RedirectQuery("run-all-sorted", sort_by="status", descending=True))
    findings = _collect_query_pages(service, FindingQuery("run-all-sorted", sort_by="status"))

    assert [item.status_code for item in resources] == [404, 200]
    assert [item.value for item in metrics] == [2, 10]
    assert [item.status_code for item in redirects] == [302, 301]
    assert [item.payload["status"] for item in findings] == ["fail", "pass"]


def test_sorted_exports_consume_each_row_once():
    store = MemorySiteStore()
    store.begin_run(RunRecord("run-export-sorted", "config", "tool", "rules"))
    for depth in (1, 2, 10):
        url = f"https://example.test/{depth}"
        store.put_page(PageRecord("run-export-sorted", url, url, status_code=200, depth=depth))

    payload = export_query(
        QueryService(store),
        PageQuery("run-export-sorted", sort_by="depth", limit=1),
        format="json",
    )

    import json

    assert [item["depth"] for item in json.loads(payload)] == [1, 2, 10]
