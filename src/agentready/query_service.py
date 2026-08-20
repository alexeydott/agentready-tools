"""Bounded typed query projections over the audit store."""
from __future__ import annotations

import hashlib
import json
import logging
import time
import base64
from dataclasses import dataclass, replace
from typing import Generic, TypeVar

from .audit_core.store import (
    FindingRecord,
    FindingStorageQuery,
    LinkOccurrenceRecord,
    LinkStorageQuery,
    MetricRecord,
    PageRecord,
    PageStorageQuery,
    RedirectFact,
    ResourceOccurrenceRecord,
    ResourceStorageQuery,
    MetricStorageQuery,
    RedirectStorageQuery,
    RunUrlRecord,
    RunUrlState,
    RunUrlStorageQuery,
    SiteStore,
    StorageCursor,
    StoreError,
    _storage_query_hash,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class PageQuery:
    """Allowlisted page query with stable keyset pagination."""

    run_id: str
    status_code: int | None = None
    cursor: str | None = None
    limit: int = 100
    locally_indexable: bool | None = None
    min_depth: int | None = None
    max_depth: int | None = None
    title_contains: str | None = None
    canonical: str | None = None
    sort_by: str = "url"
    descending: bool = False

    def __post_init__(self) -> None:
        if not self.run_id.strip():
            raise ValueError("run_id must not be empty")
        if self.limit <= 0 or self.limit > 1000:
            raise ValueError("query limit must be between 1 and 1000")
        if self.status_code is not None and not 100 <= self.status_code <= 599:
            raise ValueError("status_code must be between 100 and 599")
        if self.min_depth is not None and self.min_depth < 0:
            raise ValueError("min_depth must not be negative")
        if self.max_depth is not None and self.max_depth < 0:
            raise ValueError("max_depth must not be negative")
        if self.min_depth is not None and self.max_depth is not None and self.min_depth > self.max_depth:
            raise ValueError("min_depth must not exceed max_depth")
        if self.sort_by not in {"url", "status", "depth", "title", "canonical", "content_hash"}:
            raise ValueError("unsupported page sort field")


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
    target_key: str | None = None
    rel: str | None = None
    anchor_contains: str | None = None
    internal: bool | None = None
    sort_by: str = "source"
    descending: bool = False

    def __post_init__(self) -> None:
        if not self.run_id.strip():
            raise ValueError("run_id must not be empty")
        if self.limit <= 0 or self.limit > 1000:
            raise ValueError("query limit must be between 1 and 1000")
        if self.sort_by not in {"source", "target", "anchor", "ordinal"}:
            raise ValueError("unsupported link sort field")


@dataclass(frozen=True, slots=True)
class ResourceQuery:
    run_id: str
    page_key: str | None = None
    cursor: str | None = None
    limit: int = 100
    resource_type: str | None = None
    status_code: int | None = None
    sort_by: str = "page"
    descending: bool = False

    def __post_init__(self) -> None:
        if not self.run_id.strip():
            raise ValueError("run_id must not be empty")
        if self.limit <= 0 or self.limit > 1000:
            raise ValueError("query limit must be between 1 and 1000")
        if self.status_code is not None and not 100 <= self.status_code <= 599:
            raise ValueError("status_code must be between 100 and 599")
        if self.sort_by not in {"page", "resource", "type", "status"}:
            raise ValueError("unsupported resource sort field")


@dataclass(frozen=True, slots=True)
class MetricQuery:
    run_id: str
    provider: str | None = None
    name: str | None = None
    cursor: str | None = None
    limit: int = 100
    min_value: float | None = None
    max_value: float | None = None
    sort_by: str = "url"
    descending: bool = False

    def __post_init__(self) -> None:
        if not self.run_id.strip():
            raise ValueError("run_id must not be empty")
        if self.limit <= 0 or self.limit > 1000:
            raise ValueError("query limit must be between 1 and 1000")
        if self.min_value is not None and self.max_value is not None and self.min_value > self.max_value:
            raise ValueError("min_value must not exceed max_value")
        if self.sort_by not in {"url", "provider", "name", "value"}:
            raise ValueError("unsupported metric sort field")


@dataclass(frozen=True, slots=True)
class RedirectQuery:
    run_id: str
    from_url: str | None = None
    status_code: int | None = None
    cursor: str | None = None
    limit: int = 100
    to_url: str | None = None
    sort_by: str = "from_url"
    descending: bool = False

    def __post_init__(self) -> None:
        if not self.run_id.strip():
            raise ValueError("run_id must not be empty")
        if self.limit <= 0 or self.limit > 1000:
            raise ValueError("query limit must be between 1 and 1000")
        if self.status_code is not None and not 300 <= self.status_code <= 399:
            raise ValueError("status_code must be between 300 and 399")
        if self.sort_by not in {"from_url", "to_url", "status"}:
            raise ValueError("unsupported redirect sort field")


@dataclass(frozen=True, slots=True)
class FindingQuery:
    run_id: str
    finding_id: str | None = None
    status: str | None = None
    cursor: str | None = None
    limit: int = 100
    affected_url: str | None = None
    sort_by: str = "finding_id"
    descending: bool = False

    def __post_init__(self) -> None:
        if not self.run_id.strip():
            raise ValueError("run_id must not be empty")
        if self.limit <= 0 or self.limit > 1000:
            raise ValueError("query limit must be between 1 and 1000")
        if self.sort_by not in {"finding_id", "status", "affected_url"}:
            raise ValueError("unsupported finding sort field")


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


def _rebind_cursor(token: str, run_id: str, query_hash: str) -> str:
    """Rebind a valid run cursor when a caller changes only presentation filters.

    Inventory endpoints historically accepted a cursor with a different page
    size (and metrics callers may omit a filter on the follow-up request).
    Preserve the opaque position while retaining run ownership and the current
    query hash for subsequent pages.
    """
    try:
        payload = json.loads(base64.urlsafe_b64decode(token + "=" * (-len(token) % 4)))
        if str(payload.get("run")) != run_id:
            raise ValueError("cursor run mismatch")
        return StorageCursor(run_id, query_hash, tuple(payload["position"])).encode()
    except (ValueError, KeyError, TypeError, json.JSONDecodeError, UnicodeError) as exc:
        raise StoreError("invalid storage cursor") from exc


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

    def summary(self, query: QuerySpec, *, group_by: str = "status", limit: int = 100_000) -> dict[str, int]:
        """Return a bounded deterministic group summary from the same query AST."""
        if limit <= 0 or limit > 100_000:
            raise ValueError("summary limit must be between 1 and 100000")
        allowed = {"status", "status_code", "depth", "type", "provider", "name", "resource_type"}
        if group_by not in allowed:
            raise ValueError("unsupported summary group")
        counts: dict[str, int] = {}
        cursor = query.cursor
        consumed = 0
        while consumed < limit:
            page = self.execute(replace(query, cursor=cursor, limit=min(query.limit, limit - consumed)))
            for item in page.items:
                key = _summary_key(item, group_by)
                counts[key] = counts.get(key, 0) + 1
            consumed += len(page.items)
            if page.next_cursor is None or not page.items:
                break
            cursor = page.next_cursor
        logger.debug("query summary group=%s groups=%d rows=%d", group_by, len(counts), consumed)
        return dict(sorted(counts.items()))

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
        if (
            hasattr(self.store, "query_pages_storage")
            and query.sort_by == "url"
            and not query.descending
            and query.min_depth is None
            and query.max_depth is None
            and query.title_contains is None
            and query.canonical is None
        ):
            storage_query = PageStorageQuery(
                query.run_id,
                limit=query.limit,
                status_code=query.status_code,
                locally_indexable=query.locally_indexable,
            )
            if query.cursor:
                storage_query = replace(
                    storage_query,
                    cursor=StorageCursor(
                        query.run_id,
                        _storage_query_hash(storage_query),
                        (query.cursor,),
                    ).encode(),
                )
            result = self.store.query_pages_storage(storage_query)
            logger.debug("[FIX:query-pushdown] view=pages run_id=%s rows=%d", query.run_id, len(result.items))
            next_cursor = None
            if result.next_cursor:
                next_cursor = StorageCursor.decode(
                    result.next_cursor,
                    run_id=query.run_id,
                    query_hash=_storage_query_hash(storage_query),
                ).position[0]
            self._log_query("pages", query, len(result.items), result.total or 0, started, status=query.status_code, sort=query.sort_by)
            return QueryPage(tuple(result.items), next_cursor, result.total)
        rows = self.store.query_pages(query.run_id, status_code=query.status_code)
        rows = [
            row for row in rows
            if (query.locally_indexable is None or row.locally_indexable is query.locally_indexable)
            and (query.min_depth is None or row.depth >= query.min_depth)
            and (query.max_depth is None or row.depth <= query.max_depth)
            and (query.title_contains is None or query.title_contains.lower() in (row.title or "").lower())
            and (query.canonical is None or row.canonical == query.canonical)
        ]
        if query.sort_by == "url" and not query.descending:
            rows = [row for row in rows if query.cursor is None or row.url_key > query.cursor]
            rows.sort(key=lambda row: row.url_key)
            selected = rows[: query.limit + 1]
            page = tuple(selected[: query.limit])
            next_cursor = page[-1].url_key if len(selected) > query.limit else None
        else:
            page, next_cursor = _paginate_sorted(rows, query, _page_sort_key)
        total = len(rows)
        self._log_query("pages", query, len(page), total, started, status=query.status_code, sort=query.sort_by)
        return QueryPage(page, next_cursor, len(rows))

    def run_urls(self, query: RunUrlQuery) -> QueryPage[RunUrlRecord]:
        started = time.monotonic()
        if hasattr(self.store, "query_run_urls_storage"):
            storage_query = RunUrlStorageQuery(query.run_id, limit=query.limit, state=query.state)
            if query.cursor:
                storage_query = replace(
                    storage_query,
                    cursor=StorageCursor(
                        query.run_id,
                        _storage_query_hash(storage_query),
                        (query.cursor,),
                    ).encode(),
                )
            result = self.store.query_run_urls_storage(storage_query)
            logger.debug("[FIX:query-pushdown] view=run_urls run_id=%s rows=%d", query.run_id, len(result.items))
            next_cursor = None
            if result.next_cursor:
                next_cursor = StorageCursor.decode(
                    result.next_cursor,
                    run_id=query.run_id,
                    query_hash=_storage_query_hash(storage_query),
                ).position[0]
            self._log_query("run_urls", query, len(result.items), result.total or 0, started, state=query.state.value if query.state else None)
            return QueryPage(tuple(result.items), next_cursor, result.total)
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
        if hasattr(self.store, "query_links_storage"):
            storage_query = LinkStorageQuery(query.run_id, limit=query.limit, source_key=query.source_key, target_key=query.target_key, rel=query.rel, anchor_contains=query.anchor_contains, internal=query.internal, sort_key=query.sort_by, descending=query.descending)
            if query.cursor:
                storage_query = replace(storage_query, cursor=query.cursor)
            result = self.store.query_links_storage(storage_query)
            self._log_query("links", query, len(result.items), result.total or 0, started, source=query.source_key)
            return QueryPage(tuple(result.items), result.next_cursor, result.total)
        rows = [
            row for row in self.store.iter_link_occurrences(query.run_id)
            if query.source_key is None or row.source_key == query.source_key
            if query.target_key is None or row.target_key == query.target_key
            if query.rel is None or row.rel == query.rel
            if query.anchor_contains is None or query.anchor_contains.lower() in (row.anchor_text or "").lower()
            if query.internal is None or ((row.target_key is not None) is query.internal)
        ]
        page, next_cursor = _paginate_sorted(rows, query, _link_sort_key)
        self._log_query("links", query, len(page), len(rows), started, source=query.source_key)
        return QueryPage(page, next_cursor, len(rows))

    def resources(self, query: ResourceQuery) -> QueryPage[ResourceOccurrenceRecord]:
        started = time.monotonic()
        if hasattr(self.store, "query_resources_storage"):
            storage_query = ResourceStorageQuery(query.run_id, limit=query.limit, page_key=query.page_key, resource_type=query.resource_type, status_code=query.status_code, sort_key=query.sort_by, descending=query.descending)
            if query.cursor:
                storage_query = replace(storage_query, cursor=query.cursor)
            result = self.store.query_resources_storage(storage_query)
            self._log_query("resources", query, len(result.items), result.total or 0, started, page=query.page_key)
            return QueryPage(tuple(result.items), result.next_cursor, result.total)
        rows = [
            row for row in self.store.iter_resource_occurrences(query.run_id)
            if query.page_key is None or row.page_key == query.page_key
            if query.resource_type is None or row.resource_type == query.resource_type
            if query.status_code is None or row.status_code == query.status_code
        ]
        page, next_cursor = _paginate_sorted(rows, query, _resource_sort_key)
        self._log_query("resources", query, len(page), len(rows), started, page=query.page_key)
        return QueryPage(page, next_cursor, len(rows))

    def metrics(self, query: MetricQuery) -> QueryPage[MetricRecord]:
        started = time.monotonic()
        if hasattr(self.store, "query_metrics_storage"):
            storage_query = MetricStorageQuery(query.run_id, limit=query.limit, provider=query.provider, name=query.name, min_value=query.min_value, max_value=query.max_value, sort_key=query.sort_by, descending=query.descending)
            if query.cursor:
                storage_query = replace(storage_query, cursor=_rebind_cursor(query.cursor, query.run_id, _storage_query_hash(storage_query)))
            result = self.store.query_metrics_storage(storage_query)
            self._log_query("metrics", query, len(result.items), result.total or 0, started, provider=query.provider, name=query.name)
            return QueryPage(tuple(result.items), result.next_cursor, result.total)
        rows = [
            row for row in self.store.iter_metrics(query.run_id)
            if (query.provider is None or row.provider == query.provider)
            and (query.name is None or row.name == query.name)
            and (query.min_value is None or _numeric(row.value) >= query.min_value)
            and (query.max_value is None or _numeric(row.value) <= query.max_value)
        ]
        page, next_cursor = _paginate_sorted(rows, query, _metric_sort_key)
        self._log_query("metrics", query, len(page), len(rows), started, provider=query.provider, name=query.name)
        return QueryPage(page, next_cursor, len(rows))

    def redirects(self, query: RedirectQuery) -> QueryPage[RedirectFact]:
        started = time.monotonic()
        if hasattr(self.store, "query_redirects_storage"):
            storage_query = RedirectStorageQuery(query.run_id, limit=query.limit, from_url=query.from_url, to_url=query.to_url, status_code=query.status_code, sort_key=query.sort_by, descending=query.descending)
            if query.cursor:
                storage_query = replace(storage_query, cursor=query.cursor)
            result = self.store.query_redirects_storage(storage_query)
            self._log_query("redirects", query, len(result.items), result.total or 0, started, from_url=query.from_url, status=query.status_code)
            return QueryPage(tuple(result.items), result.next_cursor, result.total)
        rows = [
            row for row in self.store.iter_redirects(query.run_id)
            if (query.from_url is None or row.from_url == query.from_url)
            and (query.status_code is None or row.status_code == query.status_code)
            and (query.to_url is None or row.to_url == query.to_url)
        ]
        page, next_cursor = _paginate_sorted(rows, query, _redirect_sort_key)
        self._log_query("redirects", query, len(page), len(rows), started, from_url=query.from_url, status=query.status_code)
        return QueryPage(page, next_cursor, len(rows))

    def findings(self, query: FindingQuery) -> QueryPage[FindingRecord]:
        started = time.monotonic()
        if (
            hasattr(self.store, "query_findings_storage")
            and query.sort_by == "finding_id"
            and not query.descending
            and query.affected_url is None
        ):
            storage_query = FindingStorageQuery(
                query.run_id,
                limit=query.limit,
                finding_id=query.finding_id,
                status=query.status,
            )
            if query.cursor:
                storage_query = replace(
                    storage_query,
                    cursor=StorageCursor(
                        query.run_id,
                        _storage_query_hash(storage_query),
                        (query.cursor,),
                    ).encode(),
                )
            result = self.store.query_findings_storage(storage_query)
            logger.debug("[FIX:query-pushdown] view=findings run_id=%s rows=%d", query.run_id, len(result.items))
            next_cursor = None
            if result.next_cursor:
                next_cursor = StorageCursor.decode(
                    result.next_cursor,
                    run_id=query.run_id,
                    query_hash=_storage_query_hash(storage_query),
                ).position[0]
            self._log_query("findings", query, len(result.items), result.total or 0, started, finding_id=query.finding_id, status=query.status)
            return QueryPage(tuple(result.items), next_cursor, result.total)
        rows = [
            row for row in self.store.iter_findings(query.run_id)
            if (query.finding_id is None or row.finding_id == query.finding_id)
            and (query.status is None or row.payload.get("status") == query.status)
            and (query.affected_url is None or query.affected_url in tuple(row.payload.get("affected_urls", ())))
        ]
        page, next_cursor = _paginate_sorted(rows, query, _finding_sort_key)
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


def _numeric(value: object) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _page_sort_key(row: PageRecord, field: str) -> tuple[object, str]:
    value = {
        "url": row.url_key,
        "status": row.status_code or 0,
        "depth": row.depth,
        "title": (row.title or "").lower(),
        "canonical": row.canonical or "",
        "content_hash": row.content_hash or "",
    }[field]
    return value, row.url_key


def _link_sort_key(row: LinkOccurrenceRecord, field: str) -> tuple[object, str, int, str]:
    value = {
        "source": row.source_key,
        "target": row.target_key or "",
        "anchor": (row.anchor_text or "").lower(),
        "ordinal": row.ordinal,
    }[field]
    return value, row.source_key, row.ordinal, row.raw_href


def _resource_sort_key(row: ResourceOccurrenceRecord, field: str) -> tuple[object, str, int, str]:
    value = {
        "page": row.page_key,
        "resource": row.resource_url,
        "type": row.resource_type,
        "status": row.status_code or 0,
    }[field]
    return value, row.page_key, row.ordinal, row.resource_url


def _metric_sort_key(row: MetricRecord, field: str) -> tuple[object, str, str, str]:
    value = {
        "url": row.url_key or "",
        "provider": row.provider,
        "name": row.name,
        "value": _numeric(row.value),
    }[field]
    return value, row.url_key or "", row.provider, row.name


def _redirect_sort_key(row: RedirectFact, field: str) -> tuple[object, str, int, str, str]:
    value = {
        "from_url": row.from_url,
        "to_url": row.to_url or "",
        "status": row.status_code,
    }[field]
    return value, row.from_url, row.status_code, row.to_url or "", row.location_raw


def _finding_sort_key(row: FindingRecord, field: str) -> tuple[object, str]:
    affected = tuple(row.payload.get("affected_urls", ()))
    value = {
        "finding_id": row.finding_id,
        "status": str(row.payload.get("status", "")),
        "affected_url": affected[0] if affected else "",
    }[field]
    return value, row.finding_id


def _paginate_sorted(rows: list[object], query: object, key_builder) -> tuple[tuple[object, ...], str | None]:
    descending = bool(query.descending)
    sort_by = str(query.sort_by)
    rows.sort(key=lambda row: key_builder(row, sort_by), reverse=descending)
    cursor = query.cursor
    if cursor:
        # Cursors are opaque serialized typed keys. Resume by locating the exact
        # key in the already sorted sequence so numeric values and descending
        # order retain their native semantics.
        keys = [_cursor_key(key_builder(row, sort_by)) for row in rows]
        try:
            rows = rows[keys.index(cursor) + 1 :]
        except ValueError:
            # A missing/old cursor starts a fresh page rather than applying an
            # arbitrary filtering rule.
            pass
    selected = rows[: int(query.limit) + 1]
    page = tuple(selected[: int(query.limit)])
    next_cursor = _cursor_key(key_builder(page[-1], sort_by)) if len(selected) > len(page) else None
    logger.debug(
        "[FIX:v2-cursor] sorted page sort_by=%s descending=%s has_cursor=%s rows=%d has_next=%s",
        sort_by,
        descending,
        bool(cursor),
        len(page),
        bool(next_cursor),
    )
    return page, next_cursor


def _cursor_key(value: tuple[object, ...]) -> str:
    return "\x00".join(str(item) for item in value)


def _summary_key(item: object, group_by: str) -> str:
    if group_by == "status_code":
        value = getattr(item, "status_code", None)
    elif group_by == "depth":
        value = getattr(item, "depth", None)
    elif group_by in {"type", "resource_type"}:
        value = getattr(item, "resource_type", None)
    elif group_by == "provider":
        value = getattr(item, "provider", None)
    elif group_by == "name":
        value = getattr(item, "name", None)
    else:
        value = getattr(item, "state", None)
        if value is None and hasattr(item, "payload"):
            value = item.payload.get("status")
        if value is None:
            value = getattr(item, "status_code", None)
    return str(getattr(value, "value", value) if value is not None else "unknown")
