"""Bounded in-process saved QuerySpec views."""
from __future__ import annotations

from dataclasses import dataclass
from .query_service import QueryPage, QueryService, QuerySpec
from .exports import export_query


@dataclass(frozen=True, slots=True)
class SavedView:
    id: str
    name: str
    query: QuerySpec

    def __post_init__(self) -> None:
        if not self.id.strip() or not self.name.strip():
            raise ValueError("saved view id and name must not be empty")


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
