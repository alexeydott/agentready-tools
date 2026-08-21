# Stage E/F catalog reconciliation (#42)

The accepted Stage D boundary is the engineering-candidate catalog at
`master@bf59144e15d5c858b5693d8b06e2891f69399fa4`. Issue #42 reconciles the
pre-existing Stage E/F plans before any frozen evaluator is bound.

## Authoritative direction

This repository uses **catalog-authoritative** reconciliation for the current
boundary. The accepted `agentready.rule-catalog.v2` artifact remains
`2.1.0-draft.1`; its identity and digest are not silently changed. The
dependent plans must be amended against the loaded catalog snapshot before
implementation.

This is deliberately the conservative direction for an engineering-candidate
catalog: no issue text can cause a missing or differently defined rule to
become executable by evaluator code.

## Matrix contract

`agentready.seo.stage_e_reconciliation` provides the deterministic
`agentready.stage-e-reconciliation.v1` matrix. Each row records:

- the dependent issue and planned rule ID;
- the planned semantic summary;
- whether the ID is present in the accepted catalog;
- catalog version, title, scope, fact requirements, rule kind, score role,
  failure policy, mechanism, and automation mode when present;
- an explicit classification:
  `MATCH`, `SEMANTIC_MISMATCH`, `MISSING_FROM_CATALOG`, or
  `PLAN_NO_LONGER_APPLICABLE`;
- a disposition that must be applied before the dependent issue starts.

The matrix is generated from the immutable loaded snapshot, so it carries the
actual catalog digest rather than a copied expectation.

## Reconciled families

| Family | Current disposition |
| --- | --- |
| Coverage canary (#22) | Existing ID is present but semantics mismatch; amend #22 before binding. |
| Robots/sitemap (#23, #29) | Planned `CORE-ROBOTS-*`/`CORE-SITEMAP-*` IDs are absent; keep blocked and select explicit catalog IDs in a follow-up plan. |
| Canonical (#24, #26) | IDs exist, but issue semantics and catalog roles/facts differ; amend plans first. |
| Duplicate content (#25) | Planned IDs are absent; no duplicate evaluator may be bound. |
| Links (#27) | IDs exist, but score/failure/fact semantics differ; amend the plan. |
| Hreflang (#28) | IDs exist, but planned numbering/meaning differs from catalog titles and facts; amend the plan. |
| Intent (#30) | No inferred `intent.indexability` fact is created; missing IDs remain blocked. |
| Description/title (#31–#33) | Existing IDs require catalog-defined roles/facts; title remains gated by `content.main`. |

## Binding gate

Issue #42 binds no evaluator. `stage_e_binding_is_blocked()` must remain true
until this reconciliation is accepted. In particular:

- no planned ID may be silently renamed to a catalog ID;
- no missing fact family may be inferred from sitemap membership, HTTP status,
  links, provider outcomes, URL shape, or AI output;
- no catalog rule may be registered as executable as a side effect of loading
  the matrix;
- current/legacy checks remain available through the typed compatibility
  crosswalk until a later golden cutover.

The global matrix remains blocked while future plans contain unresolved or
missing IDs. A future implementation may call
`stage_e_binding_is_blocked(matrix, issue=22, rule_id="CORE-COVERAGE-001")`
after that specific row has an accepted effective catalog contract; unresolved
future rows must not prevent an already-reconciled canary from proceeding.
The next phase is #22 only after this issue's exact-HEAD gate and formal review
accept the matrix and the amended dependent issue contracts.
