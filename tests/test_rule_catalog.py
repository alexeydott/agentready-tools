"""Tests for the frozen v2.1.0-draft.1 rule catalog packaging and loader (#17).

These tests validate the packaged artifact itself, not rule execution:
Issue #17 explicitly forbids registering or executing any frozen rule.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from zipfile import ZipFile

import pytest
import yaml

from agentready.audit_core.fact_schema import DEFAULT_FACT_SCHEMA_VERSIONS
from agentready.seo.rules.catalog import (
    CATALOG_SCHEMA_ID,
    RuleCatalogValidationError,
    catalog_schema_bytes,
    catalog_yaml_bytes,
    compute_catalog_digest,
    load_frozen_rule_catalog,
    validate_catalog_document,
)

ROOT = Path(__file__).parents[1]
PACKAGE_CATALOG_DIR = ROOT / "src" / "agentready" / "seo" / "rules" / "catalog"
CATALOG_YAML_PATH = PACKAGE_CATALOG_DIR / "agentready.rule-catalog.v2.yaml"
CATALOG_SCHEMA_PATH = PACKAGE_CATALOG_DIR / "agentready.rule-catalog.v2.schema.json"
ROOT_SCHEMA_PATH = ROOT / "schemas" / "agentready.rule-catalog.v2.schema.json"

EXPECTED_MODULE_COUNTS = {
    "core-coverage": 20,
    "core-canonical": 20,
    "core-links": 20,
    "google-hreflang": 10,
    "google-metadata": 15,
    "robots-sitemap": 20,
    "structured-data": 20,
    "security": 15,
    "images": 15,
    "content": 15,
    "performance": 10,
    "mobile": 10,
    "agent-readiness": 10,
}


def _minimal_valid_document() -> dict[str, object]:
    return {
        "schema": CATALOG_SCHEMA_ID,
        "catalog_version": "2.1.0-draft.1",
        "generated_at": "2026-08-21T00:00:00Z",
        "rule_count": 1,
        "modules": [{"id": "demo", "count": 1}],
        "source_registry": {"demo-source": {"title": "Demo source", "url": "https://example.test/demo"}},
        "rules": [
            {
                "rule_id": "DEMO-001",
                "version": "1.0.0",
                "title": "Demo rule",
                "module": "demo",
                "applicability": {"applies_to": "html-page", "condition": "always"},
                "fact_requirements": [{"family": "page", "min_schema_version": "1"}],
                "source_ids": ["demo-source"],
                "score_role": "scored",
                "failure_policy": "block_on_missing_facts",
                "summary": "Demo rule summary.",
            }
        ],
    }


# --- artifact presence in the source checkout -----------------------------


def test_catalog_artifact_exists_in_source_checkout():
    assert CATALOG_YAML_PATH.is_file()
    assert CATALOG_SCHEMA_PATH.is_file()


def test_root_schema_copy_matches_packaged_schema_copy():
    assert ROOT_SCHEMA_PATH.is_file(), "public schema contract copy is missing under schemas/"
    assert ROOT_SCHEMA_PATH.read_bytes() == CATALOG_SCHEMA_PATH.read_bytes(), (
        "schemas/agentready.rule-catalog.v2.schema.json must stay byte-identical to the "
        "packaged runtime copy"
    )


def test_source_archive_contains_frozen_catalog_artifact(tmp_path):
    pwsh = shutil.which("pwsh")
    if pwsh is None:
        pytest.skip("PowerShell is required to execute the source packaging script")

    output = tmp_path / "source.zip"
    subprocess.run(
        [pwsh, "-File", str(ROOT / "scripts" / "package-source.ps1"), "-Output", str(output)],
        check=True,
        capture_output=True,
        text=True,
    )
    with ZipFile(output) as archive:
        names = {name.replace("\\", "/") for name in archive.namelist()}
    assert any(name.endswith("schemas/agentready.rule-catalog.v2.schema.json") for name in names)
    assert any(
        name.endswith("src/agentready/seo/rules/catalog/agentready.rule-catalog.v2.yaml") for name in names
    )
    assert any(
        name.endswith("src/agentready/seo/rules/catalog/agentready.rule-catalog.v2.schema.json")
        for name in names
    )


@pytest.mark.scale
def test_wheel_and_sdist_contain_frozen_catalog_artifact(tmp_path):
    build_module = pytest.importorskip("build")
    from build import ProjectBuilder

    builder = ProjectBuilder(str(ROOT))
    wheel_path = Path(builder.build("wheel", str(tmp_path)))
    sdist_path = Path(builder.build("sdist", str(tmp_path)))

    with ZipFile(wheel_path) as archive:
        wheel_names = {name.replace("\\", "/") for name in archive.namelist()}
    assert any(
        name.endswith("agentready/seo/rules/catalog/agentready.rule-catalog.v2.yaml") for name in wheel_names
    )
    assert any(
        name.endswith("agentready/seo/rules/catalog/agentready.rule-catalog.v2.schema.json")
        for name in wheel_names
    )

    import tarfile

    with tarfile.open(sdist_path) as archive:
        sdist_names = {name.replace("\\", "/") for name in archive.getnames()}
    assert any(
        name.endswith("agentready/seo/rules/catalog/agentready.rule-catalog.v2.yaml") for name in sdist_names
    )
    assert any(
        name.endswith("agentready/seo/rules/catalog/agentready.rule-catalog.v2.schema.json")
        for name in sdist_names
    )
    del build_module


# --- loader / validation ----------------------------------------------------


def test_frozen_catalog_loads_with_expected_identity():
    artifact = load_frozen_rule_catalog()
    assert artifact.schema == CATALOG_SCHEMA_ID
    assert artifact.catalog_version == "2.1.0-draft.1"
    assert artifact.rule_count == 200
    assert len(artifact.rules) == 200


def test_frozen_catalog_module_counts_match_expected_taxonomy():
    artifact = load_frozen_rule_catalog()
    assert dict(artifact.module_counts) == EXPECTED_MODULE_COUNTS
    assert sum(artifact.module_counts.values()) == 200


def test_frozen_catalog_rule_ids_are_unique():
    artifact = load_frozen_rule_catalog()
    rule_ids = [rule.rule_id for rule in artifact.rules]
    assert len(rule_ids) == len(set(rule_ids))


def test_frozen_catalog_rule_versions_are_valid_semver():
    artifact = load_frozen_rule_catalog()
    for rule in artifact.rules:
        parts = rule.version.split(".")
        assert len(parts) == 3 and all(part.isdigit() for part in parts), rule.rule_id


def test_frozen_catalog_source_ids_resolve_in_source_registry():
    artifact = load_frozen_rule_catalog()
    for rule in artifact.rules:
        for source_id in rule.source_ids:
            assert source_id in artifact.source_registry, f"{rule.rule_id} references unknown source {source_id}"


def test_frozen_catalog_fact_requirements_have_family_and_version():
    artifact = load_frozen_rule_catalog()
    for rule in artifact.rules:
        assert rule.fact_requirements
        for requirement in rule.fact_requirements:
            assert requirement.family
            assert requirement.min_schema_version


def test_frozen_catalog_fact_requirement_families_are_known_runtime_families():
    """Preflight-audit style guard: the catalog must reference fact families
    that the current shared fact layer actually emits (see
    ``agentready.audit_core.fact_schema.DEFAULT_FACT_SCHEMA_VERSIONS``),
    catching drift between the frozen catalog draft and runtime support."""
    artifact = load_frozen_rule_catalog()
    known_families = set(DEFAULT_FACT_SCHEMA_VERSIONS)
    for rule in artifact.rules:
        for requirement in rule.fact_requirements:
            assert requirement.family in known_families, (
                f"{rule.rule_id} requires unknown fact family {requirement.family!r}"
            )


def test_frozen_catalog_named_stage_e_canary_rule_ids_present():
    artifact = load_frozen_rule_catalog()
    rule_ids = {rule.rule_id for rule in artifact.rules}
    expected = {
        "CORE-COVERAGE-001",
        *[f"CORE-CANON-{i:03d}" for i in range(1, 9)],
        *[f"GOOGLE-HREF-{i:03d}" for i in range(1, 6)],
        "GOOGLE-DESC-001",
        "GOOGLE-TITLE-001",
    }
    assert expected <= rule_ids


def test_deterministic_digest_across_repeated_loads():
    data = catalog_yaml_bytes()
    first = compute_catalog_digest(data)
    second = compute_catalog_digest(catalog_yaml_bytes())
    assert first == second
    assert first == load_frozen_rule_catalog().digest


def test_valid_minimal_document_passes_validation():
    validate_catalog_document(_minimal_valid_document())


def test_invalid_schema_id_is_rejected():
    document = _minimal_valid_document()
    document["schema"] = "agentready.rule-catalog.v1"
    with pytest.raises(RuleCatalogValidationError):
        validate_catalog_document(document)


def test_duplicate_rule_id_is_rejected():
    document = _minimal_valid_document()
    document["rules"].append(dict(document["rules"][0]))
    document["rule_count"] = 2
    document["modules"] = [{"id": "demo", "count": 2}]
    with pytest.raises(RuleCatalogValidationError) as excinfo:
        validate_catalog_document(document)
    assert any("duplicate rule_id" in error for error in excinfo.value.errors)


def test_unknown_source_id_is_rejected():
    document = _minimal_valid_document()
    document["rules"][0]["source_ids"] = ["missing-source"]
    with pytest.raises(RuleCatalogValidationError) as excinfo:
        validate_catalog_document(document)
    assert any("unknown source_id" in error for error in excinfo.value.errors)


def test_missing_fact_requirements_field_is_rejected():
    document = _minimal_valid_document()
    document["rules"][0]["fact_requirements"] = [{"family": "page"}]
    with pytest.raises(RuleCatalogValidationError) as excinfo:
        validate_catalog_document(document)
    assert any("fact_requirements" in error for error in excinfo.value.errors)


def test_mismatched_rule_count_is_rejected():
    document = _minimal_valid_document()
    document["rule_count"] = 2
    with pytest.raises(RuleCatalogValidationError) as excinfo:
        validate_catalog_document(document)
    assert any("rule_count" in error for error in excinfo.value.errors)


def test_mismatched_module_count_is_rejected():
    document = _minimal_valid_document()
    document["modules"] = [{"id": "demo", "count": 5}]
    with pytest.raises(RuleCatalogValidationError) as excinfo:
        validate_catalog_document(document)
    assert any("declares count" in error for error in excinfo.value.errors)


def test_undeclared_module_reference_is_rejected():
    document = _minimal_valid_document()
    document["rules"][0]["module"] = "other"
    with pytest.raises(RuleCatalogValidationError) as excinfo:
        validate_catalog_document(document)
    assert any("not declared in modules" in error for error in excinfo.value.errors)


def test_invalid_score_role_is_rejected():
    document = _minimal_valid_document()
    document["rules"][0]["score_role"] = "definitely-not-valid"
    with pytest.raises(RuleCatalogValidationError) as excinfo:
        validate_catalog_document(document)
    assert any("score_role" in error for error in excinfo.value.errors)


def test_invalid_failure_policy_is_rejected():
    document = _minimal_valid_document()
    document["rules"][0]["failure_policy"] = "definitely-not-valid"
    with pytest.raises(RuleCatalogValidationError) as excinfo:
        validate_catalog_document(document)
    assert any("failure_policy" in error for error in excinfo.value.errors)


def test_missing_top_level_key_is_rejected():
    document = _minimal_valid_document()
    del document["source_registry"]
    with pytest.raises(RuleCatalogValidationError) as excinfo:
        validate_catalog_document(document)
    assert any("missing required top-level key: source_registry" in error for error in excinfo.value.errors)


def test_schema_bytes_are_valid_json():
    import json

    schema = json.loads(catalog_schema_bytes())
    assert schema["$id"] == CATALOG_SCHEMA_ID


def test_packaged_yaml_bytes_round_trip_through_pyyaml():
    document = yaml.safe_load(catalog_yaml_bytes())
    assert document["schema"] == CATALOG_SCHEMA_ID
    assert document["rule_count"] == 200
