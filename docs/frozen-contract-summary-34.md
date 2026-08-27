# Frozen contract summary: #34

> Baseline: `docs/baseline-after-e-wave.json`
> Master: `4c13023cad872a87c415fa5854bc51a12307bb75`
> Generated: `2026-08-27T02:38:08Z`

## Artifacts

| Artifact | Version | Digest |
|----------|---------|--------|
| `agentready.rule-catalog.v2` | 2.1.0-draft.2 | `d596780a3753733c37164172d4f2ed8e907b89b74f599d4f0025a3144afc5e6f` |
| `agentready.rule-semantics.v2` | 1.0.4 | `4c678b79dbdefe02f89423d6bc7e670f7d84bb3be736a808cf34572fd880f214` |
| Score model | readiness-transparent-v2 | — |

## Rule ID inventory

| Category | Count | IDs |
|----------|-------|-----|
| Bound (evaluator) | 20 | CORE-CANON-001..008, CORE-COVERAGE-001, CORE-LINK-001..006, GOOGLE-DESC-001, GOOGLE-HREF-001,003,004, GOOGLE-TITLE-001 |
| Deferred | 2 | GOOGLE-HREF-002, GOOGLE-HREF-005 |
| Retired | 20 | CORE-ROBOTS-001..004, CORE-SITEMAP-001..008, CORE-DUP-001..002 |
| Intentionally unbound | 6 | CORE-HTTP-002, CORE-ROBOTS-003, GOOGLE-IDX-001..002, YANDEX-IDX-001..002 |
| **Total governed** | **48** | |

## Classification matrix

| Classification | Resolution status | Bindable |
|----------------|-------------------|----------|
| MATCH | resolved_catalog_authoritative | Yes |
| SEMANTIC_MISMATCH | pending | No |
| RETIRED | retired | No |
| INTENTIONALLY_UNBOUND | intentionally_unbound | No |
| UNBLOCKED | — | Yes (after re-freeze) |

## Binding gate rules

1. `stage_e_binding_is_blocked()` returns `True` for all rows except
   those with `resolution_status=resolved_catalog_authoritative`.
2. RETIRED rows remain blocked even when `binding_allowed=True`.
3. INTENTIONALLY_UNBOUND rows remain blocked even when `binding_allowed=True`.
4. No bound rule ID appears in the retired or unbound sets.

## Drift gates

Any change to the following requires explicit governance re-freeze:
- Catalog version, digest, or rule count
- Semantics artifact version or digest
- Evaluator registry targets
- Score model ID
- Deferred set membership
- Retired set membership
- Intentionally-unbound set membership
