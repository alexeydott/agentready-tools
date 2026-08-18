# Client and agency report formats decision — 2026-08-18

## Decision

**Deferred for new formats.** The current canonical HTML/JSON/JSONL/CSV/Markdown
exports remain supported. Task 35 adds no PDF/XLSX writer, rendering engine,
dependency, schema, or alternate report contract.

## Gate review

| Gate | Finding | Decision impact |
| --- | --- | --- |
| Demand | No approved customer/agency demand or format acceptance criteria for PDF or XLSX is recorded. | Fail — no format scope to implement. |
| Canonical parity | Existing exports consume typed QueryService/report projections; the dashboard uses the same bounded inventory contract. | Pass for current formats; preserve as the source of truth. |
| Large reports | Current exports enforce a 100,000-row bound and dashboard inventory keeps only the current page in the DOM. | Pass for current formats; no alternate pagination path needed. |
| Provenance and secrets | Current v2 reports carry coverage/provenance and export rows are factual projections; no secret-bearing fields are intentionally added. | Pass for current formats. |
| Optional dependencies | PDF would require a renderer and visual regression strategy; XLSX would require a writer, formula-injection policy, and multi-sheet memory tests. No clean-install/bundle strategy is approved. | Fail — adding writers would create unbounded packaging and security scope. |
| Localization and visual evidence | No approved EN/RU visual sample set or print/layout acceptance baseline exists for a new format. | Fail — output parity could not be verified. |

The existing XLSX decision remains in force: no XLSX writer or formula-bearing
workbook is accepted by the current contract. HTML/JSON remain canonical for
client and agency handoff.

## Re-open criteria

Reconsider only after a written demand decision selects a format and audience,
defines parity against canonical JSON/dashboard projections, specifies bounded
pagination and provenance/coverage fields, approves an optional dependency and
license/bundle strategy, and supplies EN/RU visual samples, large-report,
clean-install, and secret/formula-injection tests. Any future format must be a
projection of the existing report/query facts, not a second data model.
