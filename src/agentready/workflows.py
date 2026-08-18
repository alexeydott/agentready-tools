"""Reusable bounded product-workflow DTOs over the canonical v2 query boundary."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .audit_core.store import SiteStore
from .query_service import (
    FindingQuery,
    LinkQuery,
    MetricQuery,
    PageQuery,
    QueryPage,
    QueryService,
    RedirectQuery,
    ResourceQuery,
    RunUrlQuery,
)

INVENTORY_KINDS = ("pages", "run-urls", "links", "resources", "redirects", "findings", "metrics")
WORKFLOW_CONTRACT = "agentready.workflow.v2"


class WorkflowRequestError(ValueError):
    """Stable client-facing error for invalid bounded workflow requests."""


@dataclass(frozen=True, slots=True)
class InventoryRequest:
    """Transport-neutral bounded inventory request."""

    run_id: str
    kind: str = "pages"
    limit: int = 100
    cursor: str | None = None
    search: str | None = None
    sort_by: str | None = None
    descending: bool = False

    def __post_init__(self) -> None:
        if not self.run_id.strip():
            raise WorkflowRequestError("run_id must not be empty")
        if self.kind not in INVENTORY_KINDS:
            raise WorkflowRequestError(f"unsupported inventory kind: {self.kind}")
        if self.limit < 1 or self.limit > 1000:
            raise WorkflowRequestError("limit must be between 1 and 1000")
        if self.search is not None and len(self.search) > 500:
            raise WorkflowRequestError("search must not exceed 500 characters")


@dataclass(frozen=True, slots=True)
class InventoryResponse:
    """Bounded application result; transports own serialization only."""

    run_id: str
    kind: str
    items: tuple[Any, ...]
    next_cursor: str | None
    total: int | None
    contract: str = WORKFLOW_CONTRACT


def inventory_query(request: InventoryRequest) -> object:
    """Translate one bounded request to an allowlisted typed QueryService spec."""
    sort = request.sort_by
    common = {"run_id": request.run_id, "cursor": request.cursor, "limit": request.limit}
    if request.kind == "pages":
        return PageQuery(title_contains=request.search, sort_by=sort or "url", descending=request.descending, **common)
    if request.kind == "run-urls":
        return RunUrlQuery(**common)
    if request.kind == "links":
        return LinkQuery(anchor_contains=request.search, sort_by=sort or "source", descending=request.descending, **common)
    if request.kind == "resources":
        return ResourceQuery(resource_type=request.search, sort_by=sort or "page", descending=request.descending, **common)
    if request.kind == "redirects":
        return RedirectQuery(to_url=request.search, sort_by=sort or "from_url", descending=request.descending, **common)
    if request.kind == "findings":
        return FindingQuery(affected_url=request.search, sort_by=sort or "finding_id", descending=request.descending, **common)
    return MetricQuery(name=request.search, sort_by=sort or "url", descending=request.descending, **common)


class InventoryWorkflow:
    """Application workflow for bounded inventory projections."""

    def __init__(self, store: SiteStore) -> None:
        self._queries = QueryService(store)

    def execute(self, request: InventoryRequest) -> InventoryResponse:
        page = self._queries.execute(inventory_query(request))
        assert isinstance(page, QueryPage)
        return InventoryResponse(request.run_id, request.kind, tuple(page.items), page.next_cursor, page.total)


def workflow_capabilities(version: str) -> dict[str, Any]:
    """Return stable capability/version discovery for product transports."""
    return {
        "contract": WORKFLOW_CONTRACT,
        "version": version,
        "workflows": {"inventory": {"kinds": list(INVENTORY_KINDS), "max_limit": 1000, "cursor": "opaque-keyset-v1"}},
    }
