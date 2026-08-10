from pathlib import Path

from agentready.config import default_config_yaml, load_config
from agentready.registry import selected_checks


def test_config_roundtrip(tmp_path: Path):
    p = tmp_path / ".agentready.yml"
    p.write_text(default_config_yaml(), encoding="utf-8")
    cfg, source = load_config(p)
    assert cfg["preset"] == "all"
    assert cfg["scoring"]["level_threshold"] == 0.8
    assert source == str(p.resolve())


def test_supplemental_is_opt_in():
    default_ids = [x.id for x in selected_checks("all")]
    assert "llms-txt" not in default_ids
    assert {"search-indexability", "structured-data-graph", "citation-readiness"} <= set(default_ids)
    ids = [x.id for x in selected_checks("all", include=["llms-txt"])]
    assert "llms-txt" in ids


def test_config_report_language(tmp_path: Path):
    p = tmp_path / ".agentready.yml"
    content = default_config_yaml().replace("language: en", "language: ru")
    p.write_text(content, encoding="utf-8")
    cfg, _ = load_config(p)
    assert cfg["report"]["language"] == "ru"
