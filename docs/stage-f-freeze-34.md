# Stage F freeze: final #34 re-freeze

> PR #71 — branch `stage-f-freeze-34`
> master@4c13023cad872a87c415fa5854bc51a12307bb75
> catalog `2.1.0-draft.2` / digest `d596780a3753733c37164172d4f2ed8e907b89b74f599d4f0025a3144afc5e6f`
> semantics `1.0.4` / digest `4c678b79dbdefe02f89423d6bc7e670f7d84bb3be736a808cf34572fd880f214`

## Scope

Final Stage F governance freeze for issue #34. This completes the entire
Stage E/F reconciliation cycle by incorporating all retired and
intentionally-unbound rule sets into the frozen baseline.

## Frozen sets

### Bound rules (evaluator registry)

| Evaluator | Rules |
|-----------|-------|
| CANARY | CORE-COVERAGE-001 |
| CANON | CORE-CANON-001..008 |
| LINK_BOUND | CORE-LINK-001..006 |
| GOOGLE_DESC | GOOGLE-DESC-001 |
| GOOGLE_HREF | GOOGLE-HREF-001, 003, 004 |
| GOOGLE_TITLE | GOOGLE-TITLE-001 |

### Deferred (declared not produced)

| Rule ID | Reason |
|---------|--------|
| GOOGLE-HREF-002 | Reciprocity requires cross-page cluster facts |
| GOOGLE-HREF-005 | Target URL canonical/indexability requires target page facts |

### Retired (issues #23, #25, #29)

| Issue | Rules | Disposition |
|-------|-------|-------------|
| #23 | CORE-ROBOTS-001, 002; CORE-SITEMAP-001..004, 005, 008; CORE-ROBOTS-003, 004 | Retired — catalog has ungoverned ROBOTS-SITEMAP-* rules |
| #25 | CORE-DUP-001, 002 | Retired — duplicate detection is legacy functionality |
| #29 | CORE-ROBOTS-003, 004; CORE-SITEMAP-005..008 | Retired — follows #23 governance |

**Counting semantics:** 18 issue-scoped retirement entries, 14 unique retired rule IDs
(4 IDs shared between #23 and #29: CORE-ROBOTS-003, CORE-ROBOTS-004,
CORE-SITEMAP-005, CORE-SITEMAP-008).

### Intentionally unbound (issue #30)

| Issue | Rules | Disposition |
|-------|-------|-------------|
| #30 | CORE-HTTP-002; CORE-ROBOTS-003; GOOGLE-IDX-001, 002; YANDEX-IDX-001, 002 | Intentionally unbound — intent.indexability out of scope for v0.14.0 |

## Binding gate

`stage_e_binding_is_blocked()` remains `True` for:
- RETIRED rows (resolution_status=retired)
- INTENTIONALLY_UNBOUND rows (resolution_status=intentionally_unbound)
- SEMANTIC_MISMATCH rows (resolution_status≠resolved_catalog_authoritative)

Only rows with `resolution_status=resolved_catalog_authoritative` are bindable.

## Drift gates

The following are frozen and any drift requires explicit re-freeze:
- Catalog version, digest, rule count
- Semantics artifact version, digest
- Evaluator registry targets per evaluator
- Score model ID (`readiness-transparent-v2`)
- Deferred set (GOOGLE-HREF-002, GOOGLE-HREF-005)
- Retired set (20 rule IDs across issues #23, #25, #29)
- Intentionally-unbound set (6 rule IDs from issue #30)

## Acceptance

- [x] All 14 drift gate tests pass
- [x] RETIRED rows have resolution_status=retired
- [x] INTENTIONALLY_UNBOUND rows have resolution_status=intentionally_unbound
- [x] Retired rows remain blocked when binding_allowed=True
- [x] Unbound rows remain blocked when binding_allowed=True
- [x] No bound rules overlap with retired/unbound sets
- [x] All plan references have dispositions and terminal classifications
- [x] verify-local: exit=0, dirty=false
