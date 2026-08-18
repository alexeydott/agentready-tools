# Semantic similarity decision — 2026-08-18

## Decision

**Deferred.** Task 33 does not add an embedding model, vector store, optional
dependency, adapter, endpoint, schema, or new readiness-score input. The
existing deterministic `content-v1` exact/near-duplicate signatures remain the
canonical duplicate analysis surface.

## Gate review

| Gate | Finding | Decision impact |
| --- | --- | --- |
| Approved use case | No concrete customer workflow has demonstrated a false-negative or false-positive that the current duplicate clusters cannot address. | Fail — no measurable problem to solve. |
| Model and license | No model, version, license, distribution source, or upgrade policy is approved for this product. | Fail — cannot publish a reproducible artifact contract. |
| Offline/privacy behavior | No approved model has a documented no-download, local-only execution and retention behavior for page content. | Fail — content could leave the collection boundary. |
| Determinism and version drift | No embedding/vector version, threshold calibration set, or replay fixtures are recorded. | Fail — results would drift without an explainable migration. |
| Resource budget | No CPU/RAM/storage budget or scale target has been authorized for 1k/10k/100k page runs. | Fail — existing bounded duplicate gates are the safe baseline. |
| Measured advantage | There is no labeled fixture set or benchmark showing material advantage over `content-v1` exact/SimHash clustering. | Fail — additional complexity is not justified. |

## Current safe baseline

`src/agentready/duplicates.py` provides bounded exact and near-duplicate
clusters, stable fingerprints, candidate-comparison limits, and no implicit
model downloads. It remains separate from readiness scoring and is exposed
through the existing v2 report/API/CLI/dashboard surfaces.

## Re-open criteria

Reconsider only with an approved use case and labeled fixture corpus, a pinned
model/license and artifact provenance, an offline/no-download guarantee, a
deterministic version and threshold migration policy, explicit CPU/RAM/storage
caps, and a benchmark demonstrating a material advantage over `content-v1`.
Any future implementation must remain optional, bounded, privacy-preserving,
and separate from the core readiness score; logs may contain only model/version,
vector counts, thresholds, and hashes—not page text or vectors.
