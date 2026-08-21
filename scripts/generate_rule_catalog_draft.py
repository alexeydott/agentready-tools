"""One-time authoring aid for the frozen v2.1.0-draft.1 rule catalog (#17).

This script is NOT part of the runtime package and MUST NOT be invoked by
CI, the audit pipeline, or any rule loader. It exists only so the exact
generation of the checked-in catalog data file
(``src/agentready/seo/rules/catalog/agentready.rule-catalog.v2.yaml``) is
reproducible and auditable.

The catalog it produces is an internally consistent *draft engineering
candidate* built from fact families and taxonomy already present on
`master` (see ``agentready.audit_core.fact_schema.DEFAULT_FACT_SCHEMA_VERSIONS``
and ``agentready.seo.rules.builtin.SEO_RULE_GROUPS``). It intentionally
keeps the rule IDs referenced in tracking issue #1's Stage E plan
(``CORE-COVERAGE-001``, ``CORE-CANON-001``..``008``, ``GOOGLE-HREF-001``..``005``,
``GOOGLE-DESC-001``, ``GOOGLE-TITLE-001``) so those issues can bind against a
stable identity once Stage D is accepted.

Once the catalog is checked in, it is frozen: further changes to rule
content must go through explicit catalog governance (a dedicated issue and
PR), not by silently re-running this script.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CATALOG_DIR = ROOT / "src" / "agentready" / "seo" / "rules" / "catalog"
CATALOG_PATH = CATALOG_DIR / "agentready.rule-catalog.v2.yaml"

SCHEMA_ID = "agentready.rule-catalog.v2"
CATALOG_VERSION = "2.1.0-draft.1"
GENERATED_AT = "2026-08-21T00:00:00Z"

SOURCE_REGISTRY: dict[str, dict[str, str]] = {
    "google-search-central": {
        "title": "Google Search Central documentation",
        "url": "https://developers.google.com/search/docs",
    },
    "rfc9309": {
        "title": "RFC 9309 - Robots Exclusion Protocol",
        "url": "https://www.rfc-editor.org/rfc/rfc9309",
    },
    "sitemaps-org": {
        "title": "Sitemaps.org protocol",
        "url": "https://www.sitemaps.org/protocol.html",
    },
    "google-hreflang": {
        "title": "Google: Tell Google about localized versions of your page",
        "url": "https://developers.google.com/search/docs/specialty/international/localized-versions",
    },
    "google-structured-data": {
        "title": "Google structured data general guidelines",
        "url": "https://developers.google.com/search/docs/appearance/structured-data/sd-policies",
    },
    "schema-org": {
        "title": "Schema.org vocabulary",
        "url": "https://schema.org/docs/schemas.html",
    },
    "w3c-jsonld": {
        "title": "JSON-LD 1.1",
        "url": "https://www.w3.org/TR/json-ld11/",
    },
    "whatwg-html": {
        "title": "HTML Living Standard",
        "url": "https://html.spec.whatwg.org/multipage/",
    },
    "ietf-http-semantics": {
        "title": "RFC 9110 - HTTP Semantics",
        "url": "https://www.rfc-editor.org/rfc/rfc9110",
    },
    "owasp-secure-headers": {
        "title": "OWASP Secure Headers Project",
        "url": "https://owasp.org/www-project-secure-headers/",
    },
    "google-mobile-friendly": {
        "title": "Google: Mobile-friendly sites",
        "url": "https://developers.google.com/search/docs/crawling-indexing/mobile/mobile-sites",
    },
    "web-vitals": {
        "title": "web.dev: Web Vitals",
        "url": "https://web.dev/articles/vitals",
    },
    "ogp": {
        "title": "The Open Graph protocol",
        "url": "https://ogp.me/",
    },
    "indexnow": {
        "title": "IndexNow protocol documentation",
        "url": "https://www.indexnow.org/documentation",
    },
}

# module id -> (rule_id prefix, count, applies_to, candidate fact families, source ids)
MODULES: list[tuple[str, str, int, str, tuple[str, ...], tuple[str, ...]]] = [
    ("core-coverage", "CORE-COVERAGE", 20, "html-page",
     ("page", "robots.policy", "sitemap.urls", "transport"),
     ("google-search-central", "rfc9309", "sitemaps-org")),
    ("core-canonical", "CORE-CANON", 20, "html-page",
     ("page", "links", "transport"),
     ("google-search-central",)),
    ("core-links", "CORE-LINK", 20, "html-page",
     ("links", "page", "resources"),
     ("google-search-central", "whatwg-html")),
    ("google-hreflang", "GOOGLE-HREF", 10, "html-page",
     ("page", "links"),
     ("google-hreflang",)),
    ("google-metadata", "GOOGLE-META", 15, "html-page",
     ("page", "structured-data"),
     ("google-search-central", "ogp")),
    ("robots-sitemap", "ROBOTS-SITEMAP", 20, "origin",
     ("robots.fetch", "robots.parsed", "robots.policy", "sitemap.discovery", "sitemap.fetch", "sitemap.parsed", "sitemap.urls"),
     ("rfc9309", "sitemaps-org", "indexnow")),
    ("structured-data", "SDATA", 20, "html-page",
     ("structured-data", "page"),
     ("schema-org", "w3c-jsonld", "google-structured-data")),
    ("security", "SEC", 15, "html-page",
     ("transport", "page"),
     ("ietf-http-semantics", "owasp-secure-headers")),
    ("images", "IMG", 15, "html-page",
     ("resources", "page"),
     ("google-search-central", "whatwg-html")),
    ("content", "CONTENT", 15, "html-page",
     ("page", "representation"),
     ("google-search-central", "whatwg-html")),
    ("performance", "PERF", 10, "html-page",
     ("transport", "resources"),
     ("web-vitals",)),
    ("mobile", "MOBILE", 10, "html-page",
     ("representation", "page"),
     ("google-mobile-friendly",)),
    ("agent-readiness", "AGENT", 10, "origin",
     ("page", "robots.policy", "structured-data"),
     ("google-search-central", "rfc9309")),
]

# Explicit canary/named rule titles referenced by tracking issue #1's Stage E
# plan. Keyed by exact rule_id so generation stays stable if module ordering
# changes.
NAMED_TITLES: dict[str, str] = {
    "CORE-COVERAGE-001": "Page is discoverable and returns a crawlable response",
    "CORE-CANON-001": "Canonical URL is present and resolves to a single preferred URL",
    "CORE-CANON-002": "Canonical URL uses the same scheme/host as the audited origin",
    "CORE-CANON-003": "Canonical URL is not blocked by robots directives",
    "CORE-CANON-004": "Canonical URL does not point to a redirect chain",
    "CORE-CANON-005": "Self-referencing canonical matches the requested URL for paginated pages",
    "CORE-CANON-006": "Canonical URL avoids parameter-only duplicate variants",
    "CORE-CANON-007": "Cross-domain canonical targets are consistent across the crawl",
    "CORE-CANON-008": "Canonical URL is declared exactly once per page",
    "GOOGLE-HREF-001": "Hreflang annotations declare a valid language-region code",
    "GOOGLE-HREF-002": "Hreflang cluster is reciprocal across all listed URLs",
    "GOOGLE-HREF-003": "Hreflang cluster includes a self-referencing entry",
    "GOOGLE-HREF-004": "x-default hreflang entry is present for language-neutral fallback",
    "GOOGLE-HREF-005": "Hreflang target URLs are canonical and not blocked from indexing",
    "GOOGLE-DESC-001": "Meta description is present and within recommended length",
    "GOOGLE-TITLE-001": "Title tag is present and within recommended length",
}

SCORE_ROLE_CYCLE = ("scored", "scored", "scored", "diagnostic", "scored", "observation_only", "scored")
FAILURE_POLICY_BY_ROLE = {
    "scored": "block_on_missing_facts",
    "diagnostic": "unknown_on_missing_facts",
    "observation_only": "unknown_on_missing_facts",
}


def _rule_summary(module_id: str, prefix: str, index: int, title: str) -> str:
    return (
        f"{title}. Draft engineering-candidate rule in the {module_id} module of the "
        f"frozen v2.1.0-draft.1 catalog (id {prefix}-{index:03d})."
    )


# google-metadata keeps two canary rule_ids referenced by tracking issue #1's
# Stage E plan (GOOGLE-DESC-001, GOOGLE-TITLE-001) instead of the module's
# generic GOOGLE-META prefix, before falling back to GOOGLE-META-{n:03d}.
MODULE_RULE_ID_OVERRIDES: dict[str, dict[int, str]] = {
    "google-metadata": {1: "GOOGLE-DESC-001", 2: "GOOGLE-TITLE-001"},
}


def build_rules() -> list[dict[str, object]]:
    rules: list[dict[str, object]] = []
    for module_id, prefix, count, applies_to, families, source_ids in MODULES:
        overrides = MODULE_RULE_ID_OVERRIDES.get(module_id, {})
        for i in range(1, count + 1):
            rule_id = overrides.get(i, f"{prefix}-{i:03d}")
            title = NAMED_TITLES.get(
                rule_id,
                f"{module_id.replace('-', ' ').title()} check {i:03d}",
            )
            role = SCORE_ROLE_CYCLE[(i - 1) % len(SCORE_ROLE_CYCLE)]
            fact_requirements = [
                {"family": family, "min_schema_version": "1"}
                for family in families[: 1 + (i % len(families))]
            ]
            rules.append(
                {
                    "rule_id": rule_id,
                    "version": "1.0.0",
                    "title": title,
                    "module": module_id,
                    "applicability": {
                        "applies_to": applies_to,
                        "condition": f"applies whenever a {applies_to} subject was collected for the run",
                    },
                    "fact_requirements": fact_requirements,
                    "source_ids": list(source_ids),
                    "score_role": role,
                    "failure_policy": FAILURE_POLICY_BY_ROLE[role],
                    "summary": _rule_summary(module_id, prefix, i, title),
                }
            )
    return rules


def build_document() -> dict[str, object]:
    rules = build_rules()
    modules = [{"id": module_id, "count": count} for module_id, _prefix, count, *_ in MODULES]
    total = sum(module["count"] for module in modules)
    assert total == len(rules) == 200, f"expected 200 rules, built {len(rules)} (modules sum {total})"
    rule_ids = [rule["rule_id"] for rule in rules]
    assert len(rule_ids) == len(set(rule_ids)), "duplicate rule_id generated"
    return {
        "schema": SCHEMA_ID,
        "catalog_version": CATALOG_VERSION,
        "generated_at": GENERATED_AT,
        "rule_count": total,
        "modules": modules,
        "source_registry": SOURCE_REGISTRY,
        "rules": rules,
    }


def main() -> None:
    document = build_document()
    CATALOG_DIR.mkdir(parents=True, exist_ok=True)
    header = (
        "# Frozen SEO/GEO v2.1.0-draft.1 rule catalog (issue #17).\n"
        "# This file is checked-in immutable runtime package data.\n"
        "# Do not hand-edit without updating scripts/generate_rule_catalog_draft.py\n"
        "# and recording the change through explicit catalog governance.\n"
    )
    text = header + yaml.safe_dump(document, sort_keys=False, allow_unicode=True, width=100)
    CATALOG_PATH.write_text(text, encoding="utf-8", newline="\n")
    digest = hashlib.sha256(CATALOG_PATH.read_bytes()).hexdigest()
    print(f"wrote {CATALOG_PATH} ({len(document['rules'])} rules, sha256={digest})")


if __name__ == "__main__":
    main()
