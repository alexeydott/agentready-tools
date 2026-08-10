"""Passive protocol document auditing.

Documents are supplied by an already-authorized caller. This module performs
no network, authentication, mutation, publishing, or commerce operation.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

from .manifest import PROTOCOL_MANIFEST, ProtocolProfile
from .models import ProtocolEvidence, ProtocolFinding, ProtocolStatus

logger = logging.getLogger(__name__)


def _profile(profile_id: str, version: str | None) -> ProtocolProfile | None:
    matches = [item for item in PROTOCOL_MANIFEST if item.id == profile_id]
    if version is not None:
        matches = [item for item in matches if item.version == version]
    return matches[0] if matches else None


def audit_documents(
    documents: Mapping[str, Mapping[str, Any] | None],
    *,
    source_prefix: str = "protocol",
) -> tuple[ProtocolFinding, ...]:
    """Audit supplied protocol documents without performing I/O.

    Keys are ``profile_id`` or ``profile_id@version``. A missing document is
    represented as ``unavailable`` rather than a technical protocol failure.
    """
    findings: list[ProtocolFinding] = []
    for key, document in sorted(documents.items()):
        profile_id, separator, version = key.partition("@")
        profile = _profile(profile_id, version if separator else None)
        if profile is None:
            logger.debug("Ignoring unknown protocol profile key=%s", key)
            continue
        source_id = f"{source_prefix}:{profile.source_id}"
        if document is None:
            findings.append(
                ProtocolFinding(
                    profile.id,
                    profile.version,
                    ProtocolStatus.UNAVAILABLE,
                    profile.title,
                    "No authorized document was supplied for passive evaluation.",
                    (ProtocolEvidence(source_id, "$", "Document unavailable"),),
                    profile.deprecated,
                )
            )
            continue
        missing = tuple(
            requirement for requirement in profile.requirements if requirement not in document
        )
        status = ProtocolStatus.FAIL if missing else ProtocolStatus.PASS
        reason = (
            f"Missing required fields: {', '.join(missing)}."
            if missing
            else "Required profile fields are present."
        )
        findings.append(
            ProtocolFinding(
                profile.id,
                profile.version,
                status,
                profile.title,
                reason,
                (
                    ProtocolEvidence(
                        source_id,
                        "$",
                        "Supplied protocol document evaluated passively.",
                        anchor=f"{profile.source_id}#{profile.version}",
                    ),
                ),
                profile.deprecated,
            )
        )
    return tuple(findings)
