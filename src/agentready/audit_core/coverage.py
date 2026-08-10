"""Deterministic audit coverage accounting."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class AuditCoverage:
    total_rules: int
    evaluated_rules: int
    applicable_rules: int
    complete_rules: int

    def __post_init__(self) -> None:
        values = (self.total_rules, self.evaluated_rules, self.applicable_rules, self.complete_rules)
        if any(value < 0 for value in values):
            raise ValueError("coverage counts must not be negative")
        if not (self.complete_rules <= self.applicable_rules <= self.evaluated_rules <= self.total_rules):
            raise ValueError("coverage counts must be monotonically bounded")

    def to_dict(self) -> dict[str, int]:
        return {
            "total_rules": self.total_rules,
            "evaluated_rules": self.evaluated_rules,
            "applicable_rules": self.applicable_rules,
            "complete_rules": self.complete_rules,
        }
