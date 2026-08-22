"""Tests for the immutable catalog loader / RuleCatalogSnapshot (#18).

Issue #18 requires: one canonical authoritative loader, immutable snapshot
value objects, deterministic catalog identity, no in-place mutation, no
network/browser/provider calls, fail-closed validation, and strict
separation from caller-supplied custom ruleset identity. This module owns
those tests; #17's own tests continue to own packaging/schema/digest
concerns for the raw artifact.
"""
from __future__ import annotations

import ast
import dataclasses
from pathlib import Path

import pytest

from agentready.audit_core.rule_catalog import (
    RuleCatalogEntry,
    RuleCatalogSnapshot,
    RuleCatalogSourceRef,
    RuleCatalogValidationError,
    catalog_identity,
    load_rule_catalog_snapshot,
)
from agentready.audit_core.run_context import AuditRunContext
from agentready.seo.rules.catalog import CATALOG_SCHEMA_ID

ROOT = Path(__file__).parents[1]
SOURCE = ROOT / "src" / "agentready"


def test_load_rule_catalog_snapshot_succeeds():
    snapshot = load_rule_catalog_snapshot()
    assert isinstance(snapshot, RuleCatalogSnapshot)
    assert snapshot.schema == CATALOG_SCHEMA_ID
    assert snapshot.catalog_version == "2.1.0-draft.2"
    assert snapshot.rule_count == 200
    assert len(snapshot.entries) == 200


def test_two_loads_produce_equal_catalog_identity():
    first = load_rule_catalog_snapshot()
    second = load_rule_catalog_snapshot()
    assert first.schema == second.schema
    assert first.catalog_version == second.catalog_version
    assert first.rule_catalog_digest == second.rule_catalog_digest
    assert first.rule_count == second.rule_count
    assert first.entries == second.entries


def test_snapshot_and_entries_are_frozen_dataclasses():
    snapshot = load_rule_catalog_snapshot()
    assert dataclasses.is_dataclass(snapshot)
    assert snapshot.__dataclass_params__.frozen is True
    entry = snapshot.entries[0]
    assert isinstance(entry, RuleCatalogEntry)
    assert entry.__dataclass_params__.frozen is True
    with pytest.raises(dataclasses.FrozenInstanceError):
        entry.title = "mutated"  # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        snapshot.rule_count = 0  # type: ignore[misc]


def test_snapshot_entries_tuple_cannot_be_appended_to():
    snapshot = load_rule_catalog_snapshot()
    assert isinstance(snapshot.entries, tuple)
    with pytest.raises(AttributeError):
        snapshot.entries.append(snapshot.entries[0])  # type: ignore[attr-defined]


def test_snapshot_module_counts_cannot_be_mutated_in_place():
    """#18 requires true immutability, not just a frozen dataclass wrapper:
    module_counts must reject item assignment/deletion even though the
    dataclass field itself only holds a reference to the mapping."""
    snapshot = load_rule_catalog_snapshot()
    with pytest.raises(TypeError):
        snapshot.module_counts["core-coverage"] = 0  # type: ignore[index]
    with pytest.raises(TypeError):
        del snapshot.module_counts["core-coverage"]  # type: ignore[attr-defined]


def test_entry_lookup_helpers():
    snapshot = load_rule_catalog_snapshot()
    entry = snapshot.entry("CORE-COVERAGE-001")
    assert entry is not None
    assert entry.rule_id == "CORE-COVERAGE-001"
    assert snapshot.entry("NO-SUCH-RULE-999") is None

    module_entries = snapshot.entries_by_module("core-canonical")
    assert len(module_entries) == snapshot.module_counts["core-canonical"]
    assert all(entry.module == "core-canonical" for entry in module_entries)


def test_entry_source_refs_resolve_to_registry_metadata():
    snapshot = load_rule_catalog_snapshot()
    entry = snapshot.entry("CORE-COVERAGE-001")
    assert entry is not None
    assert entry.sources
    for source in entry.sources:
        assert isinstance(source, RuleCatalogSourceRef)
        assert source.title
        assert source.url.startswith(("http://", "https://"))


def test_entry_fact_requirements_reference_known_families():
    from agentready.audit_core.fact_schema import DEFAULT_FACT_SCHEMA_VERSIONS

    snapshot = load_rule_catalog_snapshot()
    for entry in snapshot.entries:
        for requirement in entry.fact_requirements:
            assert requirement.family in DEFAULT_FACT_SCHEMA_VERSIONS


def test_catalog_identity_returns_version_and_digest():
    version, digest = catalog_identity()
    assert version == "2.1.0-draft.2"
    assert isinstance(digest, str) and len(digest) == 64  # sha256 hex


def test_catalog_identity_is_not_ruleset_identity():
    version, digest = catalog_identity()
    context = AuditRunContext.create(
        target="https://example.test/",
        configuration={"mode": "seo"},
        tool_version="test",
        rule_catalog_version=version,
        rule_catalog_digest=digest,
    )
    # Built-in catalog identity populates rule_catalog_* fields only.
    assert context.rule_catalog_version == version
    assert context.rule_catalog_digest == digest
    assert context.rule_catalog_digest_kind == "content"
    # Custom ruleset identity is untouched unless explicitly supplied.
    assert context.ruleset_version is None
    assert context.ruleset_hash is None


def test_catalog_identity_and_custom_ruleset_identity_can_coexist_independently():
    version, digest = catalog_identity()
    context = AuditRunContext.create(
        target="https://example.test/",
        configuration={"mode": "seo"},
        tool_version="test",
        rule_catalog_version=version,
        rule_catalog_digest=digest,
        ruleset_version="custom-1.0.0",
        ruleset_hash="deadbeef",
    )
    assert context.rule_catalog_version == version
    assert context.rule_catalog_digest == digest
    assert context.ruleset_version == "custom-1.0.0"
    assert context.ruleset_hash == "deadbeef"
    # Built-in and custom identities must never collide/overwrite each other.
    assert context.rule_catalog_version != context.ruleset_version
    assert context.rule_catalog_digest != context.ruleset_hash


def test_load_rule_catalog_snapshot_raises_on_invalid_document(monkeypatch):
    from agentready.audit_core import rule_catalog as rule_catalog_module

    def _boom():
        raise RuleCatalogValidationError(["synthetic failure for test"])

    monkeypatch.setattr(rule_catalog_module, "load_frozen_rule_catalog", _boom)
    with pytest.raises(RuleCatalogValidationError):
        rule_catalog_module.load_rule_catalog_snapshot()


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    result: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            result.add(node.module)
    return result


def test_only_rule_catalog_module_wraps_the_low_level_catalog_loader():
    """Architecture gate for #18: exactly one authoritative runtime parse path.

    ``agentready.seo.rules.catalog.loader`` is the low-level artifact
    parser/validator; ``agentready.audit_core.rule_catalog`` is the single
    runtime-facing snapshot builder that wraps it (see #18). No other
    runtime module may import ``agentready.seo.rules.catalog`` directly and
    duplicate catalog loading/parsing logic; they must go through
    ``agentready.audit_core.rule_catalog`` instead.
    """
    allowed_paths = {
        SOURCE / "audit_core" / "rule_catalog.py",
        SOURCE / "seo" / "rules" / "catalog" / "loader.py",
        SOURCE / "seo" / "rules" / "catalog" / "__init__.py",
    }
    offenders = []
    for path in SOURCE.rglob("*.py"):
        if path in allowed_paths:
            continue
        if any(module.startswith("agentready.seo.rules.catalog") for module in _imports(path)):
            offenders.append(path.relative_to(SOURCE).as_posix())
    assert offenders == [], f"unexpected direct catalog-package import outside rule_catalog.py: {offenders}"


def test_rule_catalog_module_performs_no_network_or_transport_imports():
    path = SOURCE / "audit_core" / "rule_catalog.py"
    forbidden = {"http", "httpx", "playwright", "sqlite3", "requests"}
    assert not (_imports_top_level(path) & forbidden)


def _imports_top_level(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    result: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            result.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            result.add(node.module.split(".", 1)[0])
    return result
