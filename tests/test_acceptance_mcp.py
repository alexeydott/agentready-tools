"""Acceptance checks that require the explicit MCP dependency profile."""

from __future__ import annotations

import pytest

from agentready.cli import build_parser
from agentready.server import V2AuditRequest


def test_l2_cli_api_mcp_surface_contracts_preserve_shared_fields():
    pytest.importorskip("mcp")
    from agentready.mcp_server import audit_v2

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
