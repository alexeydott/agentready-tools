from __future__ import annotations

from agentready.accesslog import analyze_ai_bot_log, analyze_project_ai_bot_log
from agentready.crawler_identity import (
    CrawlerIntent,
    IdentityConfidence,
    IdentityEvidenceSource,
    observe_crawler,
    verify_crawler,
)
from agentready.interaction import (
    InteractionApplicability,
    InteractionStatus,
    audit_accessibility_tree,
)


def test_accessibility_findings_keep_semantic_applicability() -> None:
    findings = audit_accessibility_tree(
        {
            "role": "document",
            "children": [
                {"role": "form", "name": "Sign in", "children": [{"role": "textbox", "name": "Email"}]},
                {"role": "button", "name": ""},
            ],
        }
    )

    controls, form = findings
    assert controls.status is InteractionStatus.WARN
    assert controls.applicability is InteractionApplicability.APPLICABLE
    assert form.status is InteractionStatus.WARN
    assert form.evidence[0].locator == "$.children[0]"
    assert controls.to_contract("https://example.test/").key.rule_version == "1.0.0"


def test_user_agent_is_observed_but_not_verified() -> None:
    observed = observe_crawler(
        "GPTBot/1.0",
        known_tokens=("GPTBot",),
        intent=CrawlerIntent.DISCOVERY,
        source=IdentityEvidenceSource.ACCESS_LOG,
    )
    unchanged = verify_crawler(observed)

    assert unchanged.confidence is IdentityConfidence.OBSERVED
    assert unchanged.is_verified is False


def test_identity_requires_independent_evidence_and_tracks_provider_dataset() -> None:
    observed = observe_crawler("GPTBot/1.0", known_tokens=("GPTBot",))

    verified = verify_crawler(observed, network_identity_verified=True, verification_locator="reverse-dns")
    dataset = verify_crawler(observed, provider_dataset_verified=True, verification_locator="provider.csv")

    assert verified.confidence is IdentityConfidence.VERIFIED
    assert dataset.confidence is IdentityConfidence.PROVIDER_DATASET
    assert dataset.intent is CrawlerIntent.PROVIDER_DATASET


def test_access_log_separates_observed_verified_and_redacts_query_values() -> None:
    lines = [
        '192.0.2.10 - - "GET /private?token=secret HTTP/1.1" 200 - "GPTBot/1.0"',
        '198.51.100.10 - - "GET /public HTTP/1.1" 200 - "GPTBot/1.0"',
    ]

    result = analyze_ai_bot_log(lines, verified_ips={"GPTBot": {"198.51.100.10"}})
    bot = result["bots"]["GPTBot"]

    assert bot["requests"] == 2
    assert bot["observed_requests"] == 2
    assert bot["verified_requests"] == 1
    assert result["observed_traffic"]["GPTBot"] == 2
    assert result["verified_traffic"]["GPTBot"] == 1
    assert bot["identity"]["confidence"] == "verified"
    assert all("secret" not in item["path"] for item in bot["top_paths"])


def test_project_access_log_matches_origin_windows_and_unmatched_buckets() -> None:
    lines = [
        '[18/Aug/2026:10:00:00 +0000] 198.51.100.10 - - "GET /docs?token=secret HTTP/1.1" 200 - "GPTBot/1.0"',
        '[18/Aug/2026:10:00:00 +0000] 198.51.100.10 - - "GET https://other.test/no HTTP/1.1" 200 - "GPTBot/1.0"',
        '[18/Aug/2026:12:00:00 +0000] 198.51.100.10 - - "GET /late HTTP/1.1" 200 - "GPTBot/1.0"',
        '[18/Aug/2026:10:00:00 +0000] 198.51.100.10 - - "GET /docs?token=secret HTTP/1.1" 200 - "GPTBot/1.0"',
    ]
    result = analyze_project_ai_bot_log(lines, project_target="https://example.test", end_at="2026-08-18T11:00:00+00:00", verified_ips={"GPTBot": {"198.51.100.10"}})
    assert result["totals"]["matched_requests"] == 1
    assert result["totals"]["duplicate_lines"] == 1
    assert result["unmatched"]["cross_origin"] == 1
    assert result["unmatched"]["out_of_window"] == 1
    assert result["bots"]["GPTBot"]["verified_requests"] == 1
    assert all("secret" not in str(result).lower() for _ in [0])
