import pytest

from agentready.custom_rules import CustomRule, CustomRuleKind, apply_rule, debug_representation


def test_custom_rules_support_bounded_text_regex_and_header_extraction():
    assert apply_rule(CustomRule("text", CustomRuleKind.TEXT, "agent"), text="agent ready") == ("agent",)
    assert apply_rule(CustomRule("regex", CustomRuleKind.REGEX, r"/[a-z]+", 1), text="/a /b") == ("/a",)
    assert apply_rule(CustomRule("header", CustomRuleKind.HEADER, "content-type"), headers={"content-type": "text/html"}) == ("text/html",)
    assert apply_rule(CustomRule("secret", CustomRuleKind.HEADER, "Authorization"), headers={"Authorization": "Bearer secret"}) == ("[REDACTED]",)
    assert apply_rule(CustomRule("json", CustomRuleKind.JSON_LD, "@type"), structured_data=({"@type": "Article"},)) == ('{"@type": "Article"}',)
    assert apply_rule(CustomRule("link", CustomRuleKind.LINK, "/docs"), links=("/docs", "/other")) == ("/docs",)


def test_custom_rules_reject_invalid_regex_and_unbounded_limits():
    with pytest.raises(ValueError):
        CustomRule("bad", CustomRuleKind.REGEX, "(", 1)
    with pytest.raises(ValueError):
        CustomRule("bad", CustomRuleKind.TEXT, "x", 1001)


def test_custom_rule_debugger_is_stable_and_bounded():
    rules = [
        CustomRule("b", CustomRuleKind.TEXT, "agent"),
        CustomRule("a", CustomRuleKind.REGEX, r"\w+", 1),
    ]
    first = debug_representation("agent ready", rules)
    second = debug_representation("agent ready", list(reversed(rules)))
    assert first == second
    assert [item.rule_id for item in first] == ["a", "b"]
    assert all(item.count <= 1 or item.rule_id == "b" for item in first)
