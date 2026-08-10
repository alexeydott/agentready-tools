import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from agentready.audit_core.store import (
    ContentRetention,
    FetchFact,
    MemorySiteStore,
    PageRecord,
    RedirectFact,
    RunRecord,
    SQLiteSiteStore,
    StoreError,
)
from agentready.audit_core.urls import UrlIdentity


def _populate(store: MemorySiteStore | SQLiteSiteStore) -> None:
    store.begin_run(RunRecord("run-1", "config", "tool", "rules"))
    store.put_page(PageRecord("run-1", "https://example.com/a", "https://example.com/a", status_code=200, content="secret body"))
    store.put_page(PageRecord("run-1", "https://example.com/b", "https://example.com/b", status_code=404, content="not found"))
    store.put_fetch(FetchFact("fetch-1", "run-1", "https://example.com/a", status_code=200))
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


def test_sqlite_matches_memory_and_retains_bounded_samples(tmp_path: Path):
    memory = MemorySiteStore(retention=ContentRetention.SAMPLES)
    sqlite = SQLiteSiteStore(tmp_path / "project.sqlite", retention=ContentRetention.SAMPLES)
    try:
        _populate(memory)
        _populate(sqlite)
        assert _semantic(sqlite) == _semantic(memory)
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
