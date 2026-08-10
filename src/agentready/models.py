from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

Status = Literal["pass", "fail", "warn", "skip", "error"]
Impact = Literal["high", "medium", "low"]
Effort = Literal["low", "medium", "high"]


@dataclass(slots=True)
class Evidence:
    action: str
    url: str | None = None
    method: str | None = None
    status_code: int | None = None
    content_type: str | None = None
    finding: str | None = None
    body_preview: str | None = None
    headers: dict[str, str] = field(default_factory=dict)
    metrics: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class Remediation:
    summary: str
    rerun_command: str
    references: list[str] = field(default_factory=list)
    agent_prompt: str | None = None


@dataclass(slots=True)
class CheckResult:
    id: str
    title: str
    category: str
    status: Status
    scored: bool
    details: str
    duration_ms: int = 0
    evidence: list[Evidence] = field(default_factory=list)
    remediation: Remediation | None = None
    experimental: bool = False
    supplemental: bool = False
    geo_scored: bool = False

    @property
    def passed(self) -> bool:
        return self.status == "pass"


@dataclass(slots=True)
class CategoryScore:
    category: str
    passed: int
    applicable: int
    score: int | None


@dataclass(slots=True)
class NextLevel:
    target: int
    name: str
    requirements: list[str]
    current: int = 0
    needed: int = 0
    remaining: int = 0


@dataclass(slots=True)
class Recommendation:
    check_id: str
    title: str
    action: str
    reason: str
    impact: Impact
    effort: Effort
    priority: int


@dataclass(slots=True)
class ScanReport:
    target: str
    origin: str
    preset: str
    checks: list[CheckResult]
    score: int
    level: int
    level_name: str
    level_model: str
    categories: list[CategoryScore]
    next_level: NextLevel | None
    recommendations: list[Recommendation]
    is_commerce: bool
    commerce_signals: list[str]
    started_at: str
    finished_at: str
    selected_check_ids: list[str] = field(default_factory=list)
    config_source: str | None = None
    language: str = "en"
    ai_search_score: int | None = None
    ai_search_applicable: int = 0
    tool_version: str = "0.8.0"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
