from __future__ import annotations

from agentready.http import Fetched
from agentready.seo.engine import aggregate_v2, run_atomic_rules
from agentready.seo.evidence import collect_page_evidence


class FakeClient:
    def __init__(self, body: bytes) -> None:
        self.calls = 0
        self.body = body

    def get(self, url: str) -> Fetched:
        self.calls += 1
        return Fetched(
            url=url,
            status_code=200,
            headers={"content-type": "text/html"},
            body=self.body,
            redirected_from=[],
        )


GOOD_HTML = b"""<!doctype html><html lang='en'><head>
<title>A sufficiently descriptive title for the page</title>
<meta name='description' content='A useful description'>
<link rel='canonical' href='https://example.test/page'>
<link rel='alternate' hreflang='en' href='https://example.test/page'>
<script type='application/ld+json'>{"@id":"https://example.test/page","@type":"Article"}</script>
</head><body><h1>Heading</h1></body></html>"""


def test_shared_evidence_is_collected_once_and_rules_are_deterministic() -> None:
    client = FakeClient(GOOD_HTML)
    evidence = collect_page_evidence("https://example.test/page", client)
    first = run_atomic_rules(evidence)
    second = run_atomic_rules(evidence)
    assert client.calls == 1
    assert first == second
    assert all(item.evidence_ids for item in first)
    assert all(item.fingerprint for item in first)


def test_atomic_rules_cover_metadata_canonical_hreflang_and_jsonld() -> None:
    evidence = collect_page_evidence("https://example.test/page", FakeClient(GOOD_HTML))
    findings = {item.rule.id: item for item in run_atomic_rules(evidence)}
    assert findings["metadata"].status == "pass"
    assert findings["canonical"].status == "pass"
    assert findings["hreflang"].status == "pass"
    assert findings["jsonld"].status == "pass"


def test_optional_capability_and_heuristic_rules_are_not_mandatory_score() -> None:
    html = b"<html><head><title>short</title></head><body><h1>Only</h1></body></html>"
    findings = {item.rule.id: item for item in run_atomic_rules(collect_page_evidence("https://example.test/page", FakeClient(html)))}
    assert findings["hreflang"].status == "skip"
    assert findings["hreflang"].scored is False
    assert findings["title-length"].rule.kind.value == "heuristic"
    assert findings["title-length"].scored is False
    assert findings["jsonld"].status == "skip"


def test_actionable_findings_have_evidence_and_v2_projection_is_canonical() -> None:
    html = b"<html><head><meta name='robots' content='noindex'></head><body></body></html>"
    findings = run_atomic_rules(collect_page_evidence("https://example.test/page", FakeClient(html)))
    indexability = next(item for item in findings if item.rule.id == "indexability")
    assert indexability.status == "fail"
    assert indexability.evidence_ids
    v2 = aggregate_v2(findings)
    assert all(item.id for item in v2)
    assert any(item.id == "indexability" and item.status.value == "fail" for item in v2)


def test_invalid_jsonld_is_evidence_backed_failure() -> None:
    html = b"<html><head><title>Valid title that is long enough for a heuristic</title><script type='application/ld+json'>{bad}</script></head><body><h1>x</h1></body></html>"
    findings = run_atomic_rules(collect_page_evidence("https://example.test/page", FakeClient(html)))
    jsonld = next(item for item in findings if item.rule.id == "jsonld")
    assert jsonld.status == "fail"
    assert jsonld.evidence_ids
