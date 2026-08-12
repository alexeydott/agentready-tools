"""Deterministic contracts shared by versioned protocol auditors."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class ProtocolStatus(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    WARN = "warn"
    UNAVAILABLE = "unavailable"
    NOT_EVALUATED = "not_evaluated"


@dataclass(frozen=True)
class ProtocolEvidence:
    source_id: str
    locator: str
    summary: str
    url: str | None = None
    anchor: str | None = None

    def to_dict(self) -> dict[str, str]:
        result = {
            "source_id": self.source_id,
            "locator": self.locator,
            "summary": self.summary,
        }
        if self.url is not None:
            result["url"] = self.url
        if self.anchor is not None:
            result["anchor"] = self.anchor
        return result


@dataclass(frozen=True)
class ProtocolFinding:
    profile_id: str
    version: str
    status: ProtocolStatus
    title: str
    reason: str
    evidence: tuple[ProtocolEvidence, ...] = ()
    deprecated: bool = False

    @property
    def fingerprint(self) -> str:
        payload = {
            "profile_id": self.profile_id,
            "version": self.version,
            "status": self.status.value,
            "reason": self.reason,
            "evidence": [item.to_dict() for item in self.evidence],
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(encoded).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile_id": self.profile_id,
            "version": self.version,
            "status": self.status.value,
            "title": self.title,
            "reason": self.reason,
            "deprecated": self.deprecated,
            "fingerprint": self.fingerprint,
            "evidence": [item.to_dict() for item in self.evidence],
        }
