"""Production page@1 fact-envelope adaptation gates (#50 P0-A).

Locks the real production adapter between collected/replayed page payloads
and the frozen-rule evaluation surface:

* :func:`agentready.audit_core.collection.page_fact_envelope` is the single
  sanctioned ``FactEnvelope`` constructor for parsed page facts;
* envelope identity is deterministic over subject URL, observed_at,
  representation id, and canonical payload;
* durable store records replay into envelopes offline via
  :func:`agentready.audit_core.collection.load_page_fact_envelopes`;
* no other production module constructs ``FactEnvelope`` directly.

Targeted exact-HEAD suite:

    python -m pytest tests/test_page_fact_adapter.py -q

"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from agentready.audit_core.collection import (
    load_page_fact_envelopes,
    page_fact_envelope,
    parsed_facts_from_dict,
)
from agentready.audit_core.contracts import FactEnvelope
from agentready.audit_core.fact_schema import DEFAULT_FACT_SCHEMA_VERSIONS
from agentready.audit_core.urls import UrlIdentity

REPO_ROOT = Path(__file__).resolve().parents[1]
SUBJECT = "https://example.com/docs/page"

FACTS_PAYLOAD = {
    "titles": ["Example Domain"],
    "descriptions": ["Example domain meta description"],
    "meta_robots": ["noindex, follow"],
    "canonicals": ["https://example.com/canonical"],
    "links": [
        {
            "source_representation_id": "static-html",
            "ordinal": 0,
            "raw_href": "/next",
            "resolved_url": "https://example.com/next",
            "rel": "next",
            "element": "a",
        }
    ],
}


def _facts():
    return parsed_facts_from_dict(FACTS_PAYLOAD)


def test_page_fact_envelope_shape_and_schema_version() -> None:
    envelope = page_fact_envelope(
        subject_url=SUBJECT, facts=_facts(), observed_at="2026-08-22T00:00:00Z"
    )
    assert isinstance(envelope, FactEnvelope)
    assert envelope.kind == "page"
    assert envelope.schema_family == "page"
    assert envelope.schema_version == DEFAULT_FACT_SCHEMA_VERSIONS["page"] == "1"
    assert isinstance(envelope.target, UrlIdentity)
    assert envelope.target.normalized() == SUBJECT
    assert envelope.value["titles"] == ("Example Domain",)
    assert envelope.value["links"][0]["rel"] == "next"


def test_envelope_identity_is_deterministic() -> None:
    kwargs = {
        "subject_url": SUBJECT,
        "facts": _facts(),
        "observed_at": "2026-08-22T00:00:00Z",
        "representation_id": "static-html",
    }
    first = page_fact_envelope(**kwargs)
    second = page_fact_envelope(**kwargs)
    assert first.id == second.id and first == second
    shifted = page_fact_envelope(**{**kwargs, "observed_at": "2026-08-23T00:00:00Z"})
    assert shifted.id != first.id
    other_representation = page_fact_envelope(**{**kwargs, "representation_id": "rendered-dom"})
    assert other_representation.id != first.id


def test_adapter_rejects_empty_inputs() -> None:
    with pytest.raises(ValueError):
        page_fact_envelope(subject_url="   ", facts=_facts(), observed_at="t")
    with pytest.raises(ValueError):
        page_fact_envelope(subject_url=SUBJECT, facts=_facts(), observed_at="")


@dataclass
class _PageRecord:
    url_key: str
    requested_url: str
    final_url: str | None = None
    depth: int = 0
    status_code: int | None = 200
    content_type: str | None = "text/html"


@dataclass
class _RunRecord:
    started_at: str = "2026-08-22T00:00:00Z"
    fact_schema_versions: tuple = field(default_factory=tuple)


@dataclass
class _RepresentationRecord:
    representation_id: str = "rep-1"
    run_id: str = "run-1"
    url_key: str = SUBJECT
    source: str = "static-html"
    content_type: str | None = "text/html"
    body_hash: str | None = None
    byte_size: int | None = None
    observed_at: str | None = "2026-08-21T23:59:59Z"
    parser_backend: str | None = None
    facts: object | None = None
    body: bytes | None = b"<html><title>Example Domain</title></html>"
    error: str | None = None


class _FakeStore:
    def __init__(self) -> None:
        self._run = _RunRecord()
        self._pages = [_PageRecord(url_key=SUBJECT, requested_url=SUBJECT)]
        self._representations = {(SUBJECT,): (_RepresentationRecord(),)}

    def get_run(self, run_id: str) -> _RunRecord:
        return self._run

    def iter_pages(self, run_id: str) -> list[_PageRecord]:
        return self._pages

    def iter_fetches(self, run_id: str) -> list:
        return []

    def iter_run_urls(self, run_id: str) -> list:
        return []

    def iter_redirects(self, run_id: str) -> list:
        return []

    def iter_representations(self, run_id: str, key: str) -> tuple[_RepresentationRecord, ...]:
        return self._representations.get((key,), ())


def test_load_page_fact_envelopes_replays_store_records_offline() -> None:
    store = _FakeStore()
    run_started_at = store.get_run("run-1").started_at
    envelopes = load_page_fact_envelopes(store, "run-1")
    assert len(envelopes) == 1
    envelope = envelopes[0]
    # Provenance comes from the persisted Representation, not from the source
    # label and not from the run's start time.
    assert envelope.representation_id == "rep-1"
    assert envelope.observed_at == store._representations[(SUBJECT,)][0].observed_at
    assert envelope.observed_at != run_started_at
    expected = page_fact_envelope(
        subject_url=SUBJECT,
        facts=parsed_facts_from_dict(dict(envelope.value)),
        observed_at=envelope.observed_at,
        representation_id="rep-1",
    )
    assert envelope == expected
    explicit = load_page_fact_envelopes(store, "run-1", observed_at="2026-01-01T00:00:00Z")
    assert explicit[0].observed_at == "2026-01-01T00:00:00Z"
    assert explicit[0].id != envelope.id


def test_envelope_identity_uses_representation_provenance_not_run_start() -> None:
    """Regression (review round 3): provenance fields must drive the id."""
    store = _FakeStore()
    by_representation = load_page_fact_envelopes(store, "run-1")[0]
    forced_run_time = load_page_fact_envelopes(store, "run-1", observed_at=store.get_run("run-1").started_at)[0]
    assert by_representation.observed_at != forced_run_time.observed_at
    assert by_representation.representation_id == "rep-1" != "static-html"
    assert by_representation.id != forced_run_time.id

    legacy_store = _FakeStore()
    legacy_store._representations[(SUBJECT,)][0].observed_at = ""
    legacy = load_page_fact_envelopes(legacy_store, "run-1")[0]
    assert legacy.observed_at == legacy_store.get_run("run-1").started_at  # documented fallback


def test_production_fact_envelope_construction_stays_in_the_sanctioned_adapter() -> None:
    """P0-A regression lock: only collection.py may construct FactEnvelope."""
    pattern = re.compile(r"FactEnvelope\s*\(")
    offenders: list[str] = []
    src_root = REPO_ROOT / "src" / "agentready"
    for path in src_root.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        rel = str(path.relative_to(REPO_ROOT))
        text = path.read_text(encoding="utf-8")
        if not pattern.search(text):
            continue
        if rel.replace("\\", "/").endswith("audit_core/collection.py"):
            continue
        offenders.append(rel)
    assert offenders == [], "FactEnvelope must be built only by the sanctioned adapter"
