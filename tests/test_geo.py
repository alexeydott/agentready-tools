import json
import subprocess
from pathlib import Path

import pytest

from agentready.accesslog import analyze_ai_bot_log
from agentready.checks import CheckContext, check_ai_crawler_live_access
from agentready.geo_rules import rules_template
from agentready.gitutils import audit_git_dates, changed_urls_from_git
from agentready.http import Fetched
from agentready.indexnow import IndexNowError, build_payload
from agentready.models import CategoryScore, CheckResult, ScanReport
from agentready.registry import AI_SEARCH_EXTRA_IDS, BY_ID, selected_checks
from agentready.report import render_console, render_html, render_json, render_markdown
from agentready.scoring import ai_search_score, overall_score
from agentready.target import parse_target


def _row(cid: str, status: str, *, scored: bool = False, geo: bool = False) -> CheckResult:
    return CheckResult(cid, cid, "AI Search / GEO", status, scored, cid, supplemental=True, geo_scored=geo)


def test_ai_search_preset_and_separate_score():
    ids = {x.id for x in selected_checks("ai-search")}
    assert {"robots-txt", "sitemap", "search-indexability", "ai-crawler-live-access", "structured-data-graph", "date-transparency", "citation-readiness"} <= ids
    assert set(AI_SEARCH_EXTRA_IDS) <= ids

    rows = [
        _row("search-indexability", "pass", geo=True),
        _row("structured-data-graph", "fail", geo=True),
        _row("citation-readiness", "warn", geo=False),
    ]
    assert overall_score(rows) == 0
    assert ai_search_score(rows) == (50, 2)


def test_geo_score_is_rendered_but_machine_fields_stay_stable():
    row = _row("search-indexability", "pass", geo=True)
    report = ScanReport(
        target="https://example.com/page/",
        origin="https://example.com",
        preset="ai-search",
        checks=[row],
        score=0,
        level=0,
        level_name="Not Agent-Ready",
        level_model="transparent-tiered-v2",
        categories=[CategoryScore("AI Search / GEO", 0, 0, None)],
        next_level=None,
        recommendations=[],
        is_commerce=False,
        commerce_signals=[],
        started_at="2026-08-07T00:00:00+00:00",
        finished_at="2026-08-07T00:00:01+00:00",
        language="ru",
        ai_search_score=100,
        ai_search_applicable=1,
    )
    console = render_console(report, "ru")
    markdown = render_markdown(report, "ru")
    html = render_html(report, "ru")
    payload = json.loads(render_json(report, "ru"))
    assert "Оценка AI Search / GEO: 100/100" in console
    assert "Оценка AI Search / GEO" in markdown
    assert "Оценка AI Search / GEO" in html
    assert html.count("<details class='report-section'>") == 4
    assert "<summary id='report-recommendations'><h3>Приоритетные рекомендации</h3></summary>" in html
    assert "<summary id='report-remediation'><h3>Инструкции по исправлению</h3></summary>" in html
    assert payload["ai_search_score"] == 100
    assert payload["checks"][0]["id"] == "search-indexability"
    assert payload["checks"][0]["status"] == "pass"


def test_indexnow_payload_deduplicates_and_requires_one_host():
    payload = build_payload(
        ["https://example.com/a", "https://example.com/a", "https://example.com/b"],
        "12345678",
    )
    assert payload["host"] == "example.com"
    assert payload["urlList"] == ["https://example.com/a", "https://example.com/b"]
    with pytest.raises(IndexNowError):
        build_payload(["https://example.com/a", "https://other.example/b"], "12345678")


def _git(repo: Path, *args: str, env=None):
    merged = None
    if env:
        import os
        merged = os.environ.copy()
        merged.update(env)
    subprocess.run(["git", "-C", str(repo), *args], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=merged)


def test_git_changed_urls_and_date_audit(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test")
    content = repo / "site"
    content.mkdir()
    page = content / "guide.md"
    page.write_text("---\ncanonical: /guides/guide/\ndatePublished: 2026-08-01\ndateModified: 2026-08-01\n---\n# Guide\nOriginal factual content.\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "initial", env={"GIT_AUTHOR_DATE": "2026-08-01T12:00:00+03:00", "GIT_COMMITTER_DATE": "2026-08-01T12:00:00+03:00"})
    page.write_text("---\ncanonical: /guides/guide/\ndatePublished: 2026-08-01\ndateModified: 2026-08-07\n---\n# Guide\nUpdated factual content with a concrete limit: 100 requests.\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "update", env={"GIT_AUTHOR_DATE": "2026-08-07T12:00:00+03:00", "GIT_COMMITTER_DATE": "2026-08-07T12:00:00+03:00"})

    changed = changed_urls_from_git(repo, "https://example.com", content_root="site")
    assert len(changed) == 1
    assert changed[0].url == "https://example.com/guides/guide/"
    assert changed[0].mapping == "frontmatter:canonical"

    audit = audit_git_dates("site/guide.md", repo, tolerance_days=1)
    assert audit.declared_published == "2026-08-01"
    assert audit.declared_modified == "2026-08-07"
    assert audit.warnings == []


def test_ai_bot_log_summary_and_rules():
    lines = [
        '1.2.3.4 - - [07/Aug/2026:12:00:00 +0000] "GET /guide HTTP/1.1" 200 123 "-" "OAI-SearchBot/1.0"',
        '1.2.3.5 - - [07/Aug/2026:12:01:00 +0000] "GET /guide HTTP/1.1" 403 10 "-" "Claude-SearchBot/1.0"',
        '1.2.3.6 - - [07/Aug/2026:12:02:00 +0000] "GET / HTTP/1.1" 200 1 "-" "Mozilla/5.0"',
    ]
    out = analyze_ai_bot_log(lines)
    assert out["matched_ai_bot_lines"] == 2
    assert out["bots"]["OAI-SearchBot"]["status_codes"] == {"200": 1}
    assert out["bots"]["Claude-SearchBot"]["status_codes"] == {"403": 1}
    ru = rules_template("ru")
    assert "IndexNow" in ru and "dateModified" in ru and "keyword stuffing" in ru
    assert "Google-Extended" in ru and "нет отдельного HTTP User-Agent" in ru


def test_google_extended_is_a_robots_only_policy_check():
    class FakeClient:
        def __init__(self):
            self.user_agents = []

        def get(self, url, *, headers=None, use_cache=True):
            self.user_agents.append((headers or {}).get("User-Agent"))
            if url.endswith("/robots.txt"):
                body = b"User-agent: Google-Extended\nDisallow: /\n\nUser-agent: *\nAllow: /\n"
                return Fetched(url, 200, {"content-type": "text/plain"}, body, [])
            return Fetched(url, 200, {"content-type": "text/html"}, b"<h1>Guide</h1>", [])

    target = parse_target("https://example.com/guide")
    client = FakeClient()
    result = check_ai_crawler_live_access(
        CheckContext(target=target, client=client, content_url=target.url),
        BY_ID["ai-crawler-live-access"],
    )

    policy = next(item for item in result.evidence if item.action == "inspect robots policy for Google-Extended")
    assert policy.metrics == {
        "role": "training-policy",
        "robots_allowed": False,
        "network_ok": None,
        "spoofed_user_agent_probe": False,
    }
    assert "Google-Extended" not in client.user_agents
    assert result.status == "pass"
    assert "training crawlers are restricted: Google-Extended" in result.details
