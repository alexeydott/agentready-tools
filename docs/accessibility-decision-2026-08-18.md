# Browser accessibility decision — 2026-08-18

## Decision

**Deferred.** Task 34 does not add an accessibility engine, optional dependency,
browser protocol adapter, endpoint, schema, or second navigation path.

## Gate review

| Gate | Finding | Decision impact |
| --- | --- | --- |
| Optional dependency | Playwright is already an optional browser collector, but no accessibility ruleset/engine is approved for this product. | Fail — no ruleset to bundle or version. |
| Bundle and license | No selected engine, license notice, browser-binary strategy, or clean-install artifact contract is recorded. | Fail — packaging cannot be released safely. |
| Shared browser facts | `BrowserPool` enforces collection and egress, while `interaction.py` evaluates supplied semantic trees offline. A canonical persisted accessibility snapshot contract is not approved. | Fail — adding a second navigation or an ad-hoc snapshot store would violate the boundary. |
| Test evidence | No approved fixture matrix exists for keyboard/focus flows, localization, CSP failures, or scale caps for a chosen ruleset. | Fail — no trustworthy acceptance gate. |
| Product scope | Existing dashboard/report accessibility foundations and offline interaction findings cover current bounded scope; no additional demand is recorded. | Fail — no justified expansion. |

## Current safe baseline

Keep `BrowserPool` as the single optional rendered-collection boundary and
`interaction.py` as the dependency-free semantic interaction evaluator. These
surfaces do not claim full WCAG conformance and do not perform a second
navigation.

## Re-open criteria

Reconsider only with an approved ruleset and license, browser-binary and
optional-install strategy, snapshot schema/provenance, shared-fact ownership,
and bounded fixture coverage for keyboard/focus, localization, CSP/failure,
and scale behavior. A future implementation must reuse one BrowserPool run,
map results to canonical findings/evidence, avoid raw page-content logging, and
remain optional and separate from unapproved scoring changes.
