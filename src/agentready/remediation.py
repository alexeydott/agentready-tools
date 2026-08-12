from __future__ import annotations

import logging

from .models import Remediation
from .registry import CheckSpec

logger = logging.getLogger(__name__)

_GUIDANCE: dict[str, str] = {
    "robots-txt": "Publish /robots.txt as plain text with at least one User-agent directive; include your intended crawler policy explicitly.",
    "sitemap": "Publish a valid XML sitemap at /sitemap.xml or advertise its absolute URL with a Sitemap: directive in robots.txt.",
    "link-headers": "Expose an RFC 8288 Link response header for agent/API discovery; rel=\"api-catalog\" is the interoperable API Catalog signal.",
    "dns-aid": "If DNS-AID is appropriate for your service, publish the draft SVCB/HTTPS discovery record under _index._agents.<domain>.",
    "markdown-negotiation": "When a client sends Accept: text/markdown, return a non-empty Markdown representation with Content-Type: text/markdown instead of HTML.",
    "ai-bot-rules": "Add explicit robots.txt User-agent groups for the AI crawlers or user-directed agents you intend to allow or block. The audit scores explicit policy, not the choice to allow or deny.",
    "content-signals": "Publish a syntactically valid Content-Signal policy in robots.txt and/or the HTTP Content-Signal header, for example search=yes, ai-input=yes, ai-train=no.",
    "web-bot-auth": "Publish /.well-known/http-message-signatures-directory as JSON containing at least one JWK-like public key entry.",
    "api-catalog": "Publish /.well-known/api-catalog as an RFC 9727 linkset describing the API descriptions that actually exist.",
    "oauth-discovery": "If the site has OAuth, publish RFC 8414 Authorization Server Metadata at /.well-known/oauth-authorization-server with the real issuer and endpoints.",
    "oauth-protected-resource": "If resources are OAuth-protected, publish RFC 9728 Protected Resource Metadata at /.well-known/oauth-protected-resource with the real resource identifier.",
    "auth-md": "If you use auth.md, serve /auth.md as Markdown and point agents to the authoritative OAuth Protected Resource Metadata. Do not use auth.md as a replacement for RFC 9728.",
    "mcp-server-card": "If an MCP server exists, publish /.well-known/mcp/server-card.json with serverInfo.name and transport metadata that points to the real server.",
    "a2a-agent-card": "If an A2A agent exists, publish /.well-known/agent-card.json with real identity, capabilities, interfaces/URL, modes, and skills.",
    "agent-skills": "Publish /.well-known/agent-skills/index.json using the Agent Skills discovery schema and real skill URLs/digests; do not advertise placeholder skills.",
    "webmcp": "If your web application intentionally exposes browser tools, register real WebMCP tools or publish a supported discovery document. Fetch-only detection cannot prove runtime registrations in external JavaScript.",
    "x402": "For a real paid resource, return HTTP 402 with a valid PAYMENT-REQUIRED challenge. This scanner never pays or retries with credentials.",
    "mpp": "For a real MPP-protected resource, return HTTP 402 with a WWW-Authenticate: Payment challenge. This scanner never submits payment credentials.",
    "ucp": "If the site is a UCP participant, publish the current UCP profile at /.well-known/ucp and keep it consistent with the actual commerce services.",
    "acp": "ACP public web discovery is still evolving. Only publish a discovery document that your deployed ACP implementation actually supports; this check is heuristic and informational.",
    "llms-txt": "Publish /llms.txt as a concise Markdown directory with a clear H1, high-value links and descriptive labels. For large documentation sites, split it into hierarchical per-section llms.txt files instead of one huge flat index.",
    "markdown-index-fallback": "Expose each important content page through an /index.md URL fallback (or equivalent stable Markdown URL) for agents that do not send Accept: text/markdown.",
    "markdown-efficiency": "Reduce navigation chrome, duplicated menus, scripts and conversion noise in the Markdown representation so it is materially smaller and easier for agents to consume than HTML.",
    "search-indexability": "Keep the selected public page HTTP 200 and indexable: remove accidental noindex directives and publish one authoritative canonical URL. Do not change canonical targets mechanically without understanding duplicate-content intent.",
    "ai-crawler-live-access": "Verify that OAI-SearchBot, Claude-SearchBot, PerplexityBot and normal search crawlers can reach the page through robots.txt, CDN/WAF and origin controls. Review Google-Extended separately as a robots.txt product policy token; it has no distinct HTTP User-Agent to probe. Treat spoofed User-Agent probes as diagnostics and confirm suspicious 403/429 responses in real server/WAF logs or official crawler traffic.",
    "structured-data-graph": "For article-like pages, publish valid Schema.org JSON-LD as a connected graph: Article/TechArticle with headline, datePublished, dateModified, mainEntityOfPage and author linked to a Person; add Person.sameAs and BreadcrumbList where appropriate. Validate the JSON after every change.",
    "faq-structured-data": "If the page contains genuine visible questions and answers, publish a valid FAQPage whose mainEntity contains Question nodes with acceptedAnswer Answer.text. Do not invent FAQ content solely for markup.",
    "date-transparency": "Expose honest datePublished/dateModified values in Article JSON-LD and visible page content. Keep datePublished stable and change dateModified only for meaningful content changes; use Git history as a verification reference, not as proof of editorial intent.",
    "citation-readiness": "Improve extractability without keyword stuffing: use concrete facts, numbers, limits, complete commands/code, useful comparison tables and self-contained answer-first paragraphs. Treat this audit as a heuristic, not a ranking factor, and review intent coverage manually.",
}


def remediation_for(spec: CheckSpec, target: str) -> Remediation:
    refs = [reference for reference in spec.references if "tochkicamp.ru/guides/kak-optimizirovat-sayt-pod-ai-poisk/" not in reference]
    removed_references = len(spec.references) - len(refs)
    if removed_references:
        logger.debug(
            "Removed development-only source references from report: check_id=%s count=%d",
            spec.id,
            removed_references,
        )
    summary = _GUIDANCE.get(spec.id, "Review the protocol specification and publish a real, valid discovery surface.")
    prompt = (
        f"Improve this website for AI-agent readiness by fixing the `{spec.id}` audit. "
        f"{summary} Preserve existing human-facing behavior and security controls. "
        f"After implementation, verify with: agentready audit --mode readiness {target!r} --include {spec.id}."
    )
    return Remediation(
        summary=summary,
        rerun_command=f"agentready audit --mode readiness {target!r} --include {spec.id}",
        references=refs,
        agent_prompt=prompt,
    )
