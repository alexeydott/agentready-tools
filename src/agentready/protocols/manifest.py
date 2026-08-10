"""Pinned protocol/profile metadata used by version-aware auditors."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ProtocolProfile:
    id: str
    version: str
    title: str
    source_id: str
    requirements: tuple[str, ...]
    deprecated: bool = False
    experimental: bool = False
    compatibility_of: str | None = None


PROTOCOL_MANIFEST: tuple[ProtocolProfile, ...] = (
    ProtocolProfile("api-catalog", "1.0", "API Catalog", "api-catalog", ("catalog",)),
    ProtocolProfile("openapi", "3.0", "OpenAPI", "openapi", ("openapi", "info", "paths")),
    ProtocolProfile("openapi", "3.1", "OpenAPI", "openapi", ("openapi", "info", "paths")),
    ProtocolProfile("openapi", "3.2", "OpenAPI", "openapi", ("openapi", "info", "paths")),
    ProtocolProfile("oauth-protected-resource", "RFC9728", "OAuth Protected Resource", "rfc-9728", ("resource",)),
    ProtocolProfile("problem-details", "RFC9457", "HTTP Problem Details", "rfc-9457", ("type", "title")),
    ProtocolProfile("mcp", "2026-07-28", "Model Context Protocol", "mcp-spec", ("protocolVersion",)),
    ProtocolProfile("a2a", "1.0.0", "Agent2Agent", "a2a-spec", ("name", "url")),
    ProtocolProfile(
        "a2a",
        "0.3",
        "Agent2Agent",
        "a2a-tck",
        ("name", "url"),
        deprecated=True,
        compatibility_of="a2a:1.0.0",
    ),
    ProtocolProfile("agent-skills", "1.0", "Agent Skills", "agentskills-spec", ("name", "description")),
    ProtocolProfile("webmcp", "experimental", "WebMCP", "webmcp-spec", ("tools",), experimental=True),
    ProtocolProfile("x402", "1.0", "x402", "commerce-x402", ("payment",)),
    ProtocolProfile("mpp", "1.0", "Machine Payments Protocol", "commerce-mpp", ("payment",)),
    ProtocolProfile("ucp", "1.0", "Universal Commerce Protocol", "commerce-ucp", ("checkout",)),
    ProtocolProfile("acp", "1.0", "Agentic Commerce Protocol", "commerce-acp", ("capabilities",)),
)
