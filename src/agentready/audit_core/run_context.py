"""Immutable run identity and explicit lifecycle transitions."""
from __future__ import annotations

import hashlib
import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, ClassVar

logger = logging.getLogger(__name__)


class RunState(StrEnum):
    CREATED = "created"
    RUNNING = "running"
    COMPLETED = "completed"
    PARTIAL = "partial"
    CANCELLING = "cancelling"
    CANCELLED = "cancelled"
    FAILED = "failed"
    INTERRUPTED = "interrupted"


@dataclass(frozen=True, slots=True)
class AuditRunContext:
    run_id: str
    target: str
    config_hash: str
    tool_version: str
    rule_catalog_version: str
    created_at: str

    @classmethod
    def create(
        cls,
        target: str,
        configuration: dict[str, Any],
        *,
        tool_version: str,
        rule_catalog_version: str,
        run_id: str | None = None,
    ) -> AuditRunContext:
        encoded = json.dumps(configuration, sort_keys=True, separators=(",", ":"), default=str)
        config_hash = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
        context = cls(
            run_id=run_id or uuid.uuid4().hex,
            target=target,
            config_hash=config_hash,
            tool_version=tool_version,
            rule_catalog_version=rule_catalog_version,
            created_at=datetime.now(UTC).isoformat(),
        )
        logger.info("audit run created run_id=%s config_hash=%s", context.run_id, config_hash[:12])
        return context


@dataclass(frozen=True, slots=True)
class RunSnapshot:
    context: AuditRunContext
    state: RunState
    completed_at: str | None = None
    error_kind: str | None = None


@dataclass(slots=True)
class RunCoordinator:
    context: AuditRunContext
    state: RunState = RunState.CREATED
    completed_at: str | None = None
    error_kind: str | None = None
    _history: list[RunState] = field(default_factory=lambda: [RunState.CREATED], repr=False)

    _TRANSITIONS: ClassVar[dict[RunState, set[RunState]]] = {
        RunState.CREATED: {RunState.RUNNING, RunState.CANCELLED},
        RunState.RUNNING: {
            RunState.COMPLETED,
            RunState.PARTIAL,
            RunState.CANCELLING,
            RunState.FAILED,
            RunState.INTERRUPTED,
        },
        RunState.CANCELLING: {RunState.CANCELLED, RunState.FAILED},
        RunState.INTERRUPTED: {RunState.RUNNING, RunState.FAILED},
        RunState.COMPLETED: set(),
        RunState.PARTIAL: set(),
        RunState.CANCELLED: set(),
        RunState.FAILED: set(),
    }

    @classmethod
    def resume(cls, snapshot: RunSnapshot) -> RunCoordinator:
        if snapshot.state is not RunState.INTERRUPTED:
            raise ValueError("only interrupted runs can be resumed")
        coordinator = cls(snapshot.context, state=RunState.INTERRUPTED)
        coordinator._history = [RunState.INTERRUPTED]
        coordinator.transition(RunState.RUNNING)
        return coordinator

    def transition(self, state: RunState, *, error_kind: str | None = None) -> RunSnapshot:
        if state not in self._TRANSITIONS[self.state]:
            raise ValueError(f"invalid run transition {self.state.value} -> {state.value}")
        self.state = state
        self.error_kind = error_kind
        if state in {RunState.COMPLETED, RunState.PARTIAL, RunState.CANCELLED, RunState.FAILED}:
            self.completed_at = datetime.now(UTC).isoformat()
        self._history.append(state)
        logger.info("audit run transition run_id=%s state=%s", self.context.run_id, state.value)
        return self.snapshot()

    def snapshot(self) -> RunSnapshot:
        return RunSnapshot(self.context, self.state, self.completed_at, self.error_kind)

    @property
    def history(self) -> tuple[RunState, ...]:
        return tuple(self._history)
