from agentready.page_parser import parse_page
from agentready.audit_core.collection import CollectedPage, FactView
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


def test_seo_evidence_projects_collected_fact_view_without_legacy_title_attribute():
    page = parse_page(b"<title>Collected</title><h1>Heading</h1>")
    view = FactView(CollectedPage("https://example.test/", 0, 200, page.representation, page.facts))
    evidence = evidence_from_parsed_page(
        view,
        url="https://example.test/",
        final_url="https://example.test/",
        status_code=200,
        content_type="text/html",
    )
    assert evidence.title == "Collected"


def test_seo_evidence_preserves_case_insensitive_x_robots_values():
    page = parse_page(b"<title>Collected</title>")
    view = FactView(
        CollectedPage(
            "https://example.test/",
            0,
            200,
            page.representation,
            page.facts,
            headers=(("x-robots-tag", "noindex"), ("X-Robots-Tag", "nofollow")),
        )
    )
    evidence = evidence_from_parsed_page(
        view,
        url="https://example.test/",
        final_url="https://example.test/",
        status_code=200,
        content_type="text/html",
    )
    assert evidence.x_robots == "noindex, nofollow"


def test_shared_parser_preserves_jsonld_nodes_and_errors():
    page = parse_page(
        b'<script type="application/ld+json">{"@type":"Article"}</script>'
        b'<script type="application/ld+json">{bad}</script>'
    )
    assert page.facts is not None
    assert page.facts.jsonld_nodes == ({"@type": "Article"},)
    assert page.facts.jsonld_errors
    assert page.facts.jsonld_block_count == 2
