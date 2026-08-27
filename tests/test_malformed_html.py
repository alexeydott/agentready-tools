"""Test malformed HTML handling in structured_data.py"""
from agentready.structured_data import extract_jsonld_nodes


def test_malformed_html_with_assertion_error():
    """Regression: malformed HTML caused AssertionError in HTML parser."""
    # This specific pattern triggered the bug
    malformed_html = (
        '<html><body>'
        '<script type="application/ld+json">'
        '<![)C@z\n\\T\x03;\x01'
        '</script>'
        '</body></html>'
    )
    nodes, errors, count = extract_jsonld_nodes(malformed_html)
    # Should not raise, should return empty results gracefully
    assert isinstance(nodes, list)
    assert isinstance(errors, list)
    assert isinstance(count, int)


def test_valid_jsonld_still_works():
    """Valid JSON-LD should still be extracted correctly."""
    valid_html = (
        '<html><body>'
        '<script type="application/ld+json">'
        '{"@type": "WebSite", "name": "Test"}'
        '</script>'
        '</body></html>'
    )
    nodes, errors, count = extract_jsonld_nodes(valid_html)
    assert count == 1
    assert len(nodes) == 1
    assert nodes[0]["@type"] == "WebSite"
