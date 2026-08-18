from agentready.audit_core.store import ContentRetention, MemorySiteStore, ProjectRecord, RunRecord, SQLiteSiteStore
from agentready.projects import ProjectService


def test_project_service_enforces_origin_and_retains_runs_on_metadata_delete():
    store = MemorySiteStore()
    service = ProjectService(store)
    service.create(ProjectRecord("p1", "Example", "https://example.test/"))
    assert service.update("p1", name="Renamed").name == "Renamed"
    store.begin_run(RunRecord("run-1", "config-hash", "tool", "rules"))
    service.attach_run("p1", "run-1", target="https://example.test/page", trigger="manual")
    try:
        service.attach_run("p1", "run-2", target="https://other.test/page")
    except ValueError as exc:
        assert "origin" in str(exc)
    else:
        raise AssertionError("cross-origin run was accepted")
    assert service.history("p1")[0].run_id == "run-1"
    service.delete_metadata("p1")
    assert list(store.iter_project_runs("p1")) == []
    assert store.resume_run("run-1").id == "run-1"


def test_projects_round_trip_through_sqlite_and_forward_migration(tmp_path):
    path = tmp_path / "projects.sqlite"
    store = SQLiteSiteStore(path, retention=ContentRetention.METADATA_ONLY)
    store.put_project(ProjectRecord("p1", "Example", "https://example.test/", default_ruleset="rules.yml"))
    store.begin_run(RunRecord("run-1", "config-hash", "tool", "rules"))
    service = ProjectService(store)
    relation = service.attach_run("p1", "run-1", target="https://example.test/", parent_run_id="parent", baseline_run_id="baseline")
    store.close()
    reopened = SQLiteSiteStore(path)
    try:
        assert reopened.get_project("p1").default_ruleset == "rules.yml"
        assert list(reopened.iter_project_runs("p1"))[0].parent_run_id == "parent"
        assert reopened._connection.execute("PRAGMA user_version").fetchone()[0] == 7
    finally:
        reopened.close()
