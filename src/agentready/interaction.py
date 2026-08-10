"""Offline semantic interaction checks for agent-facing browser surfaces."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Mapping

logger = logging.getLogger(__name__)


class InteractionStatus(StrEnum):
    PASS = "pass"
    WARN = "warn"
    NOT_EVALUATED = "not_evaluated"


class InteractionApplicability(StrEnum):
    APPLICABLE = "applicable"
    NOT_APPLICABLE = "not_applicable"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class InteractionEvidence:
    locator: str
    summary: str


@dataclass(frozen=True, slots=True)
class InteractionFinding:
    rule_id: str
    status: InteractionStatus
    applicability: InteractionApplicability
    reason: str
    evidence: tuple[InteractionEvidence, ...] = ()


def _walk(node: Mapping[str, Any], path: str = "$"):
    yield path, node
    for index, child in enumerate(node.get("children", ())):
        if isinstance(child, Mapping):
            yield from _walk(child, f"{path}.children[{index}]")


def audit_accessibility_tree(tree: Mapping[str, Any]) -> tuple[InteractionFinding, ...]:
    """Evaluate semantic controls without clicking, submitting, or navigating."""
    logger.debug("interaction audit start root_keys=%s", sorted(tree))
    nodes = tuple(_walk(tree))
    controls = tuple(
        (path, node)
        for path, node in nodes
        if str(node.get("role", "")).lower()
        in {"button", "link", "textbox", "checkbox", "combobox", "radio"}
    )
    forms = tuple((path, node) for path, node in nodes if str(node.get("role", "")).lower() == "form")
    findings: list[InteractionFinding] = []

    if controls:
        unnamed = tuple(path for path, node in controls if not str(node.get("name", "")).strip())
        findings.append(
            InteractionFinding(
                "semantic-control-name",
                InteractionStatus.WARN if unnamed else InteractionStatus.PASS,
                InteractionApplicability.APPLICABLE,
                "Interactive controls must expose an accessible name."
                if unnamed
                else "Interactive controls expose accessible names.",
                tuple(InteractionEvidence(path, "Control has no accessible name") for path in unnamed)
                or (InteractionEvidence("$", "All interactive controls have names"),),
            )
        )
    else:
        findings.append(
            InteractionFinding(
                "semantic-control-name",
                InteractionStatus.NOT_EVALUATED,
                InteractionApplicability.NOT_APPLICABLE,
                "No semantic interactive controls were observed.",
            )
        )

    if forms:
        incomplete = tuple(
            path
            for path, form in forms
            if not any(str(child.get("role", "")).lower() in {"button", "submit"} for child in form.get("children", ()) if isinstance(child, Mapping))
        )
        findings.append(
            InteractionFinding(
                "form-submit-control",
                InteractionStatus.WARN if incomplete else InteractionStatus.PASS,
                InteractionApplicability.APPLICABLE,
                "Forms should expose a semantic submit control."
                if incomplete
                else "Forms expose semantic submit controls.",
                tuple(InteractionEvidence(path, "Form has no submit control") for path in incomplete),
            )
        )
    else:
        findings.append(
            InteractionFinding(
                "form-submit-control",
                InteractionStatus.NOT_EVALUATED,
                InteractionApplicability.NOT_APPLICABLE,
                "No forms were observed in the supplied accessibility tree.",
            )
        )

    logger.debug("interaction audit complete nodes=%d findings=%d", len(nodes), len(findings))
    return tuple(findings)
