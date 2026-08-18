from agentready.audit_core.store import (
    MemorySiteStore,
    RunRecord,
    RunUrlRecord,
    RunUrlState,
)
from agentready.audit_service import AuditService
from agentready.workflows import (
    InventoryRequest,
    WorkflowRequestError,
    workflow_capabilities,
)


def _store() -> MemorySiteStore:
    store = MemorySiteStore()
    store.begin_run(RunRecord("run-workflow", "config", "tool", "rules"))
    store.put_run_url(RunUrlRecord("run-workflow", "https://example.test/", RunUrlState.DISCOVERED))
    return store


def test_inventory_workflow_returns_bounded_query_projection() -> None:
    response = AuditService.query_inventory(InventoryRequest("run-workflow", kind="run-urls", limit=1), store=_store())
    assert response.contract == "agentready.workflow.v2"
    assert response.run_id == "run-workflow"
    assert len(response.items) == 1


def test_inventory_request_rejects_unbounded_or_unknown_transport_input() -> None:
    for kwargs in ({"kind": "sql"}, {"limit": 0}, {"limit": 1001}, {"search": "x" * 501}):
        try:
            InventoryRequest("run-workflow", **kwargs)
        except WorkflowRequestError:
            continue
        raise AssertionError(f"request accepted invalid input: {kwargs}")


def test_workflow_capability_version_contract_is_stable() -> None:
    capabilities = workflow_capabilities("0.13.4")
    assert capabilities["contract"] == "agentready.workflow.v2"
    assert capabilities["version"] == "0.13.4"
    assert capabilities["workflows"]["inventory"]["max_limit"] == 1000
