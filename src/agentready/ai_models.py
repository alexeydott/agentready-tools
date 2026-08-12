"""Typed contracts for the opt-in SEO/GEO AI assistant.

The models in this module are standard-library dataclasses so importing the
base scanner never requires the optional AI SDK or server dependencies.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

AssistantMode = Literal["seo", "geo", "both"]
AssistantOperation = Literal["recommend", "chat"]
HistoryRole = Literal["user", "assistant"]


@dataclass(slots=True, frozen=True)
class ConversationMessage:
    role: HistoryRole
    content: str

    def __post_init__(self) -> None:
        if self.role not in {"user", "assistant"}:
            raise ValueError("conversation role must be user or assistant")
        if not isinstance(self.content, str) or not self.content.strip():
            raise ValueError("conversation content must be non-empty")


@dataclass(slots=True, frozen=True)
class EvidenceReference:
    check_id: str
    status: str
    details: str
    evidence: tuple[str, ...] = ()
    source_url: str | None = None
    metrics: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True, frozen=True)
class AssistantAction:
    title: str
    action: str
    priority: Literal["high", "medium", "low"]
    check_ids: tuple[str, ...] = ()
    verification: tuple[str, ...] = ()


@dataclass(slots=True, frozen=True)
class AssistantUsage:
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    input_price_per_million: float | None = None
    output_price_per_million: float | None = None
    input_cost: float | None = None
    output_cost: float | None = None
    total_cost: float | None = None


@dataclass(slots=True, frozen=True)
class AssistantError:
    code: str
    message: str
    retryable: bool = False
    request_id: str | None = None


@dataclass(slots=True)
class AssistantResponse:
    schema: str = "agentready.ai-assistant.v2"
    operation: AssistantOperation = "recommend"
    mode: AssistantMode = "both"
    language: str = "en"
    target: str | None = None
    model: str | None = None
    summary: str = ""
    actions: list[AssistantAction] = field(default_factory=list)
    evidence: list[EvidenceReference] = field(default_factory=list)
    cautions: list[str] = field(default_factory=list)
    disclaimer: str = ""
    usage: AssistantUsage | None = None
    error: AssistantError | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True, frozen=True)
class AssistantRequest:
    operation: AssistantOperation
    mode: AssistantMode
    language: str = "en"
    target: str | None = None
    report: dict[str, Any] | None = None
    message: str | None = None
    history: tuple[ConversationMessage, ...] = ()
    skills: tuple[str, ...] = ()
    mcp_tools: tuple[str, ...] = ()
    attachments: tuple[dict[str, str], ...] = ()
    mcp_context: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        if self.operation not in {"recommend", "chat"}:
            raise ValueError("operation must be recommend or chat")
        if self.mode not in {"seo", "geo", "both"}:
            raise ValueError("mode must be seo, geo, or both")
        if self.language not in {"en", "ru"}:
            raise ValueError("language must be en or ru")
        if self.operation == "chat" and not self.message:
            raise ValueError("chat operation requires a message")
