from agentready.audit_core import AuditRunContext, RunCoordinator, RunState


def test_run_context_hash_is_stable_and_run_identity_is_explicit():
    first = AuditRunContext.create(
        "https://example.test",
        {"max_pages": 2, "secret": "not logged"},
        tool_version="0.8.1",
        rule_catalog_version="rules-1",
        run_id="run-1",
    )
    second = AuditRunContext.create(
        "https://example.test",
        {"secret": "not logged", "max_pages": 2},
        tool_version="0.8.1",
        rule_catalog_version="rules-1",
        run_id="run-2",
    )
    assert first.config_hash == second.config_hash
    assert first.run_id == "run-1"
    assert first.target == "https://example.test"


def test_run_coordinator_preserves_immutable_terminal_snapshot():
    context = AuditRunContext.create(
        "https://example.test",
        {},
        tool_version="0.8.1",
        rule_catalog_version="rules-1",
        run_id="run-1",
    )
    coordinator = RunCoordinator(context)
    coordinator.transition(RunState.RUNNING)
    snapshot = coordinator.transition(RunState.PARTIAL, error_kind="deadline")
    assert snapshot.state is RunState.PARTIAL
    assert snapshot.error_kind == "deadline"
    assert coordinator.history == (RunState.CREATED, RunState.RUNNING, RunState.PARTIAL)


def test_interrupted_run_can_resume_with_same_immutable_context():
    context = AuditRunContext.create("https://example.test", {}, tool_version="1", rule_catalog_version="1")
    coordinator = RunCoordinator(context)
    coordinator.transition(RunState.RUNNING)
    interrupted = coordinator.transition(RunState.INTERRUPTED, error_kind="cancelled")
    resumed = RunCoordinator.resume(interrupted)
    assert resumed.context == context
    assert resumed.state is RunState.RUNNING
    assert resumed.history == (RunState.INTERRUPTED, RunState.RUNNING)
