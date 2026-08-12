import pytest

from agentready.audit_core.store import MemorySiteStore, RunUrlRecord, RunUrlState
from agentready.exports import (
    brand_html,
    export_csv,
    export_html,
    export_json,
    export_jsonl,
    export_markdown,
    export_query,
)
from agentready.query_service import QueryService, RunUrlQuery


def test_exports_are_bounded_and_machine_readable():
    rows = [{"id": 1, "name": "A"}, {"id": 2, "name": "B"}]
    assert '"id": 1' in export_json(rows, limit=1)
    assert len(export_jsonl(rows).splitlines()) == 2
    assert export_csv(rows).splitlines()[0] == "id,name"
    assert "| name |" in export_markdown(rows)
    assert "<table>" in export_html(rows)
    branded = brand_html(export_html(rows), name="Example")
    assert "Example" in branded
    assert "<table>" in branded
    with pytest.raises(ValueError):
        export_json(rows, limit=0)


def test_query_export_consumes_typed_query_pages():
    store = MemorySiteStore()
    store.put_run_url(RunUrlRecord("run", "https://example.test/a", RunUrlState.PARSED))
    output = export_query(QueryService(store), RunUrlQuery("run"), format="json")
    assert "https://example.test/a" in output


def test_large_inventory_exports_remain_bounded():
    rows = [{"id": index, "value": "x" * 20} for index in range(1000)]
    rendered = export_html(rows, limit=25)
    assert rendered.count("<tr>") == 26
    assert "id=\"999\"" not in rendered
