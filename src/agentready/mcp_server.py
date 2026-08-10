"""Optional MCP facade exposing the scanner as a read-only scan_site tool.

Requires: pip install 'agentready-tools[mcp]'
The tool blocks private/loopback targets because remote MCP servers must not be
usable as arbitrary SSRF proxies.
"""
from __future__ import annotations

try:
    from mcp.server import MCPServer
except ImportError as exc:  # pragma: no cover
    raise RuntimeError(
        "MCP dependency is missing. Activate the project virtual environment and run "
        "`python -m pip install -e \".[mcp]\"`; verify with "
        "`python -c \"import mcp; print(mcp.__file__)\"`."
    ) from exc

from .agentfindings import build_findings, build_remediation_plan
from .i18n import localized_report_dict
from .mobile_scanner import audit_mobile
from .scanner import scan
from .seo_scanner import audit_seo

import logging

logger = logging.getLogger(__name__)

mcp = MCPServer(
    "AgentReady Scanner",
    instructions=(
        "Read-only website audit for AI-agent discovery, content, auth, capability and commerce protocols. "
        "For coding agents: use audit_findings to get only the failed/warned checks with fix instructions, "
        "and remediation_plan to get a prioritized step-by-step fix plan with ready-to-use prompts."
    ),
)


@mcp.tool()
def scan_site(
    url: str,
    preset: str = "all",
    content_url: str | None = None,
    commerce_url: str | None = None,
    include: list[str] | None = None,
    language: str = "en",
) -> dict:
    """Scan a public website for AI-agent readiness. No payment or credentials are submitted."""
    report = scan(
        url,
        preset=preset,
        content_url=content_url,
        commerce_url=commerce_url,
        include=include,
        allow_private=False,
        language=language,
    )
    return localized_report_dict(report, language)


@mcp.tool()
def seo_audit(
    url: str,
    language: str = "en",
    recommendation_limit: int = 10,
    crawl: bool = False,
    max_pages: int = 25,
    render: bool = False,
    ga_property: str | None = None,
    gsc_site: str | None = None,
) -> dict:
    """Audit one public page for SEO best-practice gaps without mutation or credentials.

    With ``crawl=True`` a bounded same-origin crawl adds cross-page checks
    (broken links, duplicate metadata, redirect chains, internal nofollow,
    and insecure HTTP links with affected page URLs).
    ``render=True`` uses a headless browser for JS-driven pages.
    ``ga_property`` / ``gsc_site`` enable GA4/Search Console analytics checks
    using the service account stored via `agentready seo credentials set`.
    """
    report = audit_seo(
        url,
        allow_private=False,
        recommendation_limit=recommendation_limit,
        language=language,
        crawl=crawl,
        max_pages=max_pages,
        render=render,
        ga_property=ga_property,
        gsc_site=gsc_site,
    )
    return report.to_dict()


@mcp.tool()
def audit_findings(
    url: str,
    mode: str = "readiness",
    preset: str = "all",
    language: str = "en",
    recommendation_limit: int = 10,
) -> dict:
    """Return only optimization gaps for a coding agent.

    Runs a readiness scan (mode="readiness") or a single-page SEO audit
    (mode="seo") and returns each failed/warned check with a localized
    explanation of why it matters, observed evidence, and fix instructions.
    """
    logger.debug("audit_findings: url=%s mode=%s lang=%s", url, mode, language)
    if mode == "seo":
        report = audit_seo(
            url,
            allow_private=False,
            recommendation_limit=recommendation_limit,
            language=language,
        )
        return build_findings(report, language)
    if mode != "readiness":
        raise ValueError("unsupported mode: expected 'readiness' or 'seo'")
    report = scan(url, preset=preset, allow_private=False, language=language)
    return build_findings(report, language)


@mcp.tool()
def remediation_plan(
    url: str,
    mode: str = "readiness",
    preset: str = "all",
    language: str = "en",
    recommendation_limit: int = 10,
) -> dict:
    """Return a prioritized step-by-step fix plan for a coding agent.

    Each step contains fix instructions, a ready-to-use agent prompt, a
    verification command and reference links, ordered by impact/effort.
    """
    logger.debug("remediation_plan: url=%s mode=%s lang=%s", url, mode, language)
    if mode == "seo":
        report = audit_seo(
            url,
            allow_private=False,
            recommendation_limit=recommendation_limit,
            language=language,
        )
        return build_remediation_plan(report, language)
    if mode != "readiness":
        raise ValueError("unsupported mode: expected 'readiness' or 'seo'")
    report = scan(url, preset=preset, allow_private=False, language=language)
    return build_remediation_plan(report, language)


@mcp.tool()
def mobile_audit(
    urls: list[str],
    render: bool = False,
    language: str = "en",
    recommendation_limit: int = 10,
) -> dict:
    """Audit one or more public pages for mobile-friendliness (Google Mobile-Friendly signals).

    Returns per-page and aggregate scores with static HTML/CSS checks and,
    when ``render=True``, Playwright-rendered viewport/tap-target/font metrics.
    """
    logger.debug("mobile_audit: urls=%d render=%s lang=%s", len(urls), render, language)
    report = audit_mobile(
        urls,
        render=render,
        allow_private=False,
        recommendation_limit=recommendation_limit,
        language=language,
    )
    return report.to_dict()


@mcp.tool()
def mobile_findings(
    url: str,
    render: bool = False,
    language: str = "en",
    recommendation_limit: int = 10,
) -> dict:
    """Return only the mobile-friendliness gaps for a coding agent (single page)."""
    logger.debug("mobile_findings: url=%s render=%s lang=%s", url, render, language)
    report = audit_mobile(
        [url],
        render=render,
        allow_private=False,
        recommendation_limit=recommendation_limit,
        language=language,
    )
    return build_findings(report.pages[0], language)


@mcp.tool()
def mobile_remediation_plan(
    url: str,
    render: bool = False,
    language: str = "en",
    recommendation_limit: int = 10,
) -> dict:
    """Return a prioritized mobile-friendliness fix plan for a coding agent (single page)."""
    logger.debug("mobile_remediation_plan: url=%s render=%s lang=%s", url, render, language)
    report = audit_mobile(
        [url],
        render=render,
        allow_private=False,
        recommendation_limit=recommendation_limit,
        language=language,
    )
    return build_remediation_plan(report.pages[0], language)


def _run_ai(
    *,
    operation: str,
    target: str | None,
    report: dict | None,
    mode: str,
    language: str,
    model: str | None = None,
    message: str | None = None,
    history: list[dict[str, str]] | None = None,
) -> dict:
    import asyncio
    from .ai_assistant import AIAssistant
    from .ai_models import AssistantRequest, ConversationMessage
    from .ai_provider import OpenAICompatibleProvider
    from .config import active_ai_provider, load_config

    cfg, _ = load_config()
    ai_cfg = cfg["ai"]
    selected_provider = active_ai_provider(ai_cfg)
    if not ai_cfg["enabled"] or not ai_cfg["transport_enabled"]:
        raise ValueError("AI assistant transport is disabled")
    if report is None:
        if not target:
            raise ValueError("target or report is required")
        report = audit_seo(target, allow_private=False, language=language).to_dict()
    messages = tuple(ConversationMessage(item["role"], item["content"]) for item in (history or [])[:ai_cfg["history_limit"]])
    request = AssistantRequest(
        operation=operation,
        mode=mode,
        language=language,
        target=target,
        report=report,
        message=message,
        history=messages,
    )
    provider = OpenAICompatibleProvider(
        base_url=selected_provider["base_url"],
        credential_id=selected_provider["credential_id"],
        timeout=ai_cfg["timeout"],
        max_retries=ai_cfg["max_retries"],
        allow_loopback_http=ai_cfg["allow_loopback_http"],
    )
    return asyncio.run(AIAssistant(provider, context_limit=ai_cfg["context_limit"], max_concurrent=ai_cfg["max_concurrent"]).run(request, model=model or selected_provider.get("model") or ai_cfg["model"])).to_dict()


@mcp.tool()
def ai_recommend(
    target: str | None = None,
    report: dict | None = None,
    mode: str = "both",
    language: str = "en",
    model: str | None = None,
) -> dict:
    """Generate opt-in SEO/GEO recommendations using supplied audit evidence."""
    return _run_ai(operation="recommend", target=target, report=report, mode=mode, language=language, model=model)


@mcp.tool()
def ai_chat(
    message: str,
    target: str | None = None,
    report: dict | None = None,
    mode: str = "both",
    language: str = "en",
    model: str | None = None,
    history: list[dict[str, str]] | None = None,
) -> dict:
    """Run one stateless, opt-in SEO/GEO assistant chat turn."""
    return _run_ai(operation="chat", target=target, report=report, mode=mode, language=language, model=model, message=message, history=history)


def main(host: str = "127.0.0.1", port: int = 8766) -> None:
    if host not in {"127.0.0.1", "::1", "localhost"}:
        logger.error("MCP server must bind to loopback for the unauthenticated local transport")
        raise ValueError("MCP server is loopback-only")
    logger.info("Starting MCP server: host=%s port=%s", host, port)
    mcp.run(transport="streamable-http", host=host, port=port, streamable_http_path="/mcp", json_response=True)


if __name__ == "__main__":
    main()
