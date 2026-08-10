from agentready.checks import (
    _decode_b64_json,
    _index_md_url,
    _parse_content_signal,
    _robots_user_agents,
    _valid_skill_entry,
)
from agentready import __version__
from agentready.http import HttpClient
from agentready.models import CheckResult
from agentready.recommendations import generate_recommendations
from agentready.remediation import remediation_for
from agentready.registry import BY_ID
from agentready.scoring import maturity_level, overall_score
from agentready.scanner import detect_commerce


def row(cid: str, status: str, scored: bool = True, category: str = "x") -> CheckResult:
    return CheckResult(cid, cid, category, status, scored, cid)


def test_content_signal():
    ok, values, why = _parse_content_signal("search=yes, ai-input=yes, ai-train=no")
    assert ok and values["ai-train"] == "no"
    ok, _, _ = _parse_content_signal("ai-train=maybe")
    assert not ok


def test_http_client_uses_current_package_version_in_default_user_agent():
    with HttpClient() as client:
        assert client._client.headers["user-agent"].startswith(f"agentready-tools/{__version__}")


def test_robots_agents():
    agents = _robots_user_agents("User-agent: GPTBot\nDisallow: /x\nUser-agent: *\nAllow: /")
    assert "gptbot" in agents and "*" in agents


def test_skill_validation():
    good = {
        "name": "scan-site",
        "type": "skill-md",
        "description": "Scan a site",
        "url": "https://example.com/SKILL.md",
        "digest": "a" * 64,
    }
    assert _valid_skill_entry(good)[0]


def test_score_ratio():
    assert overall_score([row("a", "pass"), row("b", "fail"), row("c", "warn", False)]) == 50


def test_level_tiered_sequential():
    results = [
        row("robots-txt", "pass"),
        row("sitemap", "pass"),
        row("link-headers", "pass"),
        row("ai-bot-rules", "pass"),
        row("content-signals", "pass"),
        row("markdown-negotiation", "pass"),
        row("api-catalog", "pass"),
        row("oauth-discovery", "pass"),
        row("oauth-protected-resource", "pass"),
        row("mcp-server-card", "pass"),
        row("a2a-agent-card", "fail"),
        row("agent-skills", "pass"),
    ]
    level, name, nxt = maturity_level(results, 0.8)
    assert level == 5 and name == "Agent-Native" and nxt is None


def test_level_reports_progress():
    results = [
        row("robots-txt", "pass"),
        row("sitemap", "fail"),
        row("link-headers", "pass"),
    ]
    level, _, nxt = maturity_level(results, 0.8)
    assert level == 0
    assert nxt is not None and nxt.target == 1 and nxt.current == 2 and nxt.needed == 3 and nxt.remaining == 1


def test_index_md_url():
    assert _index_md_url("https://example.com/docs/page/") == "https://example.com/docs/page/index.md"
    assert _index_md_url("https://example.com/docs/page") == "https://example.com/docs/page/index.md"


def test_commerce_detection():
    html = '<script type="application/ld+json">{"@type":"Product"}</script><a href="/checkout">go</a>'
    signals = detect_commerce(html)
    assert "schema.org Product/Offer" in signals
    assert "cart/checkout link" in signals


def test_development_source_url_is_omitted_from_report_references():
    remediation = remediation_for(BY_ID["ai-bot-rules"], "https://example.com/")

    assert remediation.references == []
    assert "Tochki" not in remediation.summary
