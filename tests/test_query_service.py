from pathlib import Path

from agentready.audit_core.store import (
    MemorySiteStore,
    MetricRecord,
    PageRecord,
    RunRecord,
    RunUrlRecord,
    RunUrlState,
    SQLiteSiteStore,
)
from agentready.audit_core.store import RedirectFact
from agentready.query_service import (
    FindingQuery, LinkQuery, MetricQuery, PageQuery, QueryService, RedirectQuery, ResourceQuery, RunUrlQuery,
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
