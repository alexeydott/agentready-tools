from types import SimpleNamespace

from agentready.page_parser import Representation, parse_page
from agentready.seo.site_rules import evaluate_site_rules


def _page(url: str, body: bytes):
    representation = Representation.from_body(body, run_id="run", url_key=url)
    return SimpleNamespace(url=url, status_code=200, parsed=parse_page(body, representation=representation))


def test_site_rules_find_metadata_body_heading_canonical_and_hreflang_issues():
    pages = [
        _page(
            "https://example.test/en",
            b'<title>Same</title><h2>Skipped</h2><link rel="canonical" href="/de">'
            b'<link rel="alternate" hreflang="de" href="/de"><p>same words</p>',
        ),
        _page(
            "https://example.test/de",
            b'<title>Same</title><h2>Skipped</h2><link rel="canonical" href="/en">'
            b'<p>same words</p>',
        ),
    ]
    results = {item.id: item for item in evaluate_site_rules(pages, thin_word_limit=1)}
    assert results["duplicate-metadata-site"].status == "fail"
    assert results["duplicate-content-site"].status == "fail"
    assert results["heading-structure-site"].status == "warn"
    assert results["canonical-consistency-site"].status == "fail"
    assert results["hreflang-reciprocity-site"].status == "warn"


def test_site_rules_bound_evidence_and_skip_hreflang_when_absent():
    pages = [_page(f"https://example.test/{index}", b"<p>tiny</p>") for index in range(25)]
    results = {item.id: item for item in evaluate_site_rules(pages, evidence_limit=3, thin_word_limit=10)}
    assert len(results["thin-content-site"].evidence) == 3
    assert results["hreflang-reciprocity-site"].status == "skip"


def test_link_rules_report_depth_anchors_orphans_and_authority():
    from agentready.seo.site_rules import evaluate_link_rules

    root = _page("https://example.test/", b'<a href="/linked">Linked</a><a href="/linked">Linked</a>')
    linked = _page("https://example.test/linked", b"<p>linked</p>")
    orphan = _page("https://example.test/orphan", b"<p>orphan</p>")
    root.depth = 0
    linked.depth = 1
    orphan.depth = 1
    results = {item.id: item for item in evaluate_link_rules([root, linked, orphan], origin="https://example.test")}
    assert results["orphan-candidates-site"].status == "warn"
    assert results["link-depth-site"].status == "pass"
    assert results["anchor-distribution-site"].status == "pass"
    assert results["internal-link-authority-site"].status == "pass"
    assert results["orphan-candidates-site"].evidence[0].url.endswith("/orphan")
