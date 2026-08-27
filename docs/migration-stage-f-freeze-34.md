# Migration note: Stage F freeze #34

> Applies to: consumers upgrading from pre-freeze to post-freeze boundary
> Baseline: `docs/baseline-after-e-wave.json` (post Stage F)
> Catalog: `2.1.0-draft.2` / Semantics: `1.0.4`

## Summary

The Stage F freeze finalizes all governance dispositions for issue #34.
All planned rule IDs now have explicit reviewed outcomes: bound, deferred,
retired, or intentionally unbound.

## Breaking changes

**None.** This is a governance freeze, not a runtime behavior change.
All bound evaluators, their targets, contracts, and score roles remain
identical to the pre-freeze state.

## What changed

### Frozen baseline
The baseline artifact now includes:
- `frozen_retired`: 18 issue-scoped retirement entries covering 14 unique rule IDs retired from v0.14.0 scope (4 IDs shared between #23 and #29)
- `frozen_intentionally_unbound`: 6 rule IDs kept unbound by governance decision

### Retired rules (no action required)
These rules were never bound and remain unbound:
- `CORE-ROBOTS-001..004` — robots state/policy rules
- `CORE-SITEMAP-001..008` — sitemap state/validity rules
- `CORE-DUP-001..002` — duplicate detection rules

These are legacy/current functionality not governed by the frozen catalog.
No evaluator was created for them.

### Intentionally unbound rules (no action required)
These rules are intentionally unbound for v0.14.0:
- `CORE-HTTP-002` — HTTP-level intent.indexability
- `CORE-ROBOTS-003` — robots policy consistent with intent
- `GOOGLE-IDX-001..002` — Google Indexing API rules
- `YANDEX-IDX-001..002` — Yandex Indexing API rules

Intent.indexability is out of scope for this release.

### Deferred rules (unchanged)
- `GOOGLE-HREF-002` — reciprocity requires cross-page facts
- `GOOGLE-HREF-005` — target URL requires target page facts

## Consumer guidance

1. **No code changes required.** The freeze is a governance checkpoint.
2. **Baseline consumers** should update to the new baseline JSON which
   includes the retired/unbound sets.
3. **Rule ID references** to retired/unbound IDs should be treated as
   "not applicable" rather than "missing" or "failed".
4. **Future work** for robots/sitemap/duplicate rules requires new catalog
   entries in a separate governance cycle.

## Rollback

Not applicable. This is a one-way governance freeze. If re-opening is
needed, a new governance issue must be filed.
