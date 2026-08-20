from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).parents[1]
SOURCE = ROOT / "src" / "agentready"


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    result: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            result.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            result.add(node.module.split(".", 1)[0])
    return result


def _imported_symbols(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    symbols: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            symbols.update(alias.name for alias in node.names)
    return symbols


def test_sqlite_transport_is_owned_only_by_the_store():
    offenders = []
    for path in SOURCE.rglob("*.py"):
        if path.name == "store.py" and path.parent.name == "audit_core":
            continue
        if "sqlite3" in _imports(path):
            offenders.append(path.relative_to(SOURCE).as_posix())
    assert offenders == []


def test_pure_rules_and_inventory_algorithms_have_no_network_or_transport_imports():
    pure_paths = [
        *((SOURCE / "seo" / "rules").glob("*.py")),
        SOURCE / "custom_rules.py",
        SOURCE / "duplicates.py",
        SOURCE / "link_graph.py",
        SOURCE / "robots.py",
        SOURCE / "sitemap_reconciliation.py",
        SOURCE / "interaction.py",
        SOURCE / "crawler_identity.py",
    ]
    forbidden = {"http", "httpx", "playwright", "sqlite3", "cli", "server", "mcp_server"}
    offenders = {
        path.relative_to(SOURCE).as_posix(): sorted(_imports(path) & forbidden)
        for path in pure_paths
        if _imports(path) & forbidden
    }
    assert offenders == {}


COLLECTION_MIGRATION_ALLOWLIST = {
    ("checks.py", "HttpClient"),
    ("scanner.py", "HttpClient"),
    ("scanner.py", "CollectedHttpClient"),
    ("seo_checks.py", "HttpClient"),
    ("seo_crawler.py", "HttpClient"),
    ("seo_crawler.py", "BrowserPool"),
    ("seo/engine.py", "HttpClient"),
    ("seo/evidence.py", "HttpClient"),
    ("mobile_checks.py", "HttpClient"),
    ("discovery.py", "FetcherBoundary"),
    ("discovery.py", "FetchTransport"),
    ("discovery.py", "AsyncCrawler"),
}

COLLECTION_MIGRATION_METADATA = {
    key: {
        "rationale": (
            "Legacy compatibility adapter retained for the v1 CLI/check APIs; the public v2 "
            "AuditService path owns collection. Revalidate before the next collection migration wave."
        ),
        # Task 12 is complete. Keep the exception explicit and time-bounded rather
        # than silently treating the old adapters as canonical architecture.
        "expiry_task": "Task 40",
    }
    for key in COLLECTION_MIGRATION_ALLOWLIST
}


def test_collection_migration_allowlist_is_symbol_scoped_with_rationale_and_expiry():
    assert all(isinstance(key, tuple) and len(key) == 2 for key in COLLECTION_MIGRATION_ALLOWLIST)
    assert all("*" not in key[0] and "*" not in key[1] for key in COLLECTION_MIGRATION_ALLOWLIST)
    for relative, symbol in COLLECTION_MIGRATION_ALLOWLIST:
        assert (SOURCE / relative).is_file(), relative
        metadata = COLLECTION_MIGRATION_METADATA[(relative, symbol)]
        assert metadata["rationale"].strip(), (relative, symbol)
        assert re.fullmatch(r"Task \d+", metadata["expiry_task"]), (relative, symbol)


def test_transport_imports_are_declared_or_owned_by_canonical_boundaries():
    owners = {
        "audit_service.py",
        "browser_pool.py",
        "crawler.py",
        "fetcher.py",
        "http.py",
        "google_indexing.py",
        "indexnow.py",
        "seo_analytics.py",
    }
    transport_symbols = {"HttpClient", "CollectedHttpClient", "BrowserPool", "Fetcher", "AsyncCrawler", "httpx"}
    offenders = []
    for path in SOURCE.rglob("*.py"):
        relative = path.relative_to(SOURCE).as_posix()
        imported = _imported_symbols(path) & transport_symbols
        if not imported or relative in owners:
            continue
        for symbol in imported:
            if (relative, symbol) not in COLLECTION_MIGRATION_ALLOWLIST:
                offenders.append((relative, symbol))
    assert offenders == []


def test_transport_constructors_are_not_reintroduced_into_analyzers():
    owners = {
        "audit_service.py",
        "browser_pool.py",
        "crawler.py",
        "fetcher.py",
        "http.py",
        "google_indexing.py",
        "indexnow.py",
        "seo_analytics.py",
        "discovery.py",
        "scanner.py",
        "seo_crawler.py",
    }
    constructors = {"HttpClient", "CollectedHttpClient", "BrowserPool", "Fetcher", "AsyncCrawler", "Client", "AsyncClient"}
    offenders = []
    for path in SOURCE.rglob("*.py"):
        relative = path.relative_to(SOURCE).as_posix()
        if relative in owners:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                name = node.func.id if isinstance(node.func, ast.Name) else node.func.attr if isinstance(node.func, ast.Attribute) else None
                if name in constructors:
                    offenders.append((relative, name))
    assert offenders == []


def test_dashboard_has_no_direct_store_or_sqlite_access():
    dashboard = SOURCE / "dashboard.py"
    assert not (_imports(dashboard) & {"sqlite3", "store"})
    assert not re.search(r"(?:SiteStore|MemorySiteStore|SQLiteSiteStore)\s*\(", dashboard.read_text(encoding="utf-8"))


def test_generic_finding_and_storage_implementations_have_single_owners():
    generic_finding_owners = {"audit_core/contracts.py", "report_v2.py"}
    storage_owners = {"audit_core/store.py"}
    crawler_owners = {"crawler.py"}
    finding_offenders = []
    storage_offenders = []
    crawler_offenders = []
    for path in SOURCE.rglob("*.py"):
        relative = path.relative_to(SOURCE).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                if node.name in {"Finding", "FindingContract"} and relative not in generic_finding_owners:
                    finding_offenders.append((relative, node.name))
                if node.name in {"SiteStore", "MemorySiteStore", "SQLiteSiteStore"} and relative not in storage_owners:
                    storage_offenders.append((relative, node.name))
                if node.name == "AsyncCrawler" and relative not in crawler_owners:
                    crawler_offenders.append((relative, node.name))
    assert finding_offenders == []
    assert storage_offenders == []
    assert crawler_offenders == []


def test_legacy_collection_adapters_declare_their_owner_and_are_not_transport_layers():
    assert "AuditService" in (SOURCE / "scanner.py").read_text(encoding="utf-8")
    assert "AuditService" in (SOURCE / "seo_crawler.py").read_text(encoding="utf-8")
    mobile_source = (SOURCE / "mobile_scanner.py").read_text(encoding="utf-8")
    assert "AuditService" in mobile_source
    assert "HttpClient" not in mobile_source
    assert "BrowserPool(" not in mobile_source
