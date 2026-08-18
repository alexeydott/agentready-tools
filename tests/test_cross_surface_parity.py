import json

import pytest
from fastapi.testclient import TestClient

from agentready.audit_core.store import MemorySiteStore, PageRecord, RunRecord
from agentready.dashboard import render_dashboard
from agentready.exports import export_query
from agentready.query_service import PageQuery, QueryService
from agentready.server import _V2_RUNS, app


def test_api_mcp_export_and_dashboard_share_inventory_contract():
    # The API/dashboard halves remain useful in the server profile, while the
    # MCP projection is exercised only when the explicit MCP extra is present.
    pytest.importorskip("mcp")

    run_id = "parity-run-37"
    store = MemorySiteStore()
    store.begin_run(RunRecord(run_id, "config-hash", "tool", "rules"))
    store.put_page(PageRecord(run_id, "https://example.test/a", "https://example.test/a", status_code=200, depth=0, title="A"))
    store.put_page(PageRecord(run_id, "https://example.test/b", "https://example.test/b", status_code=404, depth=1, title="B"))
    _V2_RUNS.put(run_id, store)

    api = TestClient(app).get(f"/v2/runs/{run_id}/inventory/pages", params={"limit": 1}).json()
    exported = json.loads(export_query(QueryService(store), PageQuery(run_id, limit=1), format="json", limit=1))
    assert api["run_id"] == run_id
    assert api["items"] == exported
    assert api["next_cursor"] == "https://example.test/a"

    from agentready import mcp_server as mcp
    mcp_payload = mcp.run_inventory_v2(run_id, kind="pages", limit=1)
    assert mcp_payload["run_id"] == api["run_id"]
    assert mcp_payload["items"] == api["items"]
    assert mcp_payload["next_cursor"] == api["next_cursor"]

    dashboard = render_dashboard("en")
    assert "/v2/runs/" in dashboard and "/inventory/" in dashboard
    assert "next_cursor" in dashboard


def test_finding_identity_and_state_are_explicit_in_v2_projection():
    run_id = "parity-finding-37"
    store = MemorySiteStore()
    store.begin_run(RunRecord(run_id, "config-hash", "tool", "rules"))
    store.put_finding(run_id, "title", {"id": "title", "status": "fail", "state_hash": "state-37", "affected_urls": ["https://example.test/b"]})
    _V2_RUNS.put(run_id, store)
    payload = TestClient(app).get(f"/v2/runs/{run_id}/findings").json()
    assert payload["items"][0]["finding_id"] == "title"
    assert payload["items"][0]["payload"]["state_hash"] == "state-37"
