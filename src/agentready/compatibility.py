"""Release-frozen v2 contract manifest."""

from __future__ import annotations

from dataclasses import dataclass

RELEASE_VERSION = "0.13.2"
RELEASE_CHANNEL = "stable"
V2_SCHEMAS = (
    "agentready.audit.v2",
    "agentready.seo.v2",
    "agentready.mobile.v2",
    "agentready.findings.v2",
    "agentready.remediation-plan.v2",
    "agentready.protocol-findings.v2",
    "agentready.robots-simulation.v2",
    "agentready.sitemap-reconciliation.v2",
    "agentready.custom-rules.v2",
    "agentready.ai-assistant.v2",
)
V2_SURFACES = (
    "cli.audit",
    "cli.ai",
    "cli.credentials",
    "cli.indexing",
    "cli.geo",
    "cli.logs",
    "cli.serve",
    "cli.mcp",
    "/v2/audit",
    "/v2/audit/dashboard",
    "/v2/capabilities",
    "/v2/rescan",
    "/v2/jobs",
    "/v2/jobs/{job_id}",
    "/v2/jobs/{job_id}/cancel",
    "/v2/runs/{run_id}/provider-enrichment",
    "/v2/runs/{run_id}/url-inspection",
    "/v2/runs/{run_id}/provider-jobs",
    "/v2/runs/{run_id}/robots/simulate",
    "/v2/runs/{run_id}/sitemap/reconcile",
    "/v2/runs/{run_id}/graph",
    "/v2/runs/{run_id}/graph/node",
    "/v2/runs/{run_id}/duplicates",
    "/v2/runs/{run_id}/duplicates/{cluster_id}",
    "/v2/projects",
    "/v2/projects/{project_id}",
    "/v2/projects/{project_id}/runs",
    "/v2/projects/{project_id}/baseline",
    "/v2/custom-rules/validate",
    "/v2/custom-rules/debug",
    "/v2/custom-rules/apply",
    "/v2/diff",
    "/v2/export",
    "/v2/saved-views",
    "/v2/saved-views/{view_id}",
    "/v2/saved-views/{view_id}/export",
    "/v2/runs/{run_id}/inventory/{kind}",
    "/v2/runs/{run_id}/pages",
    "/v2/runs/{run_id}/overview",
    "/v2/runs/{run_id}/run-urls",
    "/v2/runs/{run_id}/urls",
    "/v2/runs/{run_id}/links",
    "/v2/runs/{run_id}/resources",
    "/v2/runs/{run_id}/redirects",
    "/v2/runs/{run_id}/findings",
    "/v2/runs/{run_id}/metrics",
    "/v2/seo/audit",
    "/v2/seo/audit/dashboard",
    "/v2/mobile/audit",
    "/v2/mobile/audit/dashboard",
    "/ai/recommend",
    "/ai/chat",
    "/healthz",
    "/checks",
    "/seo/checks",
    "/mobile/checks",
    "/ai/status",
    "/ai/tools",
    "/ai/prompts",
    "/ai/chats",
    "/ai/chats/{filename}",
    "/ai/providers",
    "/ai/providers/active",
    "/ai/providers/{provider_id}/models",
    "/ai/providers/{provider_id}",
    "/ai/credentials",
    "mcp.audit_v2",
    "mcp.seo_audit_v2",
    "mcp.provider_enrichment_v2",
    "mcp.mobile_audit_v2",
    "mcp.audit_findings",
    "mcp.remediation_plan",
    "mcp.mobile_findings",
    "mcp.mobile_remediation_plan",
    "mcp.ai_recommend",
    "mcp.ai_chat",
)
PROTOCOL_MANIFEST_VERSION = "v2"


@dataclass(frozen=True, slots=True)
class CompatibilityManifest:
    release: str = RELEASE_VERSION
    channel: str = RELEASE_CHANNEL
    schemas: tuple[str, ...] = V2_SCHEMAS
    surfaces: tuple[str, ...] = V2_SURFACES
    protocol_manifest: str = PROTOCOL_MANIFEST_VERSION
    contract_status: str = "v2-only"

    def to_dict(self) -> dict[str, object]:
        return {
            "release": self.release,
            "channel": self.channel,
            "schemas": list(self.schemas),
            "surfaces": list(self.surfaces),
            "protocol_manifest": self.protocol_manifest,
            "contract_status": self.contract_status,
        }


COMPATIBILITY = CompatibilityManifest()
