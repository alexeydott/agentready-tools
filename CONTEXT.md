# Project Glossary

> Concise terminology grounded in project source and documentation.

## Language

- **Protocol readiness score** — percentage derived only from applicable deterministic core scored checks.
- **AI Search / GEO score** — separate percentage derived from applicable checks marked `geo_scored`; it does not replace the protocol readiness score.
- **Scored check** — deterministic audit criterion that participates in protocol or GEO score calculation.
- **Supplemental check** — opt-in diagnostic criterion that does not alter the core protocol score.
- **Maturity level** — sequential readiness tier from Level 0 through Level 5, calculated with the configured tier pass ratio.
- **Remediation** — implementation guidance and an optional coding-agent prompt attached to an actionable audit result.
- **Baseline** — prior JSON report used to detect check, score, or maturity regressions.
- **v2 report** — the only supported public report contract, with typed findings,
  evidence, coverage, stable identities, and bounded projections.
- **Public-target mode** — network policy that rejects targets resolving to non-public IP addresses.

## Avoid

- Avoid **overall score** when the distinction matters; use **protocol readiness score** or **AI Search / GEO score**.
- Avoid treating **citation-readiness** as a ranking factor; it is an experimental heuristic.
- Avoid describing IndexNow acceptance as indexing success; it confirms receipt only.

## Relationships

- **Protocol readiness score** depends on applicable core **scored checks**.
- **AI Search / GEO score** depends on applicable GEO **scored checks**.
- **Maturity level** depends on sequential tier requirements and the configured pass ratio.
- **Baseline** comparison can identify regressions and improvements between reports.

## Flagged Ambiguities

- **Readiness** may refer to protocol interoperability or AI Search/GEO quality; confirm which score is intended.
- **Agent** may refer to an autonomous web client, AI crawler, coding agent, or MCP client; preserve the specific context.
