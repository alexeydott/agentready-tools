"""Gates for transport@1 and run-projection@1 fact adapters (#56, #57).

* ``transport_fact_envelope`` / ``load_transport_fact_envelopes`` produce the
  governed transport family (origin, final_url, persisted redirect chain)
  with representation-true provenance;
* ``run_projection_fact_envelope`` / ``canonical_projection_fact_envelopes``
  project the run-scoped canonical duplicate variants and off-origin
  canonical target inventory as a pure function of replayed pages.

Targeted exact-HEAD suite:

    python -m pytest tests/test_transport_projection_adapters.py -q

"""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from agentready.audit_core.collection import (
    canonical_projection_fact_envelopes,
    load_transport_fact_envelopes,
    transport_fact_envelope,
)
from agentready.audit_core.contracts import FactEnvelope
from agentready.audit_core.fact_schema import DEFAULT_FACT_SCHEMA_VERSIONS
from agentready.audit_core.urls import UrlIdentity

SUBJECT = "https://example.com/a"
FINAL = "https://example.com/final"


def test_transport_family_is_registered() -> None:
    assert DEFAULT_FACT_SCHEMA_VERSIONS["transport"] == "1"
    assert DEFAULT_FACT_SCHEMA_VERSIONS["run-projection"] == "1"


def test_transport_envelope_shape_and_provenance() -> None:
    envelope = transport_fact_envelope(
        subject_url=SUBJECT,
        final_url=FINAL,
        redirect_chain=(FINAL,),
        observed_at="2026-08-22T10:00:00Z",
        representation_id="rep-t",
    )
    assert isinstance(envelope, FactEnvelope)
    assert envelope.kind == "transport"
    assert envelope.schema_family == "transport"
    assert envelope.schema_version == "1"
    assert envelope.representation_id == "rep-t"
    identity = UrlIdentity.parse(SUBJECT)
    assert envelope.value["origin"] == identity.origin.to_string()
    assert envelope.value["final_url"] == FINAL
    assert list(envelope.value["redirect_chain"]) == [FINAL]


def test_transport_rejects_empty_timestamp() -> None:
    with pytest.raises(ValueError):
        transport_fact_envelope(
            subject_url=SUBJECT, final_url=None, observed_at="   "
        )


@dataclass
class _PageRecord:
    url_key: str
    requested_url: str
    final_url: str | None = None
    depth: int = 0
    status_code: int | None = 200


@dataclass
class _RunRecord:
    started_at: str = "2026-08-22T00:00:00Z"
    fact_schema_versions: tuple = field(default_factory=tuple)


@dataclass
class _RepresentationRecord:
    representation_id: str = "rep-x"
    run_id: str = "run-p"
    url_key: str = ""
    source: str = "static-html"
    content_type: str | None = "text/html"
    body_hash: str | None = None
    byte_size: int | None = None
    observed_at: str = "2026-08-22T09:00:00Z"
    parser_backend: str | None = None
    facts: object | None = None
    body: bytes | None = b"<html></html>"
    error: str | None = None


@dataclass
class _RedirectRecord:
    from_url: str = SUBJECT
    to_url: str | None = FINAL
    status_code: int = 301
    location_raw: str = FINAL
    request_url: str = SUBJECT
    hop_index: int = 0


class _FakeStore:
    def __init__(self, pages, representations_by_key, redirects=()):
        self._pages = pages
        self._reps = representations_by_key
        self._redirects = redirects

    def get_run(self, run_id):
        return _RunRecord()

    def iter_pages(self, run_id):
        return self._pages

    def iter_fetches(self, run_id):
        return []

    def iter_run_urls(self, run_id):
        return []

    def iter_redirects(self, run_id):
        return self._redirects

    def iter_representations(self, run_id, key):
        return self._reps.get((key,), ())


def _store_for(urls_and_bodies, redirects=(), final_urls=None):
    pages = []
    reps = {}
    for url, body in urls_and_bodies:
        page = _PageRecord(
            url_key=url,
            requested_url=url,
            final_url=(final_urls or {}).get(url),
        )
        pages.append(page)
        reps[(url,)] = (_RepresentationRecord(url_key=url, body=body),)
    return _FakeStore(pages, reps, redirects)


def test_load_transport_envelopes_from_replayed_redirects() -> None:
    store = _store_for(
        [(SUBJECT, b"<html><title>t</title></html>")],
        redirects=[_RedirectRecord()],
        final_urls={SUBJECT: FINAL},
    )
    envelopes = load_transport_fact_envelopes(store, "run-p")
    assert len(envelopes) == 1
    env = envelopes[0]
    assert env.schema_family == "transport"
    assert env.representation_id == "rep-x"
    assert env.observed_at == "2026-08-22T09:00:00Z"  # representation provenance wins over run start
    assert list(env.value["redirect_chain"]) == [FINAL]
    assert env.value["final_url"] == FINAL


def _html(canonical: str) -> bytes:
    return (
        b"<html><head><link rel='canonical' href='" + canonical.encode() + b"'/>"
        b"<title>t</title></head><body>text</body></html>"
    )


def test_canonical_projection_variants_and_cross_domain_targets() -> None:
    store = _store_for(
        [
            ("https://example.com/a?q=1", _html("https://example.com/a")),
            ("https://example.com/a?q=2", _html("https://example.com/a")),
            ("https://example.com/b", _html("https://other.example.org/b")),
        ]
    )
    envelopes = canonical_projection_fact_envelopes(store, "run-p")
    assert len(envelopes) == 1
    value = envelopes[0].value
    assert set(value["parameter_variants"]) == {
        "https://example.com/a?q=1",
        "https://example.com/a?q=2",
    }
    assert set(value["cross_domain_targets"]) == {"https://other.example.org/b"}
    assert UrlIdentity.parse(envelopes[0].target.normalized()).host == "example.com"
    assert envelopes[0].schema_family == "run-projection"
    assert envelopes[0].schema_version == "1"


def test_projection_is_deterministic_per_run() -> None:
    store = _store_for(
        [
            ("https://example.com/a?q=1", _html("https://example.com/a")),
            ("https://example.com/a?q=2", _html("https://example.com/a")),
        ]
    )
    first = canonical_projection_fact_envelopes(store, "run-p")
    second = canonical_projection_fact_envelopes(store, "run-p")
    assert first == second
