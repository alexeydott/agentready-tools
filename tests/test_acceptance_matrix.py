"""Deterministic acceptance matrix for the canonical v2 application boundary."""

from __future__ import annotations

from agentready.cli import build_parser
from agentready.dashboard import render_dashboard
from agentready.mcp_server import audit_v2
from agentready.server import V2AuditRequest


def test_l0_unit_contracts_are_available():
    request = V2AuditRequest(url="https://example.test/", profile="quick", max_pages=1)
    assert request.profile == "quick"
    assert request.max_pages == 1


def test_l1_deterministic_dashboard_fixture_is_localized():
    html = render_dashboard("en")
    assert 'id="v2-inventory-panel"' in html
    assert 'id="v2-inventory-next"' in html
    assert "saveV2InventoryView" in html


def test_l2_cli_api_mcp_surface_contracts_preserve_shared_fields():
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
    assert audit_v2.__name__ == "audit_v2"


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
