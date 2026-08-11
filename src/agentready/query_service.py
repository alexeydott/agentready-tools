"""Bounded typed query projections over the audit store."""
from __future__ import annotations

import logging
import hashlib
import json
import time
from dataclasses import dataclass
from typing import Generic, TypeVar

from .audit_core.store import (
    FindingRecord,
    LinkOccurrenceRecord,
    MetricRecord,
    PageRecord,
    RedirectFact,
    ResourceOccurrenceRecord,
    RunUrlRecord,
    RunUrlState,
    SiteStore,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class PageQuery:
    """Allowlisted page query with stable keyset pagination."""

    run_id: str
    status_code: int | None = None
    cursor: str | None = None
    limit: int = 100

    def __post_init__(self) -> None:
        if not self.run_id.strip():
            raise ValueError("run_id must not be empty")
        if self.limit <= 0 or self.limit > 1000:
            raise ValueError("query limit must be between 1 and 1000")
        if self.status_code is not None and not 100 <= self.status_code <= 599:
            raise ValueError("status_code must be between 100 and 599")


@dataclass(frozen=True, slots=True)
class RunUrlQuery:
    run_id: str
    state: RunUrlState | None = None
    cursor: str | None = None
    limit: int = 100

    def __post_init__(self) -> None:
        if not self.run_id.strip():
            raise ValueError("run_id must not be empty")
        if self.limit <= 0 or self.limit > 1000:
            raise ValueError("query limit must be between 1 and 1000")


@dataclass(frozen=True, slots=True)
class LinkQuery:
    run_id: str
    source_key: str | None = None
    cursor: str | None = None
    limit: int = 100

    def __post_init__(self) -> None:
        if not self.run_id.strip():
            raise ValueError("run_id must not be empty")
        if self.limit <= 0 or self.limit > 1000:
            raise ValueError("query limit must be between 1 and 1000")


@dataclass(frozen=True, slots=True)
class ResourceQuery:
    run_id: str
    page_key: str | None = None
    cursor: str | None = None
    limit: int = 100

    def __post_init__(self) -> None:
        if not self.run_id.strip():
            raise ValueError("run_id must not be empty")
        if self.limit <= 0 or self.limit > 1000:
            raise ValueError("query limit must be between 1 and 1000")


@dataclass(frozen=True, slots=True)
class MetricQuery:
    run_id: str
    provider: str | None = None
    name: str | None = None
    cursor: str | None = None
    limit: int = 100

    def __post_init__(self) -> None:
        if not self.run_id.strip():
            raise ValueError("run_id must not be empty")
        if self.limit <= 0 or self.limit > 1000:
            raise ValueError("query limit must be between 1 and 1000")


@dataclass(frozen=True, slots=True)
class RedirectQuery:
    run_id: str
    from_url: str | None = None
    status_code: int | None = None
    cursor: str | None = None
    limit: int = 100

    def __post_init__(self) -> None:
        if not self.run_id.strip():
            raise ValueError("run_id must not be empty")
        if self.limit <= 0 or self.limit > 1000:
            raise ValueError("query limit must be between 1 and 1000")
        if self.status_code is not None and not 300 <= self.status_code <= 399:
            raise ValueError("status_code must be between 300 and 399")


@dataclass(frozen=True, slots=True)
class FindingQuery:
    run_id: str
    finding_id: str | None = None
    status: str | None = None
    cursor: str | None = None
    limit: int = 100

    def __post_init__(self) -> None:
        if not self.run_id.strip():
            raise ValueError("run_id must not be empty")
        if self.limit <= 0 or self.limit > 1000:
            raise ValueError("query limit must be between 1 and 1000")


T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class QueryPage(Generic[T]):
    items: tuple[T, ...]
    next_cursor: str | None
    total: int | None = None


@dataclass(frozen=True, slots=True)
class QueryBenchmark:
    query_type: str
    repeats: int
    total_items: int
    elapsed_ms: int


QuerySpec = PageQuery | RunUrlQuery | LinkQuery | ResourceQuery | RedirectQuery | FindingQuery | MetricQuery


def validate_query_spec(query: QuerySpec) -> QuerySpec:
    """Validate an allowlisted typed query before it reaches a store."""
    if not isinstance(query, (PageQuery, RunUrlQuery, LinkQuery, ResourceQuery, RedirectQuery, FindingQuery, MetricQuery)):
        raise TypeError(f"unsupported query specification: {type(query).__name__}")
    return query


class QueryService:
    """Provide identical bounded projections for MemorySiteStore and SQLiteSiteStore."""

    def __init__(self, store: SiteStore) -> None:
        self.store = store

    def execute(self, query: QuerySpec) -> QueryPage[object]:
        """Execute one allowlisted query AST node without arbitrary SQL."""
        validate_query_spec(query)
        if isinstance(query, PageQuery):
            return self.pages(query)
        if isinstance(query, RunUrlQuery):
            return self.run_urls(query)
        if isinstance(query, LinkQuery):
            return self.links(query)
        if isinstance(query, ResourceQuery):
            return self.resources(query)
        if isinstance(query, RedirectQuery):
            return self.redirects(query)
        if isinstance(query, FindingQuery):
            return self.findings(query)
        if isinstance(query, MetricQuery):
            return self.metrics(query)
        raise TypeError(f"unsupported query specification: {type(query).__name__}")

    def count(self, query: QuerySpec) -> int:
        """Return the filtered inventory count from the same typed projection."""
        return self.execute(query).total or 0

    def benchmark(self, query: QuerySpec, *, repeats: int = 3) -> QueryBenchmark:
        if repeats <= 0 or repeats > 100:
            raise ValueError("query benchmark repeats must be between 1 and 100")
        started = time.monotonic()
        total = 0
        for _ in range(repeats):
            total = self.count(query)
        return QueryBenchmark(
            type(query).__name__,
            repeats,
            total,
            int((time.monotonic() - started) * 1000),
        )

    def pages(self, query: PageQuery) -> QueryPage[PageRecord]:
        started = time.monotonic()
        rows = self.store.query_pages(query.run_id, status_code=query.status_code)
        rows = [row for row in rows if query.cursor is None or row.url_key > query.cursor]
        rows.sort(key=lambda row: row.url_key)
        selected = rows[: query.limit + 1]
        page = tuple(selected[: query.limit])
        next_cursor = page[-1].url_key if len(selected) > query.limit else None
        self._log_query("pages", query, len(page), len(rows), started, status=query.status_code)
        return QueryPage(page, next_cursor, len(rows))

    def run_urls(self, query: RunUrlQuery) -> QueryPage[RunUrlRecord]:
        started = time.monotonic()
        rows = list(self.store.iter_run_urls(query.run_id))
        rows = [
            row
            for row in rows
            if (query.state is None or row.state is query.state)
            and (query.cursor is None or row.url_key > query.cursor)
        ]
        rows.sort(key=lambda row: row.url_key)
        selected = rows[: query.limit + 1]
        page = tuple(selected[: query.limit])
        next_cursor = page[-1].url_key if len(selected) > query.limit else None
        self._log_query("run_urls", query, len(page), len(rows), started, state=query.state.value if query.state else None)
        return QueryPage(page, next_cursor, len(rows))

    def links(self, query: LinkQuery) -> QueryPage[LinkOccurrenceRecord]:
        started = time.monotonic()
        rows = [
            row for row in self.store.iter_link_occurrences(query.run_id)
            if query.source_key is None or row.source_key == query.source_key
        ]
        rows.sort(key=lambda row: (row.source_key, row.ordinal, row.raw_href))
        rows = [row for row in rows if query.cursor is None or _link_cursor(row) > query.cursor]
        selected = rows[: query.limit + 1]
        page = tuple(selected[: query.limit])
        next_cursor = _link_cursor(page[-1]) if len(selected) > query.limit else None
        self._log_query("links", query, len(page), len(rows), started, source=query.source_key)
        return QueryPage(page, next_cursor, len(rows))

    def resources(self, query: ResourceQuery) -> QueryPage[ResourceOccurrenceRecord]:
        started = time.monotonic()
        rows = [
            row for row in self.store.iter_resource_occurrences(query.run_id)
            if query.page_key is None or row.page_key == query.page_key
        ]
        rows.sort(key=lambda row: (row.page_key, row.ordinal, row.resource_url))
        rows = [row for row in rows if query.cursor is None or _resource_cursor(row) > query.cursor]
        selected = rows[: query.limit + 1]
        page = tuple(selected[: query.limit])
        next_cursor = _resource_cursor(page[-1]) if len(selected) > query.limit else None
        self._log_query("resources", query, len(page), len(rows), started, page=query.page_key)
        return QueryPage(page, next_cursor, len(rows))

    def metrics(self, query: MetricQuery) -> QueryPage[MetricRecord]:
        started = time.monotonic()
        rows = [
            row for row in self.store.iter_metrics(query.run_id)
            if (query.provider is None or row.provider == query.provider)
            and (query.name is None or row.name == query.name)
        ]
        rows.sort(key=_metric_cursor)
        rows = [row for row in rows if query.cursor is None or _metric_cursor(row) > query.cursor]
        selected = rows[: query.limit + 1]
        page = tuple(selected[: query.limit])
        next_cursor = _metric_cursor(page[-1]) if len(selected) > query.limit else None
        self._log_query("metrics", query, len(page), len(rows), started, provider=query.provider, name=query.name)
        return QueryPage(page, next_cursor, len(rows))

    def redirects(self, query: RedirectQuery) -> QueryPage[RedirectFact]:
        started = time.monotonic()
        rows = [
            row for row in self.store.iter_redirects(query.run_id)
            if (query.from_url is None or row.from_url == query.from_url)
            and (query.status_code is None or row.status_code == query.status_code)
        ]
        rows.sort(key=_redirect_cursor)
        rows = [row for row in rows if query.cursor is None or _redirect_cursor(row) > query.cursor]
        selected = rows[: query.limit + 1]
        page = tuple(selected[: query.limit])
        next_cursor = _redirect_cursor(page[-1]) if len(selected) > query.limit else None
        self._log_query("redirects", query, len(page), len(rows), started, from_url=query.from_url, status=query.status_code)
        return QueryPage(page, next_cursor, len(rows))

    def findings(self, query: FindingQuery) -> QueryPage[FindingRecord]:
        started = time.monotonic()
        rows = [
            row for row in self.store.iter_findings(query.run_id)
            if (query.finding_id is None or row.finding_id == query.finding_id)
            and (query.status is None or row.payload.get("status") == query.status)
        ]
        rows.sort(key=lambda row: row.finding_id)
        rows = [row for row in rows if query.cursor is None or row.finding_id > query.cursor]
        selected = rows[: query.limit + 1]
        page = tuple(selected[: query.limit])
        next_cursor = page[-1].finding_id if len(selected) > query.limit else None
        self._log_query("findings", query, len(page), len(rows), started, finding_id=query.finding_id, status=query.status)
        return QueryPage(page, next_cursor, len(rows))

    @staticmethod
    def _log_query(
        view: str,
        query: QuerySpec,
        page_count: int,
        total: int,
        started: float,
        **filters: object,
    ) -> None:
        query_id = hashlib.sha256(
            json.dumps(
                {"view": view, "run_id": query.run_id, "filters": filters},
                sort_keys=True,
                default=str,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()[:16]
        logger.debug(
            "query view=%s query_id=%s run_id=%s count=%d total=%d duration_ms=%d",
            view,
            query_id,
            query.run_id,
            page_count,
            total,
            int((time.monotonic() - started) * 1000),
        )


def _link_cursor(row: LinkOccurrenceRecord) -> str:
    return f"{row.source_key}\x00{row.ordinal:010d}\x00{row.raw_href}"


def _resource_cursor(row: ResourceOccurrenceRecord) -> str:
    return f"{row.page_key}\x00{row.ordinal:010d}\x00{row.resource_url}"


def _metric_cursor(row: MetricRecord) -> str:
    return f"{row.url_key or ''}\x00{row.provider}\x00{row.name}"


def _redirect_cursor(row: RedirectFact) -> str:
    has_target = "1" if row.to_url is not None else "0"
    return f"{row.from_url}\x00{row.status_code:03d}\x00{has_target}\x00{row.to_url or ''}\x00{row.location_raw}"
