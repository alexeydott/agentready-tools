"""Adapters for exposing protocol findings without changing v1 report shapes."""

from __future__ import annotations

from typing import Any

from .models import ProtocolFinding


def to_agent_findings(findings: tuple[ProtocolFinding, ...]) -> dict[str, Any]:
    """Project versioned findings into a stable agent/MCP-friendly payload."""
    return {
        "schema": "agentready.protocol-findings.v1",
        "findings": [finding.to_dict() for finding in findings],
        "findings_count": len(findings),
    }
