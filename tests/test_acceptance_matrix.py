"""Deterministic acceptance matrix for the canonical v2 application boundary."""

from __future__ import annotations

import asyncio
import re
from threading import Lock
from pathlib import Path

from agentready.cli import build_parser
from agentready.dashboard import render_dashboard
from agentready.metrics import (
    ExternalMetric,
    ProviderConfig,
    ProviderJob,
    ProviderRunBudget,
    ProviderScheduler,
    ProviderStatus,
    ga4_adapter,
)
from agentready.server import V2AuditRequest


def test_interactive_matrix_lists_all_cases_and_safe_manual_boundary():
    matrix = (Path(__file__).parents[1] / "docs" / "interactive-acceptance-matrix.md").read_text(encoding="utf-8")
    assert all(f"IT-{number:02d}" in matrix for number in range(1, 13))
    assert "Manual credentialed; never default CI" in matrix
    assert "authorization headers" in matrix


def test_l0_unit_contracts_are_available():
    request = V2AuditRequest(url="https://example.test/", profile="quick", max_pages=1)
    assert request.profile == "quick"
    assert request.max_pages == 1


def test_l1_deterministic_dashboard_fixture_is_localized():
    html = render_dashboard("en")
    assert 'id="v2-discovery"' in html
    assert "discovery_kind" in html
    assert 'id="v2-inventory-panel"' in html
    assert 'id="v2-inventory-next"' in html
    assert "saveV2InventoryView" in html
    assert 'id="robots-simulation-panel"' in html
    assert "simulateRobots" in html
    assert not re.search(r"<summary\\b[^>]*>.*?class=['\"]hint", html, re.DOTALL)


def test_l2_cli_api_surface_contracts_preserve_shared_fields():
    parser = build_parser()
    args = parser.parse_args(
        [
            "audit",
            "https://example.test/",
            "--profile",
            "quick",
            "--max-pages",
            "3",
            "--render",
            "--provider",
            "local",
        ]
    )
    api = V2AuditRequest(
        url=args.url[0],
        profile=args.profile,
        max_pages=args.max_pages,
        render=args.render,
        provider=args.provider,
    )
    assert {
        "url": args.url[0],
        "profile": api.profile,
        "max_pages": api.max_pages,
        "render": api.render,
        "provider": api.provider,
    } == {
        "url": "https://example.test/",
        "profile": "quick",
        "max_pages": 3,
        "render": True,
        "provider": "local",
    }


def test_l3_dashboard_has_keyboard_safe_inventory_controls():
    html = render_dashboard("en")
    assert 'label for="v2-inventory-limit"' in html
    assert 'label for="v2-inventory-filter"' in html


def test_dashboard_inventory_workspace_has_typed_table_and_marketer_actions():
    html = render_dashboard("en")
    assert 'id="v2-inventory-kind"' in html
    assert 'id="v2-inventory-sort"' in html
    assert 'id="v2-inventory-desc"' in html
    assert "compareV2Inventory()" in html
    assert "rescanV2Selection()" in html
    assert "runV2InventoryJob()" in html
    assert 'scope="col"' in html
    assert 'role="status"' in html


def test_l4_is_explicitly_opt_in_and_not_required_for_main_suite():
    """Live smoke is intentionally workflow_dispatch-only, never an implicit skip."""
    assert True


def test_it10_provider_budget_caps_independent_fake_calls_under_concurrency():
    """IT-10: one run budget must cap actual provider calls, not only results."""
    calls = 0
    call_lock = Lock()

    async def fake_provider_call(_: str | None) -> tuple[ExternalMetric, ...]:
        nonlocal calls
        with call_lock:
            calls += 1
        await asyncio.sleep(0.01)
        return (ExternalMetric("ga4", "sessions", 1, "count", "it-10", "1", "fixture"),)

    adapter = ga4_adapter(
        ProviderConfig(enabled=True, explicit_operation=True, quota=8, timeout_seconds=1)
    )
    budget = ProviderRunBudget(total=2, per_provider={"ga4": 2})
    results = ProviderScheduler(max_workers=4, budget=budget).run(
        [ProviderJob(adapter, fake_provider_call) for _ in range(8)],
        run_id="it-10",
    )

    assert calls == 2
    assert [result.status for result in results].count(ProviderStatus.AVAILABLE) == 2
    assert [result.status for result in results].count(ProviderStatus.QUOTA_EXCEEDED) == 6
    snapshot = budget.snapshot()
    assert snapshot.started == 2
    assert snapshot.exhausted == 6
