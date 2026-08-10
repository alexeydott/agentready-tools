from agentready.target import parse_target


def test_target_normalization():
    t = parse_target("example.com/path")
    assert t.url == "https://example.com/path"
    assert t.origin == "https://example.com"
