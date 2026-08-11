from agentready.page_parser import parse_page
from agentready.seo.evidence import evidence_from_parsed_page


def test_legacy_seo_evidence_can_project_shared_parsed_facts():
    page = parse_page(
        b'<title>Example</title><meta name="description" content="Desc">'
        b'<h1>Heading</h1><link rel="canonical" href="/">'
    )
    evidence = evidence_from_parsed_page(
        page,
        url="https://example.test/",
        final_url="https://example.test/",
        status_code=200,
        content_type="text/html",
    )
    assert evidence.title == "Example"
    assert evidence.description == "Desc"
    assert evidence.h1 == ("Heading",)
    assert evidence.canonicals == ("https://example.test/",)
