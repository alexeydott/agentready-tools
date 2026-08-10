"""Secret-safe evidence and fetch contracts."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .urls import UrlIdentity


@dataclass(frozen=True, slots=True)
class Evidence:
    action: str
    target: UrlIdentity
    finding: str
    status_code: int | None = None
    content_type: str | None = None
    metrics: dict[str, int | float | str] = field(default_factory=dict)
    header_names: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "target": self.target.to_dict(),
            "finding": self.finding,
            "status_code": self.status_code,
            "content_type": self.content_type,
            "metrics": dict(sorted(self.metrics.items())),
            "header_names": sorted(self.header_names),
        }


@dataclass(frozen=True, slots=True)
class FetchRecord:
    request: UrlIdentity
    purpose: str
    status_code: int | None
    content_type: str | None
    elapsed_ms: int | None
    redirects: tuple[UrlIdentity, ...] = ()
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "request": self.request.to_dict(),
            "purpose": self.purpose,
            "status_code": self.status_code,
            "content_type": self.content_type,
            "elapsed_ms": self.elapsed_ms,
            "redirects": [item.to_dict() for item in self.redirects],
            "error": self.error,
        }
