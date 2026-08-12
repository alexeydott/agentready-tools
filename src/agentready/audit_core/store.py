"""Memory and SQLite SiteStore contracts for deterministic audit persistence."""
from __future__ import annotations

import json
import logging
import sqlite3
import threading
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, Protocol

from agentready.security import SecretRedactor

from .urls import UrlIdentity

logger = logging.getLogger(__name__)
SCHEMA_VERSION = 4


class StoreError(RuntimeError):
    """Raised when a store cannot safely satisfy an operation."""


class ContentRetention(StrEnum):
    METADATA_ONLY = "metadata-only"
    SAMPLES = "samples"
    FULL_CONTENT = "full-content"


@dataclass(frozen=True, slots=True)
class RunRecord:
    id: str
    config_hash: str
    tool_version: str
    rule_catalog_version: str
    state: str = "running"
    started_at: str = ""
    finished_at: str | None = None

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise ValueError("run id must not be empty")
        if not self.started_at:
            object.__setattr__(self, "started_at", _now())


class RunUrlState(StrEnum):
    DISCOVERED = "discovered"
    QUEUED = "queued"
    FETCHING = "fetching"
    FETCHED = "fetched"
    PARSED = "parsed"
    SKIPPED = "skipped"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class RunUrlRecord:
    run_id: str
    url_key: str
    state: RunUrlState
    depth: int = 0
    attempts: int = 0
    error_kind: str | None = None


@dataclass(frozen=True, slots=True)
class PageRecord:
    run_id: str
    url_key: str
    requested_url: str
    final_url: str | None = None
    depth: int = 0
    status_code: int | None = None
    content_type: str | None = None
    title: str | None = None
    canonical: str | None = None
    locally_indexable: bool | None = None
    content_hash: str | None = None
    content: str | None = None


@dataclass(frozen=True, slots=True)
class FetchFact:
    id: str
    run_id: str
    request_url: str
    final_url: str | None = None
    status_code: int | None = None
    error_kind: str | None = None
    total_ms: float | None = None
    wire_bytes: int | None = None
    decoded_bytes: int | None = None
    body_hash: str | None = None


@dataclass(frozen=True, slots=True)
class RedirectFact:
    run_id: str
    from_url: str
    to_url: str | None
    status_code: int
    location_raw: str


@dataclass(frozen=True, slots=True)
class FindingRecord:
    run_id: str
    finding_id: str
    payload: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class LinkOccurrenceRecord:
    run_id: str
    source_key: str
    ordinal: int
    raw_href: str
    target_key: str | None = None
    resolved_url: str | None = None
    rel_flags: int = 0
    anchor_text: str | None = None
    discovery_method: str = "parser"
    representation_id: str | None = None
    rel: str | None = None
    element: str | None = None
    dom_path: str | None = None


@dataclass(frozen=True, slots=True)
class ResourceOccurrenceRecord:
    run_id: str
    page_key: str
    ordinal: int
    resource_url: str
    resource_type: str
    status_code: int | None = None
    resolved_url: str | None = None
    representation_id: str | None = None
    element: str | None = None
    dom_path: str | None = None


@dataclass(frozen=True, slots=True)
class MetricRecord:
    run_id: str
    url_key: str | None
    provider: str
    name: str
    value: Any
    unit: str | None
    source: str
    version: str
    observed_at: str
    kind: str = "enrichment"


class SiteStore(Protocol):
    def begin_run(self, run: RunRecord) -> RunRecord: ...
    def update_run_state(self, run_id: str, state: str, *, finished_at: str | None = None) -> None: ...
    def put_run_url(self, record: RunUrlRecord) -> None: ...
    def put_fetch(self, fetch: FetchFact) -> None: ...
    def put_url(self, identity: UrlIdentity) -> None: ...
    def put_redirect(self, redirect: RedirectFact) -> None: ...
    def put_page(self, page: PageRecord) -> None: ...
    def put_link(self, run_id: str, source_key: str, raw_href: str, *, target_key: str | None = None,
                resolved_url: str | None = None, rel_flags: int = 0, anchor_text: str | None = None,
                discovery_method: str = "parser", ordinal: int = 0, representation_id: str | None = None,
                rel: str | None = None, element: str | None = None, dom_path: str | None = None) -> None: ...
    def put_resource(self, run_id: str, page_key: str, resource_url: str, resource_type: str,
                     *, status_code: int | None = None, ordinal: int = 0,
                     resolved_url: str | None = None, representation_id: str | None = None,
                     element: str | None = None, dom_path: str | None = None) -> None: ...
    def put_metric(self, metric: MetricRecord) -> None: ...
    def put_evidence(self, run_id: str, evidence_id: str, payload: Mapping[str, Any]) -> None: ...
    def put_finding(self, run_id: str, finding_id: str, payload: Mapping[str, Any]) -> None: ...
    def put_coverage(self, run_id: str, payload: Mapping[str, Any]) -> None: ...
    def put_version_manifest(self, run_id: str, payload: Mapping[str, Any]) -> None: ...
    def iter_pages(self, run_id: str) -> Iterator[PageRecord]: ...
    def iter_run_urls(self, run_id: str) -> Iterator[RunUrlRecord]: ...
    def query_pages(self, run_id: str, *, status_code: int | None = None) -> list[PageRecord]: ...
    def iter_link_occurrences(self, run_id: str) -> Iterator[LinkOccurrenceRecord]: ...
    def iter_resource_occurrences(self, run_id: str) -> Iterator[ResourceOccurrenceRecord]: ...
    def iter_metrics(self, run_id: str) -> Iterator[MetricRecord]: ...
    def iter_redirects(self, run_id: str) -> Iterator[RedirectFact]: ...
    def iter_findings(self, run_id: str) -> Iterator[FindingRecord]: ...
    def recover_interrupted_runs(self) -> int: ...
    def resume_run(self, run_id: str) -> RunRecord: ...
    def close(self) -> None: ...


class MemorySiteStore:
    """Deterministic in-memory store used for unit tests and small audits."""

    def __init__(self, *, retention: ContentRetention = ContentRetention.METADATA_ONLY) -> None:
        self.retention = retention
        self._runs: dict[str, RunRecord] = {}
        self._pages: dict[tuple[str, str], PageRecord] = {}
        self._run_urls: dict[tuple[str, str], RunUrlRecord] = {}
        self._fetches: dict[str, FetchFact] = {}
        self._urls: dict[str, UrlIdentity] = {}
        self._redirects: dict[tuple[str, str, str], RedirectFact] = {}
        self._links: dict[tuple[str, str, str], dict[str, Any]] = {}
        self._link_occurrences: dict[tuple[str, str, str, int], LinkOccurrenceRecord] = {}
        self._resource_occurrences: dict[tuple[str, str, str, int], ResourceOccurrenceRecord] = {}
        self._metrics: dict[tuple[str, str | None, str, str], MetricRecord] = {}
        self._evidence: dict[tuple[str, str], dict[str, Any]] = {}
        self._findings: dict[tuple[str, str], dict[str, Any]] = {}
        self._redactor = SecretRedactor()

    def begin_run(self, run: RunRecord) -> RunRecord:
        existing = self._runs.get(run.id)
        if existing is not None:
            return existing
        self._runs[run.id] = run
        logger.debug("[WP3.1] memory run created id=%s", run.id)
        return run

    def update_run_state(self, run_id: str, state: str, *, finished_at: str | None = None) -> None:
        run = self._runs[run_id]
        self._runs[run_id] = RunRecord(**{
            **asdict(run),
            "state": state,
            "finished_at": finished_at if finished_at is not None else run.finished_at,
        })

    def put_fetch(self, fetch: FetchFact) -> None:
        self._fetches.setdefault(fetch.id, fetch)

    def put_run_url(self, record: RunUrlRecord) -> None:
        self._run_urls[(record.run_id, record.url_key)] = record

    def put_url(self, identity: UrlIdentity) -> None:
        self._urls.setdefault(identity.normalized(), identity)

    def put_redirect(self, redirect: RedirectFact) -> None:
        self._redirects.setdefault((redirect.run_id, redirect.from_url, redirect.to_url or ""), redirect)

    def put_page(self, page: PageRecord) -> None:
        content = _retained_content(page.content, self.retention)
        self._pages[(page.run_id, page.url_key)] = PageRecord(**{**asdict(page), "content": content})

    def put_link(self, run_id: str, source_key: str, raw_href: str, **kwargs: Any) -> None:
        key = (run_id, source_key, raw_href)
        self._links.setdefault(key, {"run_id": run_id, "source_key": source_key, "raw_href": raw_href, **kwargs})
        record = LinkOccurrenceRecord(run_id, source_key, int(kwargs.get("ordinal", 0)), raw_href, **{
            key: kwargs.get(key)
            for key in (
                "target_key", "resolved_url", "rel_flags", "anchor_text", "discovery_method",
                "representation_id", "rel", "element", "dom_path",
            )
        })
        self._link_occurrences.setdefault(
            (run_id, source_key, record.representation_id or "", record.ordinal),
            record,
        )

    def put_resource(self, run_id: str, page_key: str, resource_url: str, resource_type: str, **kwargs: Any) -> None:
        self._evidence.setdefault(
            (run_id, f"resource:{page_key}:{resource_url}"),
            {"run_id": run_id, "page_key": page_key, "resource_url": resource_url,
             "resource_type": resource_type, "status_code": kwargs.get("status_code")},
        )
        record = ResourceOccurrenceRecord(
            run_id,
            page_key,
            int(kwargs.get("ordinal", 0)),
            resource_url,
            resource_type,
            status_code=kwargs.get("status_code"),
            resolved_url=kwargs.get("resolved_url"),
            representation_id=kwargs.get("representation_id"),
            element=kwargs.get("element"),
            dom_path=kwargs.get("dom_path"),
        )
        self._resource_occurrences.setdefault(
            (run_id, page_key, record.representation_id or "", record.ordinal),
            record,
        )

    def put_metric(self, metric: MetricRecord) -> None:
        self._metrics[(metric.run_id, metric.url_key, metric.provider, metric.name)] = metric

    def put_evidence(self, run_id: str, evidence_id: str, payload: Mapping[str, Any]) -> None:
        self._evidence.setdefault((run_id, evidence_id), self._redactor.value(dict(payload)))

    def put_finding(self, run_id: str, finding_id: str, payload: Mapping[str, Any]) -> None:
        self._findings.setdefault((run_id, finding_id), self._redactor.value(dict(payload)))

    def put_coverage(self, run_id: str, payload: Mapping[str, Any]) -> None:
        self._evidence.setdefault((run_id, "coverage"), self._redactor.value(dict(payload)))

    def put_version_manifest(self, run_id: str, payload: Mapping[str, Any]) -> None:
        self._evidence.setdefault((run_id, "version-manifest"), self._redactor.value(dict(payload)))

    def iter_pages(self, run_id: str) -> Iterator[PageRecord]:
        yield from sorted(
            (page for (page_run, _), page in self._pages.items() if page_run == run_id),
            key=lambda page: page.url_key,
        )

    def iter_run_urls(self, run_id: str) -> Iterator[RunUrlRecord]:
        yield from sorted(
            (record for (record_run, _), record in self._run_urls.items() if record_run == run_id),
            key=lambda record: record.url_key,
        )

    def query_pages(self, run_id: str, *, status_code: int | None = None) -> list[PageRecord]:
        pages = list(self.iter_pages(run_id))
        return [page for page in pages if status_code is None or page.status_code == status_code]

    def iter_link_occurrences(self, run_id: str) -> Iterator[LinkOccurrenceRecord]:
        yield from sorted(
            (record for key, record in self._link_occurrences.items() if key[0] == run_id),
            key=lambda record: (record.source_key, record.ordinal, record.raw_href),
        )

    def iter_resource_occurrences(self, run_id: str) -> Iterator[ResourceOccurrenceRecord]:
        yield from sorted(
            (record for key, record in self._resource_occurrences.items() if key[0] == run_id),
            key=lambda record: (record.page_key, record.ordinal, record.resource_url),
        )

    def iter_metrics(self, run_id: str) -> Iterator[MetricRecord]:
        yield from sorted(
            (record for key, record in self._metrics.items() if key[0] == run_id),
            key=lambda record: (record.url_key or "", record.provider, record.name),
        )

    def iter_redirects(self, run_id: str) -> Iterator[RedirectFact]:
        yield from sorted(
            (redirect for (redirect_run, _, _), redirect in self._redirects.items() if redirect_run == run_id),
            key=lambda redirect: (
                redirect.from_url, redirect.status_code, redirect.to_url is not None,
                redirect.to_url or "", redirect.location_raw,
            ),
        )

    def iter_findings(self, run_id: str) -> Iterator[FindingRecord]:
        yield from sorted(
            (
                FindingRecord(run_id, finding_id, dict(payload))
                for (finding_run, finding_id), payload in self._findings.items()
                if finding_run == run_id
            ),
            key=lambda finding: finding.finding_id,
        )

    def recover_interrupted_runs(self) -> int:
        changed = 0
        for run_id, run in list(self._runs.items()):
            if run.state == "running":
                self._runs[run_id] = RunRecord(**{**asdict(run), "state": "interrupted"})
                changed += 1
        return changed

    def resume_run(self, run_id: str) -> RunRecord:
        run = self._runs[run_id]
        resumed = RunRecord(**{**asdict(run), "state": "running", "finished_at": None})
        self._runs[run_id] = resumed
        return resumed

    def close(self) -> None:
        return None


class SQLiteSiteStore:
    """SQLite project store with forward-only migrations and serialized writes."""

    def __init__(
        self,
        path: str | Path,
        *,
        retention: ContentRetention = ContentRetention.METADATA_ONLY,
        read_only: bool = False,
        synchronous: str = "NORMAL",
    ) -> None:
        self.path = Path(path)
        self.retention = retention
        self.read_only = read_only
        self._lock = threading.RLock()
        uri = f"file:{self.path.as_posix()}?mode=ro" if read_only else str(self.path)
        self._connection = sqlite3.connect(uri, uri=read_only, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._redactor = SecretRedactor()
        self._configure(synchronous)
        self._migrate()
        self.recover_interrupted_runs()

    def _configure(self, synchronous: str) -> None:
        self._connection.execute("PRAGMA foreign_keys=ON")
        if self.read_only:
            return
        journal = self._connection.execute("PRAGMA journal_mode=WAL").fetchone()[0]
        if journal.lower() != "wal":
            raise StoreError(f"SQLite WAL unavailable; received journal mode {journal}")
        if synchronous.upper() not in {"NORMAL", "FULL"}:
            raise ValueError("synchronous must be NORMAL or FULL")
        self._connection.execute(f"PRAGMA synchronous={synchronous.upper()}")

    def _migrate(self) -> None:
        version = int(self._connection.execute("PRAGMA user_version").fetchone()[0])
        if version > SCHEMA_VERSION:
            if not self.read_only:
                raise StoreError(f"database schema {version} is newer than supported {SCHEMA_VERSION}")
            return
        if self.read_only:
            if version < SCHEMA_VERSION:
                raise StoreError("read-only database requires an up-to-date schema")
            return
        with self._transaction():
            if version == 0:
                self._connection.executescript(_INITIAL_SCHEMA)
                self._connection.execute(
                    "INSERT OR IGNORE INTO schema_migrations(version, applied_at) VALUES (?, ?)",
                    (SCHEMA_VERSION, _now()),
                )
                self._connection.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
            elif version == 1:
                self._connection.executescript(_MIGRATION_2)
                self._connection.executescript(_MIGRATION_3)
                self._connection.execute(
                    "INSERT OR IGNORE INTO schema_migrations(version, applied_at) VALUES (?, ?)",
                    (SCHEMA_VERSION, _now()),
                )
                self._connection.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
            elif version == 2:
                self._connection.executescript(_MIGRATION_3)
                self._connection.executescript(_MIGRATION_4)
                self._connection.execute(
                    "INSERT OR IGNORE INTO schema_migrations(version, applied_at) VALUES (?, ?)",
                    (SCHEMA_VERSION, _now()),
                )
                self._connection.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
            elif version == 3:
                self._connection.executescript(_MIGRATION_4)
                self._connection.execute(
                    "INSERT OR IGNORE INTO schema_migrations(version, applied_at) VALUES (?, ?)",
                    (SCHEMA_VERSION, _now()),
                )
                self._connection.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
            self._connection.execute("PRAGMA optimize")

    @contextmanager
    def _transaction(self) -> Iterator[None]:
        with self._lock:
            try:
                self._connection.execute("BEGIN")
                yield
            except Exception:
                self._connection.rollback()
                raise
            else:
                self._connection.commit()

    def _write_guard(self) -> None:
        if self.read_only:
            raise StoreError("store is read-only because its schema is newer than supported")

    def begin_run(self, run: RunRecord) -> RunRecord:
        self._write_guard()
        with self._transaction():
            self._connection.execute(
                "INSERT OR IGNORE INTO runs(id, started_at, config_hash, tool_version, rule_catalog_version, state) VALUES (?, ?, ?, ?, ?, ?)",
                (run.id, run.started_at, run.config_hash, run.tool_version, run.rule_catalog_version, run.state),
            )
            row = self._connection.execute("SELECT * FROM runs WHERE id=?", (run.id,)).fetchone()
        return _run_from_row(row)

    def update_run_state(self, run_id: str, state: str, *, finished_at: str | None = None) -> None:
        self._write_guard()
        with self._transaction():
            self._connection.execute(
                "UPDATE runs SET state=?, finished_at=? WHERE id=?",
                (state, finished_at, run_id),
            )

    def put_fetch(self, fetch: FetchFact) -> None:
        self._write_guard()
        with self._transaction():
            self._connection.execute(
                """INSERT OR REPLACE INTO fetches
                (id, run_id, request_url, final_url, status_code, error_kind, total_ms, wire_bytes, decoded_bytes, body_hash)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                tuple(asdict(fetch).values()),
            )

    def put_run_url(self, record: RunUrlRecord) -> None:
        self._write_guard()
        with self._transaction():
            self._connection.execute(
                """INSERT OR REPLACE INTO run_urls
                (run_id, url_key, state, depth, attempts, error_kind)
                VALUES (?, ?, ?, ?, ?, ?)""",
                (record.run_id, record.url_key, record.state.value, record.depth, record.attempts, record.error_kind),
            )

    def put_url(self, identity: UrlIdentity) -> None:
        self._write_guard()
        with self._transaction():
            self._connection.execute(
                """INSERT OR IGNORE INTO urls(url_key, url, scheme, host, port, path, query)
                VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (identity.normalized(), identity.original, identity.scheme, identity.host,
                 identity.port, identity.path, identity.query),
            )

    def put_redirect(self, redirect: RedirectFact) -> None:
        self._write_guard()
        with self._transaction():
            self._connection.execute(
                "INSERT OR IGNORE INTO redirects(run_id, from_url, to_url, status_code, location_raw) VALUES (?, ?, ?, ?, ?)",
                (redirect.run_id, redirect.from_url, redirect.to_url, redirect.status_code, redirect.location_raw),
            )

    def put_page(self, page: PageRecord) -> None:
        self._write_guard()
        content = _retained_content(page.content, self.retention)
        with self._transaction():
            self._connection.execute(
                """INSERT OR REPLACE INTO pages
                (run_id, url_key, requested_url, final_url, depth, status_code, content_type, title, canonical,
                 locally_indexable, content_hash, content)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (page.run_id, page.url_key, page.requested_url, page.final_url, page.depth, page.status_code,
                 page.content_type, page.title, page.canonical,
                 None if page.locally_indexable is None else int(page.locally_indexable), page.content_hash, content),
            )

    def put_link(self, run_id: str, source_key: str, raw_href: str, **kwargs: Any) -> None:
        self._write_guard()
        with self._transaction():
            self._connection.execute(
                """INSERT OR IGNORE INTO links
                (run_id, source_key, raw_href, target_key, resolved_url, rel_flags, anchor_text, discovery_method)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (run_id, source_key, raw_href, kwargs.get("target_key"), kwargs.get("resolved_url"),
                 kwargs.get("rel_flags", 0), kwargs.get("anchor_text"), kwargs.get("discovery_method", "parser")),
            )
            self._connection.execute(
                """INSERT OR IGNORE INTO link_occurrences
                (run_id, source_key, ordinal, raw_href, target_key, resolved_url, rel_flags, anchor_text,
                 discovery_method, representation_id, rel, element, dom_path)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    run_id, source_key, int(kwargs.get("ordinal", 0)), raw_href, kwargs.get("target_key"),
                    kwargs.get("resolved_url"), kwargs.get("rel_flags", 0), kwargs.get("anchor_text"),
                    kwargs.get("discovery_method", "parser"), kwargs.get("representation_id") or "",
                    kwargs.get("rel"), kwargs.get("element"), kwargs.get("dom_path"),
                ),
            )

    def put_resource(self, run_id: str, page_key: str, resource_url: str, resource_type: str, **kwargs: Any) -> None:
        self._write_guard()
        with self._transaction():
            self._connection.execute(
                """INSERT OR IGNORE INTO resources(run_id, page_key, resource_url, resource_type, status_code)
                VALUES (?, ?, ?, ?, ?)""",
                (run_id, page_key, resource_url, resource_type, kwargs.get("status_code")),
            )
            self._connection.execute(
                """INSERT OR IGNORE INTO resource_occurrences
                (run_id, page_key, ordinal, resource_url, resource_type, status_code, resolved_url,
                 representation_id, element, dom_path)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    run_id, page_key, int(kwargs.get("ordinal", 0)), resource_url, resource_type,
                    kwargs.get("status_code"), kwargs.get("resolved_url"), kwargs.get("representation_id") or "",
                    kwargs.get("element"), kwargs.get("dom_path"),
                ),
            )

    def put_metric(self, metric: MetricRecord) -> None:
        self._write_guard()
        with self._transaction():
            self._connection.execute(
                """INSERT OR REPLACE INTO metrics
                (run_id, url_key, provider, name, value, unit, source, version, observed_at, kind)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    metric.run_id,
                    metric.url_key,
                    metric.provider,
                    metric.name,
                    json.dumps(metric.value, sort_keys=True, default=str),
                    metric.unit,
                    metric.source,
                    metric.version,
                    metric.observed_at,
                    metric.kind,
                ),
            )

    def put_evidence(self, run_id: str, evidence_id: str, payload: Mapping[str, Any]) -> None:
        self._put_json("evidence", run_id, evidence_id, payload)

    def put_finding(self, run_id: str, finding_id: str, payload: Mapping[str, Any]) -> None:
        self._put_json("findings", run_id, finding_id, payload)

    def put_coverage(self, run_id: str, payload: Mapping[str, Any]) -> None:
        self._put_json("coverage", run_id, "coverage", payload)

    def put_version_manifest(self, run_id: str, payload: Mapping[str, Any]) -> None:
        self._put_json("version_manifests", run_id, "manifest", payload)

    def _put_json(self, table: str, run_id: str, item_id: str, payload: Mapping[str, Any]) -> None:
        self._write_guard()
        safe = json.dumps(self._redactor.value(dict(payload)), sort_keys=True, separators=(",", ":"))
        with self._transaction():
            self._connection.execute(
                f"INSERT OR REPLACE INTO {table}(run_id, item_id, payload) VALUES (?, ?, ?)",
                (run_id, item_id, safe),
            )

    def iter_pages(self, run_id: str) -> Iterator[PageRecord]:
        rows = self._connection.execute("SELECT * FROM pages WHERE run_id=? ORDER BY url_key", (run_id,))
        for row in rows:
            yield _page_from_row(row)

    def iter_run_urls(self, run_id: str) -> Iterator[RunUrlRecord]:
        rows = self._connection.execute("SELECT * FROM run_urls WHERE run_id=? ORDER BY url_key", (run_id,))
        for row in rows:
            yield RunUrlRecord(
                run_id=row["run_id"],
                url_key=row["url_key"],
                state=RunUrlState(row["state"]),
                depth=row["depth"],
                attempts=row["attempts"],
                error_kind=row["error_kind"],
            )

    def query_pages(self, run_id: str, *, status_code: int | None = None) -> list[PageRecord]:
        if status_code is None:
            return list(self.iter_pages(run_id))
        return [_page_from_row(row) for row in self._connection.execute(
            "SELECT * FROM pages WHERE run_id=? AND status_code=? ORDER BY url_key", (run_id, status_code)
        )]

    def iter_link_occurrences(self, run_id: str) -> Iterator[LinkOccurrenceRecord]:
        rows = self._connection.execute(
            "SELECT * FROM link_occurrences WHERE run_id=? ORDER BY source_key, ordinal, raw_href",
            (run_id,),
        )
        for row in rows:
            yield LinkOccurrenceRecord(
                run_id=row["run_id"], source_key=row["source_key"], ordinal=row["ordinal"],
                raw_href=row["raw_href"], target_key=row["target_key"], resolved_url=row["resolved_url"],
                rel_flags=row["rel_flags"], anchor_text=row["anchor_text"],
                discovery_method=row["discovery_method"], representation_id=row["representation_id"] or None,
                rel=row["rel"], element=row["element"], dom_path=row["dom_path"],
            )

    def iter_resource_occurrences(self, run_id: str) -> Iterator[ResourceOccurrenceRecord]:
        rows = self._connection.execute(
            "SELECT * FROM resource_occurrences WHERE run_id=? ORDER BY page_key, ordinal, resource_url",
            (run_id,),
        )
        for row in rows:
            yield ResourceOccurrenceRecord(
                run_id=row["run_id"], page_key=row["page_key"], ordinal=row["ordinal"],
                resource_url=row["resource_url"], resource_type=row["resource_type"],
                status_code=row["status_code"], resolved_url=row["resolved_url"],
                representation_id=row["representation_id"] or None, element=row["element"], dom_path=row["dom_path"],
            )

    def iter_metrics(self, run_id: str) -> Iterator[MetricRecord]:
        rows = self._connection.execute(
            "SELECT * FROM metrics WHERE run_id=? ORDER BY COALESCE(url_key, ''), provider, name",
            (run_id,),
        )
        for row in rows:
            yield MetricRecord(
                run_id=row["run_id"],
                url_key=row["url_key"],
                provider=row["provider"],
                name=row["name"],
                value=json.loads(row["value"]),
                unit=row["unit"],
                source=row["source"],
                version=row["version"],
                observed_at=row["observed_at"],
                kind=row["kind"],
            )

    def iter_redirects(self, run_id: str) -> Iterator[RedirectFact]:
        rows = self._connection.execute(
            "SELECT * FROM redirects WHERE run_id=? ORDER BY from_url, status_code, to_url, location_raw",
            (run_id,),
        )
        for row in rows:
            yield RedirectFact(
                run_id=row["run_id"], from_url=row["from_url"], to_url=row["to_url"],
                status_code=row["status_code"], location_raw=row["location_raw"],
            )

    def iter_findings(self, run_id: str) -> Iterator[FindingRecord]:
        rows = self._connection.execute(
            "SELECT item_id, payload FROM findings WHERE run_id=? ORDER BY item_id",
            (run_id,),
        )
        for row in rows:
            yield FindingRecord(run_id, row["item_id"], json.loads(row["payload"]))

    def recover_interrupted_runs(self) -> int:
        if self.read_only:
            return 0
        with self._transaction():
            cursor = self._connection.execute("UPDATE runs SET state='interrupted' WHERE state='running'")
        return cursor.rowcount

    def resume_run(self, run_id: str) -> RunRecord:
        self._write_guard()
        with self._transaction():
            self._connection.execute(
                "UPDATE runs SET state='running', finished_at=NULL WHERE id=? AND state IN ('interrupted', 'running')",
                (run_id,),
            )
            row = self._connection.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
        if row is None:
            raise StoreError(f"run not found: {run_id}")
        return _run_from_row(row)

    def close(self) -> None:
        self._connection.close()


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _retained_content(content: str | None, retention: ContentRetention) -> str | None:
    if content is None or retention == ContentRetention.METADATA_ONLY:
        return None
    if retention == ContentRetention.SAMPLES:
        return content[:4096]
    return content


def _run_from_row(row: sqlite3.Row) -> RunRecord:
    return RunRecord(
        id=row["id"], config_hash=row["config_hash"], tool_version=row["tool_version"],
        rule_catalog_version=row["rule_catalog_version"], state=row["state"],
        started_at=row["started_at"], finished_at=row["finished_at"],
    )


def _page_from_row(row: sqlite3.Row) -> PageRecord:
    return PageRecord(
        run_id=row["run_id"], url_key=row["url_key"], requested_url=row["requested_url"],
        final_url=row["final_url"], depth=row["depth"], status_code=row["status_code"],
        content_type=row["content_type"], title=row["title"], canonical=row["canonical"],
        locally_indexable=None if row["locally_indexable"] is None else bool(row["locally_indexable"]),
        content_hash=row["content_hash"], content=row["content"],
    )


_INITIAL_SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
) STRICT;
CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    config_hash TEXT NOT NULL,
    tool_version TEXT NOT NULL,
    rule_catalog_version TEXT NOT NULL,
    state TEXT NOT NULL
) STRICT;
CREATE TABLE IF NOT EXISTS fetches (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES runs(id),
    request_url TEXT NOT NULL,
    final_url TEXT,
    status_code INTEGER,
    error_kind TEXT,
    total_ms REAL,
    wire_bytes INTEGER,
    decoded_bytes INTEGER,
    body_hash TEXT
) STRICT;
CREATE TABLE IF NOT EXISTS urls (
    id INTEGER PRIMARY KEY,
    url_key TEXT NOT NULL UNIQUE,
    url TEXT NOT NULL,
    scheme TEXT NOT NULL,
    host TEXT NOT NULL,
    port INTEGER,
    path TEXT NOT NULL,
    query TEXT
) STRICT;
CREATE INDEX IF NOT EXISTS idx_urls_host ON urls(host);
CREATE TABLE IF NOT EXISTS pages (
    run_id TEXT NOT NULL REFERENCES runs(id),
    url_key TEXT NOT NULL,
    requested_url TEXT NOT NULL,
    final_url TEXT,
    depth INTEGER NOT NULL,
    status_code INTEGER,
    content_type TEXT,
    title TEXT,
    canonical TEXT,
    locally_indexable INTEGER,
    content_hash TEXT,
    content TEXT,
    PRIMARY KEY(run_id, url_key)
) STRICT;
CREATE TABLE IF NOT EXISTS run_urls (
    run_id TEXT NOT NULL REFERENCES runs(id),
    url_key TEXT NOT NULL,
    state TEXT NOT NULL,
    depth INTEGER NOT NULL,
    attempts INTEGER NOT NULL,
    error_kind TEXT,
    PRIMARY KEY(run_id, url_key)
) STRICT;
CREATE INDEX IF NOT EXISTS idx_run_urls_run_state ON run_urls(run_id, state);
CREATE TABLE IF NOT EXISTS links (
    run_id TEXT NOT NULL REFERENCES runs(id),
    source_key TEXT NOT NULL,
    raw_href TEXT NOT NULL,
    target_key TEXT,
    resolved_url TEXT,
    rel_flags INTEGER NOT NULL,
    anchor_text TEXT,
    discovery_method TEXT NOT NULL,
    PRIMARY KEY(run_id, source_key, raw_href)
) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS link_occurrences (
    run_id TEXT NOT NULL REFERENCES runs(id),
    source_key TEXT NOT NULL,
    ordinal INTEGER NOT NULL,
    raw_href TEXT NOT NULL,
    target_key TEXT,
    resolved_url TEXT,
    rel_flags INTEGER NOT NULL,
    anchor_text TEXT,
    discovery_method TEXT NOT NULL,
    representation_id TEXT NOT NULL DEFAULT '',
    rel TEXT,
    element TEXT,
    dom_path TEXT,
    PRIMARY KEY(run_id, source_key, representation_id, ordinal)
) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS redirects (
    run_id TEXT NOT NULL REFERENCES runs(id),
    from_url TEXT NOT NULL,
    to_url TEXT,
    status_code INTEGER NOT NULL,
    location_raw TEXT NOT NULL,
    PRIMARY KEY(run_id, from_url, to_url)
) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS resources (
    run_id TEXT NOT NULL REFERENCES runs(id),
    page_key TEXT NOT NULL,
    resource_url TEXT NOT NULL,
    resource_type TEXT NOT NULL,
    status_code INTEGER,
    PRIMARY KEY(run_id, page_key, resource_url)
) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS resource_occurrences (
    run_id TEXT NOT NULL REFERENCES runs(id),
    page_key TEXT NOT NULL,
    ordinal INTEGER NOT NULL,
    resource_url TEXT NOT NULL,
    resource_type TEXT NOT NULL,
    status_code INTEGER,
    resolved_url TEXT,
    representation_id TEXT NOT NULL DEFAULT '',
    element TEXT,
    dom_path TEXT,
    PRIMARY KEY(run_id, page_key, representation_id, ordinal)
) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS evidence (
    run_id TEXT NOT NULL REFERENCES runs(id),
    item_id TEXT NOT NULL,
    payload TEXT NOT NULL,
    PRIMARY KEY(run_id, item_id)
) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS findings (
    run_id TEXT NOT NULL REFERENCES runs(id),
    item_id TEXT NOT NULL,
    payload TEXT NOT NULL,
    PRIMARY KEY(run_id, item_id)
) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS coverage (
    run_id TEXT PRIMARY KEY REFERENCES runs(id),
    item_id TEXT NOT NULL,
    payload TEXT NOT NULL
) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS version_manifests (
    run_id TEXT PRIMARY KEY REFERENCES runs(id),
    item_id TEXT NOT NULL,
    payload TEXT NOT NULL
) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS metrics (
    run_id TEXT NOT NULL REFERENCES runs(id),
    url_key TEXT,
    provider TEXT NOT NULL,
    name TEXT NOT NULL,
    value TEXT,
    unit TEXT,
    source TEXT NOT NULL,
    version TEXT NOT NULL,
    observed_at TEXT NOT NULL,
    kind TEXT NOT NULL,
    PRIMARY KEY(run_id, url_key, provider, name)
) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS idx_metrics_run_name ON metrics(run_id, name);
CREATE INDEX IF NOT EXISTS idx_pages_run_status ON pages(run_id, status_code);
CREATE INDEX IF NOT EXISTS idx_fetches_run ON fetches(run_id);
"""

_MIGRATION_2 = """
CREATE TABLE IF NOT EXISTS run_urls (
    run_id TEXT NOT NULL REFERENCES runs(id),
    url_key TEXT NOT NULL,
    state TEXT NOT NULL,
    depth INTEGER NOT NULL,
    attempts INTEGER NOT NULL,
    error_kind TEXT,
    PRIMARY KEY(run_id, url_key)
) STRICT;
CREATE INDEX IF NOT EXISTS idx_run_urls_run_state ON run_urls(run_id, state);
"""

_MIGRATION_3 = """
CREATE TABLE IF NOT EXISTS link_occurrences (
    run_id TEXT NOT NULL REFERENCES runs(id),
    source_key TEXT NOT NULL,
    ordinal INTEGER NOT NULL,
    raw_href TEXT NOT NULL,
    target_key TEXT,
    resolved_url TEXT,
    rel_flags INTEGER NOT NULL,
    anchor_text TEXT,
    discovery_method TEXT NOT NULL,
    representation_id TEXT NOT NULL DEFAULT '',
    rel TEXT,
    element TEXT,
    dom_path TEXT,
    PRIMARY KEY(run_id, source_key, representation_id, ordinal)
) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS resource_occurrences (
    run_id TEXT NOT NULL REFERENCES runs(id),
    page_key TEXT NOT NULL,
    ordinal INTEGER NOT NULL,
    resource_url TEXT NOT NULL,
    resource_type TEXT NOT NULL,
    status_code INTEGER,
    resolved_url TEXT,
    representation_id TEXT NOT NULL DEFAULT '',
    element TEXT,
    dom_path TEXT,
    PRIMARY KEY(run_id, page_key, representation_id, ordinal)
) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS metrics (
    run_id TEXT NOT NULL REFERENCES runs(id),
    url_key TEXT,
    provider TEXT NOT NULL,
    name TEXT NOT NULL,
    value TEXT,
    unit TEXT,
    source TEXT NOT NULL,
    version TEXT NOT NULL,
    observed_at TEXT NOT NULL,
    kind TEXT NOT NULL,
    PRIMARY KEY(run_id, url_key, provider, name)
) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS idx_metrics_run_name ON metrics(run_id, name);
"""

_MIGRATION_4 = """
CREATE TABLE IF NOT EXISTS metrics (
    run_id TEXT NOT NULL REFERENCES runs(id),
    url_key TEXT,
    provider TEXT NOT NULL,
    name TEXT NOT NULL,
    value TEXT,
    unit TEXT,
    source TEXT NOT NULL,
    version TEXT NOT NULL,
    observed_at TEXT NOT NULL,
    kind TEXT NOT NULL,
    PRIMARY KEY(run_id, url_key, provider, name)
) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS idx_metrics_run_name ON metrics(run_id, name);
"""
