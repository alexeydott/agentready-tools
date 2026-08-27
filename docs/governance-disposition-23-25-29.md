# Governance Disposition: #23 / #25 / #29

> PR-only master. No automated attribution/signature trailers.
> master@c5720bdd — catalog `2.1.0-draft.2` / digest `d596780a…`

## Scope

Final governance dispositions for all planned rule IDs absent from the accepted
catalog.  After this PR merges, every blocked ID has an explicit reviewed
outcome and the reconciliation artifact is consistent.

---

## #23 — Robots/Sitemap planned IDs

| Planned ID | Planned semantics | Catalog candidate | Disposition | Rationale |
|---|---|---|---|---|
| CORE-ROBOTS-001 | robots.txt fetch state is known | ROBOTS-SITEMAP-001 (robots.fetch, robots.parsed) | **RETIRE** | Catalog has 20 `ROBOTS-SITEMAP-*` rules covering the same fact families, but none are governed in semantics v1.0.4.  The planned `CORE-ROBOTS-*` IDs were never mapped to the catalog scheme.  Adding them now would require a new catalog revision + evaluator + golden work during final cutover. |
| CORE-ROBOTS-002 | robots.txt parsed under explicit REP profile | ROBOTS-SITEMAP-002 (+ robots.policy) | **RETIRE** | Same rationale — catalog rule exists but is ungoverned.  No runtime evaluator binds it. |
| CORE-ROBOTS-003 | robots policy consistent with intent.indexability | No exact equivalent | **RETIRE** | Semantic intent-matching rule; no catalog entry, no evaluator, no fact family. |
| CORE-ROBOTS-004 | robots blocking does not hide a noindex directive | No exact equivalent | **RETIRE** | Cross-check between robots policy and meta robots; no catalog binding. |
| CORE-SITEMAP-001 | sitemap discovery state is known | ROBOTS-SITEMAP-003 (+ sitemap.discovery) | **RETIRE** | Catalog rule exists but ungoverned. |
| CORE-SITEMAP-002 | sitemap fetch state is known | ROBOTS-SITEMAP-004 (+ sitemap.fetch) | **RETIRE** | Catalog rule exists but ungoverned. |
| CORE-SITEMAP-003 | sitemap parse state is known | ROBOTS-SITEMAP-005 (+ sitemap.parsed) | **RETIRE** | Catalog rule exists but ungoverned. |
| CORE-SITEMAP-004 | sitemap URLs are absolute and valid | No exact equivalent | **RETIRE** | URL validation rule; no catalog entry. |
| CORE-SITEMAP-005 | sitemap contains preferred/canonical URLs | No exact equivalent | **RETIRE** | Cross-reference between sitemap and canonical; no catalog binding. |
| CORE-SITEMAP-008 | sitemap preferred URLs not marked noindex | No exact equivalent | **RETIRE** | Cross-reference between sitemap and robots; no catalog binding. |

**Summary for #23:** All 10 planned IDs → RETIRE. The catalog contains 20
structurally-generated `ROBOTS-SITEMAP-*` rules covering the same fact families,
but zero have accepted semantics or runtime evaluators.  Adding governed
robots/sitemap rules is future work beyond v0.14.0.

---

## #25 — Duplicate detection planned IDs

| Planned ID | Planned semantics | Catalog candidate | Disposition | Rationale |
|---|---|---|---|---|
| CORE-DUP-001 | exact duplicate clusters via content.hash + canonical | None | **RETIRE** | Duplicate detection is legacy/current functionality; not a governed frozen rule.  Adding would require new catalog revision + evaluator + golden work. |
| CORE-DUP-002 | near-duplicate similarity as observation-only | None | **RETIRE** | Same rationale.  Similarity thresholds are configuration metadata, not ranking claims. |

**Summary for #25:** Both IDs → RETIRE from v0.14.0.  Duplicate analysis
remains available as legacy functionality; no frozen evaluator identity is
created.

---

## #29 — Dependent robots/sitemap consistency IDs

| Planned ID | Planned semantics | Catalog candidate | Disposition | Rationale |
|---|---|---|---|---|
| CORE-ROBOTS-003 | robots policy consistent with intent.indexability | — | **RETIRE** | Follows #23 dispositions.  No catalog binding. |
| CORE-ROBOTS-004 | robots blocking does not hide a noindex directive | — | **RETIRE** | Follows #23 dispositions.  No catalog binding. |
| CORE-SITEMAP-005 | sitemap contains preferred/canonical URLs | — | **RETIRE** | Follows #23 dispositions.  No catalog binding. |
| CORE-SITEMAP-006 | sitemap URLs are not redirect URLs | — | **RETIRE** | No catalog entry.  Redirect verification is a crawl-level concern. |
| CORE-SITEMAP-007 | sitemap URLs do not return 4xx/5xx | — | **RETIRE** | No catalog entry.  HTTP status verification is a crawl-level concern. |
| CORE-SITEMAP-008 | sitemap preferred URLs not marked noindex | — | **RETIRE** | Follows #23 dispositions.  No catalog binding. |

**Summary for #29:** All 6 IDs → RETIRE.  Dependent on #23 governance;
all follow the same retirement path.

---

## Acceptance criteria

- [x] Every planned ID has exactly one explicit reviewed disposition (RETIRE)
- [x] No silent ID renaming or semantic aliasing
- [x] No catalog revision required (all retired)
- [x] Reconciliation/crosswalk artifacts updated to reflect dispositions
- [x] No evaluator implementation needed

## Closure

After merge:
- Close #23 (all 10 IDs retired)
- Close #25 (both IDs retired)
- Close #29 (all 6 IDs retired)

New implementation for retired rules is not planned for v0.14.0.  If robots/sitemap governed rules are needed later, they should be proposed as new catalog entries in a separate cycle.
