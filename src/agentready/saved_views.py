"""Bounded in-process saved QuerySpec views."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass

from .audit_core.store import RunUrlState
from .exports import export_query
from .query_service import (
    FindingQuery,
    LinkQuery,
    MetricQuery,
    PageQuery,
    QueryPage,
    QueryService,
    QuerySpec,
    RedirectQuery,
    ResourceQuery,
    RunUrlQuery,
)

SAVED_VIEW_SCHEMA = "agentready.saved-view.v1"


@dataclass(frozen=True, slots=True)
class SavedView:
    id: str
    name: str
    query: QuerySpec

    def __post_init__(self) -> None:
        if not self.id.strip() or not self.name.strip():
            raise ValueError("saved view id and name must not be empty")

    def to_dict(self) -> dict[str, object]:
        query = self.query
        values = asdict(query)
        defaults = {"sort_by": {"PageQuery": "url", "LinkQuery": "source", "ResourceQuery": "page", "MetricQuery": "url", "RedirectQuery": "from_url", "FindingQuery": "finding_id"}.get(type(query).__name__)}
        return {
            "id": self.id,
            "name": self.name,
            "query": type(query).__name__,
            "run_id": query.run_id,
            "filters": {
                key: value for key, value in values.items()
                if key not in {"run_id", "cursor", "limit"}
                and value not in (None, "", False)
                and value != defaults.get("sort_by")
            },
        }

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> SavedView:
        if payload.get("schema", SAVED_VIEW_SCHEMA) != SAVED_VIEW_SCHEMA:
            raise ValueError("unsupported saved view schema")
        query_type = str(payload.get("query", ""))
        run_id = str(payload.get("run_id", ""))
        filters = dict(payload.get("filters", {}))
        common = {"cursor": filters.pop("cursor", None), "limit": int(filters.pop("limit", 100))}
        constructors = {
            "PageQuery": PageQuery,
            "RunUrlQuery": RunUrlQuery,
            "LinkQuery": LinkQuery,
            "ResourceQuery": ResourceQuery,
            "RedirectQuery": RedirectQuery,
            "FindingQuery": FindingQuery,
            "MetricQuery": MetricQuery,
        }
        constructor = constructors.get(query_type)
        if constructor is None:
            raise ValueError(f"unsupported saved view query: {query_type}")
        if query_type == "RunUrlQuery" and filters.get("state"):
            filters["state"] = RunUrlState(str(filters["state"]))
        query = constructor(run_id, **filters, **common)
        return cls(str(payload["id"]), str(payload["name"]), query)

    def serialize(self) -> str:
        payload = self.to_dict()
        payload["schema"] = SAVED_VIEW_SCHEMA
        payload["filters"] = {
            key: (value.value if isinstance(value, RunUrlState) else value)
            for key, value in asdict(self.query).items()
            if key not in {"run_id"}
        }
        return json.dumps(payload, ensure_ascii=True, sort_keys=True)


class SavedViewRegistry:
    """Allowlisted saved-view registry with bounded cardinality."""

    def __init__(self, *, max_views: int = 100) -> None:
        if max_views <= 0 or max_views > 10_000:
            raise ValueError("max_views must be between 1 and 10000")
        self._max_views = max_views
        self._views: dict[str, SavedView] = {}

    def save(self, view: SavedView) -> SavedView:
        if view.id not in self._views and len(self._views) >= self._max_views:
            raise ValueError("saved view limit reached")
        self._views[view.id] = view
        return view

    def get(self, view_id: str) -> SavedView:
        return self._views[view_id]

    def list(self) -> tuple[SavedView, ...]:
        return tuple(self._views[key] for key in sorted(self._views))

    def snapshot(self) -> tuple[str, ...]:
        """Return deterministic portable view records for optional persistence."""
        return tuple(view.serialize() for view in self.list())

    def restore(self, records: tuple[str, ...] | list[str]) -> int:
        restored = 0
        for record in records:
            view = SavedView.from_dict(json.loads(record))
            self.save(view)
            restored += 1
        return restored

    def delete(self, view_id: str) -> None:
        del self._views[view_id]

    def execute(self, view_id: str, query_service: QueryService) -> QueryPage[object]:
        """Execute a saved typed query through the shared QueryService."""
        return query_service.execute(self.get(view_id).query)

    def export(
        self,
        view_id: str,
        query_service: QueryService,
        *,
        format: str = "json",
        limit: int = 100_000,
    ) -> str:
        """Export the complete bounded result of a saved typed query."""
        return export_query(
            query_service,
            self.get(view_id).query,
            format=format,
            limit=limit,
        )
