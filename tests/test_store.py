import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from agentready.audit_core.store import (
    ContentRetention,
    FetchFact,
    FindingStorageQuery,
    MemorySiteStore,
    MetricRecord,
    PageRecord,
    PageStorageQuery,
    RedirectFact,
    RepresentationRecord,
    RunFactRecord,
    RunRecord,
    RunUrlRecord,
    RunUrlState,
    RunUrlStorageQuery,
    SQLiteSiteStore,
    StoreError,
)
from agentready.audit_core.urls import UrlIdentity


def _populate(store: MemorySiteStore | SQLiteSiteStore) -> None:
    store.begin_run(RunRecord("run-1", "config", "tool", "rules"))
    store.put_run_url(RunUrlRecord("run-1", "https://example.com/a", RunUrlState.PARSED, depth=1, attempts=1))
    store.put_page(PageRecord("run-1", "https://example.com/a", "https://example.com/a", status_code=200, content="secret body"))
    store.put_page(PageRecord("run-1", "https://example.com/b", "https://example.com/b", status_code=404, content="not found"))
    store.put_fetch(FetchFact("fetch-1", "run-1", "https://example.com/a", status_code=200))
    store.put_representation(
        RepresentationRecord(
            "run-1",
            "https://example.com/a",
            "static-html:abc",
            "static-html",
            "text/html",
            "abc",
            11,
            "2026-01-01T00:00:00+00:00",
            "stdlib-htmlparser",
            body=b"secret body",
        )
    )
    store.put_url(UrlIdentity.parse("https://example.com/a"))
    store.put_resource("run-1", "https://example.com/a", "https://cdn.example.com/app.js", "script", status_code=200)
    store.put_evidence("run-1", "evidence-1", {"Authorization": "secret", "status": "pass"})
    store.put_finding("run-1", "finding-1", {"api_key": "secret", "message": "safe"})


def _semantic(store: MemorySiteStore | SQLiteSiteStore) -> list[tuple[str, int | None, str | None]]:
    return [(page.url_key, page.status_code, page.content) for page in store.iter_pages("run-1")]


def test_memory_store_is_idempotent_and_metadata_only_by_default():
    store = MemorySiteStore()
    _populate(store)
    store.begin_run(RunRecord("run-1", "different", "different", "different"))
    store.put_page(PageRecord("run-1", "https://example.com/a", "https://example.com/a", status_code=200, content="updated"))
    assert _semantic(store) == [
        ("https://example.com/a", 200, None),
        ("https://example.com/b", 404, None),
    ]
    assert store.recover_interrupted_runs() == 1
    assert store.resume_run("run-1").state == "running"
    assert next(store.iter_representations("run-1")).body is None


@pytest.mark.parametrize("store_kind", ["memory", "sqlite"])
def test_run_identity_and_version_manifest_round_trip(tmp_path: Path, store_kind: str):
    store = MemorySiteStore() if store_kind == "memory" else SQLiteSiteStore(tmp_path / "identity.sqlite")
    try:
        run = RunRecord(
            "run-identity",
            "config",
            "tool",
            "catalog-v2",
            rule_catalog_digest="digest-123",
            rule_catalog_digest_kind="content",
            score_model_id="score-v1",
            fact_schema_versions=(("page", "2"), ("transport", "1")),
        )
        store.begin_run(run)
        store.put_version_manifest(
            "run-identity",
            {
                "rule_catalog_digest": run.rule_catalog_digest,
                "rule_catalog_digest_kind": run.rule_catalog_digest_kind,
                "score_model_id": run.score_model_id,
                "fact_schema_versions": dict(run.fact_schema_versions),
            },
        )

        restored = store.get_run("run-identity")
        assert restored.rule_catalog_digest == "digest-123"
        assert restored.rule_catalog_digest_kind == "content"
        assert restored.score_model_id == "score-v1"
        assert restored.fact_schema_versions == (("page", "2"), ("transport", "1"))
        assert store.get_version_manifest("run-identity") == {
            "rule_catalog_digest": "digest-123",
            "rule_catalog_digest_kind": "content",
            "score_model_id": "score-v1",
            "fact_schema_versions": {"page": "2", "transport": "1"},
        }
    finally:
        store.close()


@pytest.mark.parametrize("store_kind", ["memory", "sqlite"])
def test_storage_queries_are_bounded_and_cursor_bound(tmp_path: Path, store_kind: str):
    store = MemorySiteStore() if store_kind == "memory" else SQLiteSiteStore(tmp_path / "query.sqlite")
    try:
        _populate(store)
        store.put_finding("run-1", "finding-2", {"status": "fail"})
        first = store.query_pages_storage(PageStorageQuery("run-1", limit=1))
        assert len(first.items) == 1 and first.next_cursor
        second = store.query_pages_storage(PageStorageQuery("run-1", limit=1, cursor=first.next_cursor))
        assert second.items[0].url_key != first.items[0].url_key
        findings = store.query_findings_storage(FindingStorageQuery("run-1", status="fail"))
        assert [row.finding_id for row in findings.items] == ["finding-2"]
        urls = store.query_run_urls_storage(RunUrlStorageQuery("run-1", limit=1))
        assert urls.items[0].url_key.endswith("/a")
        with pytest.raises(StoreError):
            store.query_pages_storage(PageStorageQuery("other", limit=1, cursor=first.next_cursor))
        with pytest.raises(ValueError):
            PageStorageQuery("run-1", sort_key="status")
        with pytest.raises(ValueError):
            FindingStorageQuery("run-1", descending=True)
    finally:
        store.close()


@pytest.mark.parametrize("store_kind", ["memory", "sqlite"])
def test_fetch_and_representation_records_round_trip_with_retention(tmp_path: Path, store_kind: str):
    store = (
        MemorySiteStore(retention=ContentRetention.FULL_CONTENT)
        if store_kind == "memory"
        else SQLiteSiteStore(tmp_path / "representations.sqlite", retention=ContentRetention.FULL_CONTENT)
    )
    try:
        store.begin_run(RunRecord("run-representations", "config", "tool", "rules"))
        store.put_fetch(
            FetchFact(
                "fetch-ok",
                "run-representations",
                "https://example.test/",
                final_url="https://example.test/final",
                status_code=200,
                total_ms=12,
                decoded_bytes=32,
                body_hash="hash",
            )
        )
        store.put_representation(
            RepresentationRecord(
                "run-representations",
                "https://example.test/",
                "static-html:hash",
                "static-html",
                "text/html",
                "hash",
                32,
                "2026-01-01T00:00:00+00:00",
                "stdlib-htmlparser",
                body=b"<title>Stored</title>",
                facts={"titles": ["Stored"], "links": []},
            )
        )

        assert next(store.iter_fetches("run-representations")).final_url == "https://example.test/final"
        restored = next(store.iter_representations("run-representations", "https://example.test/"))
        assert restored.source == "static-html"
        assert restored.body == b"<title>Stored</title>"
        assert restored.facts == {"titles": ["Stored"], "links": []}
    finally:
        store.close()


@pytest.mark.parametrize("store_kind", ["memory", "sqlite"])
def test_run_facts_round_trip_as_versioned_run_scope_records(tmp_path: Path, store_kind: str):
    store = MemorySiteStore() if store_kind == "memory" else SQLiteSiteStore(tmp_path / "run-facts.sqlite")
    try:
        store.begin_run(RunRecord("run-facts", "config", "tool", "rules"))
        store.put_run_fact(
            RunFactRecord(
                "run-facts",
                "robots.fetch",
                "1",
                "origin",
                "https://example.test",
                {"state": "available", "Authorization": "secret"},
                "2026-01-01T00:00:00+00:00",
            )
        )

        facts = tuple(store.iter_run_facts("run-facts", "robots.fetch"))
        assert len(facts) == 1
        assert facts[0].schema_version == "1"
        assert facts[0].payload["state"] == "available"
        assert facts[0].payload["Authorization"] == "[REDACTED]"
    finally:
        store.close()


@pytest.mark.parametrize("store_kind", ["memory", "sqlite"])
def test_storage_query_pages_match_backend_sequences(tmp_path: Path, store_kind: str):
    store = MemorySiteStore() if store_kind == "memory" else SQLiteSiteStore(tmp_path / "sequence.sqlite")
    try:
        _populate(store)
        store.put_page(PageRecord("run-1", "https://example.com/c", "https://example.com/c", status_code=200, locally_indexable=False))
        pages: list[str] = []
        cursor = None
        while True:
            result = store.query_pages_storage(PageStorageQuery("run-1", limit=1, cursor=cursor))
            pages.extend(page.url_key for page in result.items)
            if not result.next_cursor:
                break
            cursor = result.next_cursor
        assert pages == ["https://example.com/a", "https://example.com/b", "https://example.com/c"]
        assert store.query_pages_storage(PageStorageQuery("run-1", status_code=204)).items == ()
    finally:
        store.close()


def test_memory_and_sqlite_storage_cursors_match_after_deletion(tmp_path: Path):
    memory = MemorySiteStore()
    sqlite = SQLiteSiteStore(tmp_path / "cursor-parity.sqlite")
    try:
        _populate(memory)
        _populate(sqlite)
        del memory._pages[("run-1", "https://example.com/b")]
        sqlite._connection.execute("DELETE FROM pages WHERE run_id=? AND url_key=?", ("run-1", "https://example.com/b"))
        sqlite._connection.commit()
        def collect(store):
            cursor = None
            rows = []
            cursors = []
            while True:
                page = store.query_pages_storage(PageStorageQuery("run-1", limit=1, cursor=cursor))
                rows.extend(item.url_key for item in page.items)
                if not page.next_cursor:
                    break
                cursors.append(page.next_cursor)
                cursor = page.next_cursor
            return rows, cursors
        assert collect(memory) == collect(sqlite)
    finally:
        memory.close()
        sqlite.close()


def test_sqlite_storage_query_uses_keyset_index(tmp_path: Path):
    store = SQLiteSiteStore(tmp_path / "plan.sqlite")
    try:
        _populate(store)
        plan = store._connection.execute(
            "EXPLAIN QUERY PLAN SELECT * FROM pages WHERE run_id=? ORDER BY url_key LIMIT ?",
            ("run-1", 2),
        ).fetchall()
        assert any("idx_pages_run_url" in str(tuple(row)).lower() or "sqlite_autoindex_pages" in str(tuple(row)).lower() for row in plan)
    finally:
        store.close()


def test_sqlite_matches_memory_and_retains_bounded_samples(tmp_path: Path):
    memory = MemorySiteStore(retention=ContentRetention.SAMPLES)
    sqlite = SQLiteSiteStore(tmp_path / "project.sqlite", retention=ContentRetention.SAMPLES)
    try:
        _populate(memory)
        _populate(sqlite)
        assert _semantic(sqlite) == _semantic(memory)
        assert list(sqlite.iter_run_urls("run-1")) == list(memory.iter_run_urls("run-1"))
        sqlite.put_redirect(RedirectFact("run-1", "https://example.com/a", "https://example.com/b", 301, "/b"))
        sqlite.put_page(PageRecord("run-1", "https://example.com/long", "https://example.com/long", content="x" * 5000))
        assert len(sqlite.query_pages("run-1")[-1].content or "") == 4096
        assert sqlite.query_pages("run-1", status_code=404)[0].url_key.endswith("/b")
    finally:
        sqlite.close()


def test_sqlite_wal_foreign_keys_and_rollback(tmp_path: Path):
    path = tmp_path / "project.sqlite"
    store = SQLiteSiteStore(path)
    try:
        journal_mode = store._connection.execute("PRAGMA journal_mode").fetchone()[0]
        assert journal_mode.lower() == "wal"
        with pytest.raises(sqlite3.IntegrityError):
            store.put_page(PageRecord("missing-run", "key", "https://example.com"))
        assert store.query_pages("missing-run") == []
        assert store._connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert list(store.iter_run_urls("run-1")) == []
    finally:
        store.close()


def test_newer_schema_requires_read_only_mode(tmp_path: Path):
    path = tmp_path / "newer.sqlite"
    initial = SQLiteSiteStore(path)
    initial.close()
    connection = sqlite3.connect(path)
    connection.execute("PRAGMA user_version=99")
    connection.commit()
    connection.close()
    with pytest.raises(StoreError, match="newer"):
        SQLiteSiteStore(path)
    store = SQLiteSiteStore(path, read_only=True)
    try:
        assert store.query_pages("run-1") == []
        with pytest.raises(StoreError, match="read-only"):
            store.begin_run(RunRecord("run-1", "config", "tool", "rules"))
    finally:
        store.close()


def test_reopening_sqlite_marks_running_runs_interrupted_and_resumes(tmp_path: Path):
    path = tmp_path / "resume.sqlite"
    first = SQLiteSiteStore(path)
    first.begin_run(RunRecord("run-1", "config", "tool", "rules"))
    first.close()
    second = SQLiteSiteStore(path)
    try:
        assert second.resume_run("run-1").state == "running"
        assert second.begin_run(RunRecord("run-1", "other", "other", "other")).config_hash == "config"
        second.put_run_url(RunUrlRecord("run-1", "https://example.com/a", RunUrlState.FETCHED))
        assert next(iter(second.iter_run_urls("run-1"))).state is RunUrlState.FETCHED
    finally:
        second.close()


def test_sqlite_serializes_writes_while_reading(tmp_path: Path):
    store = SQLiteSiteStore(tmp_path / "concurrent.sqlite")
    try:
        store.begin_run(RunRecord("run-1", "config", "tool", "rules"))

        def write_page(index: int) -> None:
            store.put_page(PageRecord("run-1", f"url-{index}", f"https://example.com/{index}"))

        with ThreadPoolExecutor(max_workers=4) as executor:
            list(executor.map(write_page, range(20)))
            assert len(list(store.iter_pages("run-1"))) == 20
        assert store._connection.execute("EXPLAIN QUERY PLAN SELECT * FROM pages WHERE run_id='run-1' AND status_code=200").fetchone()
    finally:
        store.close()


@pytest.mark.parametrize("store_kind", ["memory", "sqlite"])
def test_link_and_resource_occurrences_preserve_duplicate_occurrences(tmp_path: Path, store_kind: str):
    store = MemorySiteStore() if store_kind == "memory" else SQLiteSiteStore(tmp_path / "occurrences.sqlite")
    try:
        store.begin_run(RunRecord("run-occurrences", "config", "tool", "rules"))
        store.put_link(
            "run-occurrences",
            "https://example.com/",
            "/target",
            ordinal=0,
            representation_id="rep-1",
            anchor_text="one",
        )
        store.put_link(
            "run-occurrences",
            "https://example.com/",
            "/target",
            ordinal=1,
            representation_id="rep-1",
            anchor_text="two",
        )
        store.put_resource(
            "run-occurrences",
            "https://example.com/",
            "/asset.js",
            "script",
            ordinal=0,
            representation_id="rep-1",
        )
        store.put_resource(
            "run-occurrences",
            "https://example.com/",
            "/asset.js",
            "script",
            ordinal=1,
            representation_id="rep-1",
        )
        assert [item.anchor_text for item in store.iter_link_occurrences("run-occurrences")] == ["one", "two"]
        assert [item.ordinal for item in store.iter_resource_occurrences("run-occurrences")] == [0, 1]
    finally:
        store.close()


def test_sqlite_v2_migrates_occurrence_tables(tmp_path: Path):
    path = tmp_path / "v2.sqlite"
    initial = SQLiteSiteStore(path)
    initial.close()
    connection = sqlite3.connect(path)
    connection.execute("DROP TABLE link_occurrences")
    connection.execute("DROP TABLE resource_occurrences")
    connection.execute("PRAGMA user_version=2")
    connection.commit()
    connection.close()

    store = SQLiteSiteStore(path)
    try:
        store.begin_run(RunRecord("run-migration", "config", "tool", "rules"))
        store.put_link("run-migration", "page", "/target", representation_id="rep", ordinal=0)
        assert len(list(store.iter_link_occurrences("run-migration"))) == 1
        store.put_metric(MetricRecord("run-migration", "page", "fixture", "lcp", 100, "ms", "test", "1", "now"))
        assert len(list(store.iter_metrics("run-migration"))) == 1
    finally:
        store.close()


def test_sqlite_migration_is_idempotent_and_recovery_is_durable(tmp_path: Path):
    path = tmp_path / "idempotent.sqlite"
    first = SQLiteSiteStore(path)
    first.begin_run(RunRecord("run-recovery", "config", "tool", "rules"))
    first.close()
    second = SQLiteSiteStore(path)
    try:
        assert second.recover_interrupted_runs() == 0
        assert second._connection.execute("PRAGMA user_version").fetchone()[0] == 13
        assert second._connection.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0] == 1
        assert second.resume_run("run-recovery").state == "running"
    finally:
        second.close()


def test_sqlite_v8_run_identity_migration_is_durable(tmp_path: Path):
    path = tmp_path / "v8-identity.sqlite"
    store = SQLiteSiteStore(path)
    store.begin_run(RunRecord("run-v8", "config", "tool", "rules-v8"))
    store.close()
    connection = sqlite3.connect(path)
    connection.execute("ALTER TABLE runs DROP COLUMN rule_catalog_digest")
    connection.execute("ALTER TABLE runs DROP COLUMN score_model_id")
    connection.execute("ALTER TABLE runs DROP COLUMN fact_schema_versions")
    connection.execute("PRAGMA user_version=8")
    connection.commit()
    connection.close()

    reopened = SQLiteSiteStore(path)
    try:
        restored = reopened.get_run("run-v8")
        assert restored.rule_catalog_digest
        assert restored.rule_catalog_digest_kind == "synthetic"
        assert restored.score_model_id == "readiness-transparent-v2"
        assert restored.fact_schema_versions == ()
        assert reopened._connection.execute("PRAGMA user_version").fetchone()[0] == 13
    finally:
        reopened.close()


def test_sqlite_reclaims_stale_pending_evidence(tmp_path: Path):
    path = tmp_path / "stale-evidence.sqlite"
    store = SQLiteSiteStore(path)
    store.begin_run(RunRecord("run-stale", "config", "tool", "rules"))
    evidence_id = "provider:ga4:https://example.com/"
    assert store.claim_evidence("run-stale", evidence_id)
    store.put_evidence("run-stale", evidence_id, {"status": "pending"})
    store._connection.execute("UPDATE evidence_claims SET claimed_at=datetime('now', '-2 hours')")
    store._connection.commit()
    store.close()

    reopened = SQLiteSiteStore(path)
    try:
        assert reopened.claim_evidence("run-stale", evidence_id)
        assert reopened.get_evidence("run-stale", evidence_id) is None
    finally:
        reopened.close()
