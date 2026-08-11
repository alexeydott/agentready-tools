from agentready.seo.rules.builtin import SEO_ATOMIC_RULES, rule_groups, rule_manifest
from pathlib import Path
import ast


def test_builtin_rule_manifest_is_unique_and_machine_readable():
    manifest = rule_manifest()
    assert len(manifest) == len(SEO_ATOMIC_RULES)
    assert len({item["id"] for item in manifest}) == len(manifest)
    assert all(item["status"] == "implemented" for item in manifest)
    assert all("category" in item and "kind" in item for item in manifest)


def test_seo_rules_are_pure_and_heuristics_are_not_scored_by_default():
    source = Path(__file__).parents[1] / "src" / "agentready" / "seo" / "rules" / "builtin.py"
    imports = {
        alias.name.split(".", 1)[0]
        for node in ast.walk(ast.parse(source.read_text(encoding="utf-8")))
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    assert not imports & {"httpx", "sqlite3", "playwright"}
    assert all(
        item["scored_by_default"] is False
        for item in rule_manifest()
        if item["kind"] == "heuristic"
    )


def test_rule_groups_expose_complete_taxonomy_and_implementation_status():
    groups = rule_groups()

    assert {item["id"] for item in groups} >= {
        "visibility",
        "crawl-index",
        "canonical-duplicates",
        "performance",
    }
    assert any(item["status"] == "implemented" for item in groups)
    assert any(item["status"] == "planned" for item in groups)
