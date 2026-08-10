"""Release-frozen compatibility and migration manifest."""

from __future__ import annotations

from dataclasses import dataclass

RELEASE_VERSION = "0.8.0"
RELEASE_CHANNEL = "release-candidate"
V1_FACADES = ("scan", "seo audit", "mobile audit", "/scan", "/seo/audit", "/mobile/audit")
V2_SCHEMAS = ("agentready.audit.v2", "agentready.findings.v1", "agentready.remediation-plan.v1")
PROTOCOL_MANIFEST_VERSION = "v1"


@dataclass(frozen=True, slots=True)
class CompatibilityManifest:
    release: str = RELEASE_VERSION
    channel: str = RELEASE_CHANNEL
    v1_facades: tuple[str, ...] = V1_FACADES
    v2_schemas: tuple[str, ...] = V2_SCHEMAS
    protocol_manifest: str = PROTOCOL_MANIFEST_VERSION
    migration_status: str = "v1-preserved-v2-additive"

    def to_dict(self) -> dict[str, object]:
        return {
            "release": self.release,
            "channel": self.channel,
            "v1_facades": list(self.v1_facades),
            "v2_schemas": list(self.v2_schemas),
            "protocol_manifest": self.protocol_manifest,
            "migration_status": self.migration_status,
        }


COMPATIBILITY = CompatibilityManifest()
