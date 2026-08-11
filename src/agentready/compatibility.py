"""Release-frozen compatibility and migration manifest."""

from __future__ import annotations

from dataclasses import dataclass

RELEASE_VERSION = "0.9.0"
RELEASE_CHANNEL = "stable"
V1_FACADES = (
    "scan",
    "seo audit",
    "mobile audit",
    "/scan",
    "/seo/audit",
    "/mobile/audit",
    "mcp.scan_site",
    "mcp.seo_audit",
    "mcp.mobile_audit",
)
V2_SCHEMAS = ("agentready.audit.v2", "agentready.findings.v1", "agentready.remediation-plan.v1")
V2_SURFACES = ("cli.audit", "/v2/audit", "/v2/audit/dashboard", "mcp.audit_v2")
PROTOCOL_MANIFEST_VERSION = "v1"


@dataclass(frozen=True, slots=True)
class CompatibilityManifest:
    release: str = RELEASE_VERSION
    channel: str = RELEASE_CHANNEL
    v1_facades: tuple[str, ...] = V1_FACADES
    v2_schemas: tuple[str, ...] = V2_SCHEMAS
    v2_surfaces: tuple[str, ...] = V2_SURFACES
    protocol_manifest: str = PROTOCOL_MANIFEST_VERSION
    migration_status: str = "v1-preserved-v2-additive"

    def to_dict(self) -> dict[str, object]:
        return {
            "release": self.release,
            "channel": self.channel,
            "v1_facades": list(self.v1_facades),
            "v2_schemas": list(self.v2_schemas),
            "v2_surfaces": list(self.v2_surfaces),
            "protocol_manifest": self.protocol_manifest,
            "migration_status": self.migration_status,
        }


COMPATIBILITY = CompatibilityManifest()
