from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Effort = Literal["low", "medium", "high"]


@dataclass(frozen=True, slots=True)
class CheckSpec:
    id: str
    title: str
    category: str
    scored: bool
    presets: frozenset[str]
    references: tuple[str, ...] = ()
    experimental: bool = False
    supplemental: bool = False
    effort: Effort = "medium"
    geo_scored: bool = False


CONTENT = frozenset({"all", "content"})
API = frozenset({"all", "api"})
BOTH = frozenset({"all", "content", "api"})
COMMERCE = frozenset({"all"})
AI_SEARCH = frozenset({"ai-search"})
OPTIONAL = frozenset()

GUIDE = "https://tochkicamp.ru/guides/kak-optimizirovat-sayt-pod-ai-poisk/"

CHECKS: tuple[CheckSpec, ...] = (
    CheckSpec("robots-txt", "robots.txt", "Discoverability", True, BOTH | AI_SEARCH, ("https://www.rfc-editor.org/rfc/rfc9309", GUIDE), effort="low", geo_scored=True),
    CheckSpec("sitemap", "Sitemap", "Discoverability", True, CONTENT | AI_SEARCH, ("https://www.sitemaps.org/protocol.html", GUIDE), effort="low", geo_scored=True),
    CheckSpec("link-headers", "Link headers", "Discoverability", True, BOTH, ("https://www.rfc-editor.org/rfc/rfc8288", "https://www.rfc-editor.org/rfc/rfc9727"), effort="low"),
    CheckSpec("dns-aid", "DNS for AI Discovery (DNS-AID)", "Discoverability", False, BOTH, ("https://datatracker.ietf.org/doc/draft-mozleywilliams-dnsop-dnsaid/",), True, effort="medium"),
    CheckSpec("markdown-negotiation", "Markdown negotiation", "Content Accessibility", True, BOTH | AI_SEARCH, ("https://developers.cloudflare.com/fundamentals/reference/markdown-for-agents/",), effort="medium", geo_scored=False),
    # Cloudflare notes Web Bot Auth is not applicable to every content-only site. We keep it informational
    # unless a future applicability probe can prove the site operates an outbound agent.
    CheckSpec("ai-bot-rules", "AI bot rules", "Bot Access Control", True, BOTH | AI_SEARCH, (GUIDE,), effort="low", geo_scored=True),
    CheckSpec("content-signals", "Content Signals", "Bot Access Control", True, BOTH | AI_SEARCH, ("https://contentsignals.org/", GUIDE), effort="low", geo_scored=False),
    CheckSpec("web-bot-auth", "Web Bot Auth", "Bot Access Control", False, BOTH, effort="medium"),
    CheckSpec("api-catalog", "API Catalog", "Protocol Discovery", True, API, ("https://www.rfc-editor.org/rfc/rfc9727",), effort="medium"),
    CheckSpec("oauth-discovery", "OAuth discovery", "Protocol Discovery", True, API, ("https://www.rfc-editor.org/rfc/rfc8414",), effort="medium"),
    CheckSpec("oauth-protected-resource", "OAuth Protected Resource", "Protocol Discovery", True, API, ("https://www.rfc-editor.org/rfc/rfc9728",), effort="medium"),
    CheckSpec("auth-md", "Auth.md", "Protocol Discovery", False, API, experimental=True, effort="low"),
    CheckSpec("mcp-server-card", "MCP Server Card", "Protocol Discovery", True, API, ("https://modelcontextprotocol.io/",), effort="medium"),
    CheckSpec("a2a-agent-card", "A2A Agent Card", "Protocol Discovery", True, API, ("https://a2a-protocol.org/",), effort="medium"),
    CheckSpec("agent-skills", "Agent Skills", "Protocol Discovery", True, API, ("https://agentskills.io/",), effort="medium"),
    CheckSpec("webmcp", "WebMCP", "Protocol Discovery", False, API, ("https://webmcp.org/",), True, effort="high"),
    CheckSpec("x402", "x402", "Commerce", False, COMMERCE, ("https://www.x402.org/",), effort="high"),
    CheckSpec("mpp", "MPP", "Commerce", False, COMMERCE, ("https://mpp.dev/",), effort="high"),
    CheckSpec("ucp", "UCP", "Commerce", False, COMMERCE, ("https://ucp.dev/",), effort="high"),
    CheckSpec("acp", "ACP", "Commerce", False, COMMERCE, ("https://agenticcommerce.dev/",), True, effort="high"),
    # Supplemental Cloudflare-docs-inspired audits. These are opt-in and never alter the core score.
    CheckSpec("llms-txt", "llms.txt", "Content Accessibility", False, OPTIONAL, ("https://llmstxt.org/", "https://blog.cloudflare.com/agent-readiness/", GUIDE), supplemental=True, effort="low"),
    CheckSpec("markdown-index-fallback", "Markdown /index.md fallback", "Content Accessibility", False, OPTIONAL, ("https://blog.cloudflare.com/agent-readiness/",), supplemental=True, effort="medium"),
    CheckSpec("markdown-efficiency", "Markdown efficiency", "Content Accessibility", False, OPTIONAL, ("https://blog.cloudflare.com/agent-readiness/",), supplemental=True, effort="medium"),
    # AI Search / GEO profile inspired by the Tochki guide. These are separate from the protocol score.
    CheckSpec(
        "search-indexability",
        "Search indexability & canonical",
        "AI Search / GEO",
        False,
        AI_SEARCH,
        (
            GUIDE,
            "https://developers.google.com/search/docs/crawling-indexing/block-indexing",
            "https://developers.google.com/search/docs/crawling-indexing/consolidate-duplicate-urls",
        ),
        supplemental=True,
        effort="low",
        geo_scored=True,
    ),
    CheckSpec(
        "ai-crawler-live-access",
        "Live AI crawler access",
        "AI Search / GEO",
        False,
        AI_SEARCH,
        (
            GUIDE,
            "https://developers.google.com/search/docs/crawling-indexing/google-common-crawlers#google-extended",
            "https://platform.openai.com/docs/bots",
            "https://docs.perplexity.ai/docs/resources/perplexity-crawlers",
            "https://support.anthropic.com/en/articles/8896518-does-anthropic-crawl-data-from-the-web-and-how-can-site-owners-block-the-crawler",
        ),
        supplemental=True,
        effort="medium",
        geo_scored=True,
    ),
    CheckSpec(
        "structured-data-graph",
        "Connected Schema.org JSON-LD",
        "AI Search / GEO",
        False,
        AI_SEARCH,
        (GUIDE, "https://schema.org/Article", "https://schema.org/BreadcrumbList"),
        supplemental=True,
        effort="medium",
        geo_scored=True,
    ),
    CheckSpec(
        "faq-structured-data",
        "FAQ structured data when applicable",
        "AI Search / GEO",
        False,
        AI_SEARCH,
        (GUIDE, "https://schema.org/FAQPage", "https://schema.org/Question"),
        supplemental=True,
        effort="low",
        geo_scored=True,
    ),
    CheckSpec(
        "date-transparency",
        "Publication/update date transparency",
        "AI Search / GEO",
        False,
        AI_SEARCH,
        (GUIDE, "https://schema.org/datePublished", "https://schema.org/dateModified"),
        supplemental=True,
        effort="low",
        geo_scored=True,
    ),
    CheckSpec(
        "citation-readiness",
        "Citation-ready content",
        "AI Search / GEO",
        False,
        AI_SEARCH,
        (GUIDE,),
        supplemental=True,
        experimental=True,
        effort="medium",
        geo_scored=False,
    ),
)

BY_ID = {c.id: c for c in CHECKS}
CORE_CHECK_IDS = tuple(c.id for c in CHECKS if not c.supplemental)
SUPPLEMENTAL_CHECK_IDS = tuple(c.id for c in CHECKS if c.supplemental)
AI_SEARCH_CHECK_IDS = tuple(c.id for c in CHECKS if "ai-search" in c.presets)
AI_SEARCH_EXTRA_IDS = tuple(c.id for c in CHECKS if "ai-search" in c.presets and c.supplemental)


def selected_checks(
    preset: str,
    only: list[str] | None = None,
    include: list[str] | None = None,
    exclude: list[str] | None = None,
) -> list[CheckSpec]:
    if preset not in {"all", "content", "api", "ai-search"}:
        raise ValueError("preset must be all, content, api, or ai-search")

    def validate(ids: list[str] | None) -> list[str]:
        ids = ids or []
        unknown = [x for x in ids if x not in BY_ID]
        if unknown:
            raise ValueError(f"Unknown check(s): {', '.join(unknown)}")
        return ids

    only = validate(only)
    include = validate(include)
    exclude = validate(exclude)
    excluded = set(exclude)

    if only:
        return [BY_ID[x] for x in only if x not in excluded]

    ids = [c.id for c in CHECKS if preset in c.presets]
    for cid in include:
        if cid not in ids:
            ids.append(cid)
    return [BY_ID[cid] for cid in ids if cid not in excluded]
