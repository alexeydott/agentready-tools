import pytest

from agentready.custom_rules import (
    CustomRule,
    CustomRuleKind,
    apply_rule,
    builtin_presets,
    debug_representation,
    apply_rules,
    compile_rules,
    validate_rules,
    css_matches_from_html,
)


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


def test_css_rules_require_matches_from_shared_representation_and_presets_are_editable():
    rule = CustomRule("css", CustomRuleKind.CSS, "img[loading=lazy]")
    assert apply_rule(rule, text="img[loading=lazy]") == ()
    assert apply_rule(rule, css_matches=("img[loading=lazy]",)) == ("img[loading=lazy]",)
    presets = builtin_presets()
    assert {"analytics", "schema"} <= set(presets)
    assert presets["analytics"] is not builtin_presets()["analytics"]


def test_custom_rules_v1_document_compiles_with_stable_hash_and_applies_metadata():
    document = """version: 1
rules:
  - id: product
    title: Product text
    scope: page
    assert:
      kind: text
      pattern: Product
    severity: high
"""
    first = compile_rules(document)
    second = compile_rules(document)
    assert first.rule_hash == second.rule_hash
    result = apply_rules(first, text="Product page")
    assert result["rule_hash"] == first.rule_hash
    assert result["matches"][0]["severity"] == "high"
    assert validate_rules(document)["valid"] is True


def test_custom_rules_reject_expensive_regex_and_unknown_dsl_shape():
    with pytest.raises(ValueError, match="unsupported or expensive"):
        compile_rules({"version": 1, "rules": [{"id": "evil", "assert": {"kind": "regex", "pattern": "(a+)+"}}]})
    with pytest.raises(ValueError):
        compile_rules({"version": 2, "rules": []})
    with pytest.raises(ValueError):
        compile_rules({"version": 1, "rules": [{"id": "x", "when": {"eval": "1"}, "assert": {"kind": "text", "pattern": "x"}}]})


def test_css_selector_is_evaluated_against_saved_html():
    matches = css_matches_from_html('<main><p class="notice">Known</p><p>Other</p></main>', "main p.notice")
    assert len(matches) == 1
    assert "notice" in matches[0]
