import csv
import io
import json

import pytest

from agentready.audit_core.store import MemorySiteStore, RunUrlRecord, RunUrlState
from agentready.query_service import PageQuery, QueryService, RunUrlQuery
from agentready.saved_views import SavedView, SavedViewRegistry


def test_saved_views_are_bounded_and_deterministically_listed():
    registry = SavedViewRegistry(max_views=1)
    view = SavedView("pages", "Pages", PageQuery("run-1", limit=10))
    registry.save(view)
    assert registry.list() == (view,)
    assert registry.get("pages").query.limit == 10
    with pytest.raises(ValueError, match="limit reached"):
        registry.save(SavedView("other", "Other", PageQuery("run-1")))
    registry.delete("pages")
    assert registry.list() == ()


def test_saved_view_executes_through_query_service():
    store = MemorySiteStore()
    store.put_run_url(RunUrlRecord("run", "https://example.test/a", RunUrlState.PARSED))
    registry = SavedViewRegistry()
    registry.save(SavedView("urls", "URLs", RunUrlQuery("run")))
    result = registry.execute("urls", QueryService(store))
    assert result.items[0].url_key == "https://example.test/a"


def test_saved_view_exports_complete_bounded_query_result():
    store = MemorySiteStore()
    store.put_run_url(RunUrlRecord("run", "https://example.test/a", RunUrlState.PARSED))
    registry = SavedViewRegistry()
    registry.save(SavedView("urls", "URLs", RunUrlQuery("run")))

    output = registry.export("urls", QueryService(store), format="json")

    assert "https://example.test/a" in output


def test_saved_view_export_preserves_filters_cursor_sorting_and_limit_in_json_and_csv():
    store = MemorySiteStore()
    for url, state in (
        ("https://example.test/a", RunUrlState.PARSED),
        ("https://example.test/b", RunUrlState.SKIPPED),
        ("https://example.test/c", RunUrlState.PARSED),
        ("https://example.test/d", RunUrlState.PARSED),
    ):
        store.put_run_url(RunUrlRecord("run", url, state))

    registry = SavedViewRegistry()
    registry.save(
        SavedView(
            "parsed-after-b",
            "Parsed after b",
            RunUrlQuery("run", state=RunUrlState.PARSED, cursor="https://example.test/b", limit=1),
        )
    )
    query_service = QueryService(store)

    json_rows = json.loads(registry.export("parsed-after-b", query_service, format="json", limit=2))
    csv_rows = list(csv.DictReader(io.StringIO(registry.export("parsed-after-b", query_service, format="csv", limit=2))))

    assert [row["url_key"] for row in json_rows] == [
        "https://example.test/c",
        "https://example.test/d",
    ]
    assert [row["url_key"] for row in csv_rows] == [
        "https://example.test/c",
        "https://example.test/d",
    ]
    assert all(row["state"] == RunUrlState.PARSED.value for row in json_rows)
    assert all(row["state"] == RunUrlState.PARSED.value for row in csv_rows)

    bounded = json.loads(registry.export("parsed-after-b", query_service, format="json", limit=1))
    assert [row["url_key"] for row in bounded] == ["https://example.test/c"]
