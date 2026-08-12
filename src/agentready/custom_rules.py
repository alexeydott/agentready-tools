"""Safe, bounded custom extraction rules without executable code or network access."""
from __future__ import annotations

import json
import logging
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import StrEnum


class CustomRuleKind(StrEnum):
    CSS = "css"
    TEXT = "text"
    REGEX = "regex"
    HEADER = "header"
    JSON_LD = "json-ld"
    LINK = "link"
    RESOURCE = "resource"


_SENSITIVE_HEADERS = frozenset(
    {"authorization", "cookie", "set-cookie", "proxy-authorization", "x-api-key"}
)
logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class CustomRule:
    id: str
    kind: CustomRuleKind
    pattern: str
    max_matches: int = 100

    def __post_init__(self) -> None:
        if not self.id.strip() or not self.pattern:
            raise ValueError("custom rule id and pattern are required")
        if len(self.pattern) > 2048:
            raise ValueError("custom rule pattern must not exceed 2048 characters")
        if self.max_matches <= 0 or self.max_matches > 1000:
            raise ValueError("custom rule max_matches must be between 1 and 1000")
        if self.kind is CustomRuleKind.REGEX:
            try:
                re.compile(self.pattern)
            except re.error as exc:
                raise ValueError(f"invalid custom rule regex: {exc}") from exc


@dataclass(frozen=True, slots=True)
class CustomRuleMatch:
    rule_id: str
    matches: tuple[str, ...]

    @property
    def count(self) -> int:
        return len(self.matches)


def apply_rule(
    rule: CustomRule,
    *,
    text: str = "",
    headers: dict[str, str] | None = None,
    structured_data: Iterable[Mapping[str, object]] = (),
    links: Iterable[str] = (),
    resources: Iterable[str] = (),
    css_matches: Iterable[str] = (),
) -> tuple[str, ...]:
    if rule.kind is CustomRuleKind.CSS:
        # CSS is deliberately not a substring search.  Callers must provide
        # matches from the shared parsed representation (bounded externally).
        return tuple(css_matches)[:rule.max_matches]
    if rule.kind is CustomRuleKind.TEXT:
        return (rule.pattern,) if rule.pattern in text else ()
    if rule.kind is CustomRuleKind.HEADER:
        value = (headers or {}).get(rule.pattern)
        if value is None:
            return ()
        return ("[REDACTED]",) if rule.pattern.lower() in _SENSITIVE_HEADERS else (value,)
    if rule.kind is CustomRuleKind.JSON_LD:
        matches = [
            json.dumps(item, sort_keys=True, ensure_ascii=True)
            for item in structured_data
            if rule.pattern in item
        ]
        return tuple(matches[:rule.max_matches])
    if rule.kind is CustomRuleKind.LINK:
        return tuple(value for value in links if rule.pattern in value)[:rule.max_matches]
    if rule.kind is CustomRuleKind.RESOURCE:
        return tuple(value for value in resources if rule.pattern in value)[:rule.max_matches]
    matches = [match.group(0) for match in re.finditer(rule.pattern, text, flags=re.MULTILINE)]
    return tuple(matches[:rule.max_matches])


def debug_representation(
    text: str,
    rules: tuple[CustomRule, ...] | list[CustomRule],
    *,
    headers: dict[str, str] | None = None,
    structured_data: Iterable[Mapping[str, object]] = (),
    links: Iterable[str] = (),
    resources: Iterable[str] = (),
    css_matches: Iterable[str] = (),
    max_rules: int = 100,
) -> tuple[CustomRuleMatch, ...]:
    """Apply allowlisted rules to one saved representation with bounded output."""
    if max_rules <= 0 or max_rules > 100:
        raise ValueError("custom debugger rule limit must be between 1 and 100")
    selected = sorted(rules[:max_rules], key=lambda item: item.id)
    structured_data = tuple(structured_data)
    links = tuple(links)
    resources = tuple(resources)
    matches = tuple(
        CustomRuleMatch(
            rule.id,
            apply_rule(
                rule,
                text=text,
                headers=headers,
                structured_data=structured_data,
                links=links,
                resources=resources,
                css_matches=css_matches,
            ),
        )
        for rule in selected
    )
    logger.debug(
        "custom rule debugger complete rules=%d matches=%s",
        len(matches),
        ",".join(f"{item.rule_id}:{item.count}" for item in matches),
    )
    return matches


# Editable, safe presets.  Values are declarative CustomRule objects; callers
# may copy/modify them without introducing executable code or network access.
BUILTIN_PRESETS: dict[str, tuple[CustomRule, ...]] = {
    "analytics": (
        CustomRule("google-analytics", CustomRuleKind.TEXT, "googletagmanager.com/gtag/js"),
        CustomRule("google-tag-manager", CustomRuleKind.RESOURCE, "googletagmanager.com"),
        CustomRule("yandex-metrica", CustomRuleKind.RESOURCE, "mc.yandex.ru"),
    ),
    "schema": (
        CustomRule("jsonld-schema", CustomRuleKind.JSON_LD, "@type"),
        CustomRule("microdata-schema", CustomRuleKind.TEXT, "itemtype"),
    ),
}


def builtin_presets() -> dict[str, tuple[CustomRule, ...]]:
    """Return a copy of built-in presets suitable for UI editing."""
    return {name: (*rules,) for name, rules in BUILTIN_PRESETS.items()}
