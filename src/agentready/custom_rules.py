"""Safe, bounded custom extraction rules without executable code or network access."""
from __future__ import annotations

import json
import hashlib
import logging
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import StrEnum

import yaml


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
CUSTOM_RULE_VERSION = "1"
MAX_RULES = 100
MAX_INPUT_BYTES = 1_000_000


@dataclass(frozen=True, slots=True)
class CustomRule:
    id: str
    kind: CustomRuleKind
    pattern: str
    max_matches: int = 100
    title: str = ""
    scope: str = "page"
    severity: str = "info"
    url_regex: str | None = None

    def __post_init__(self) -> None:
        if not self.id.strip() or not self.pattern:
            raise ValueError("custom rule id and pattern are required")
        if len(self.pattern) > 2048:
            raise ValueError("custom rule pattern must not exceed 2048 characters")
        if self.max_matches <= 0 or self.max_matches > 1000:
            raise ValueError("custom rule max_matches must be between 1 and 1000")
        if self.scope != "page":
            raise ValueError("custom rule scope must be page")
        if self.severity not in {"info", "low", "medium", "high", "critical"}:
            raise ValueError("unsupported custom rule severity")
        if self.kind is CustomRuleKind.REGEX:
            if _unsafe_regex(self.pattern):
                raise ValueError("custom rule regex contains unsupported or expensive construct")
            try:
                re.compile(self.pattern)
            except re.error as exc:
                raise ValueError(f"invalid custom rule regex: {exc}") from exc
        if self.url_regex:
            if _unsafe_regex(self.url_regex):
                raise ValueError("custom rule URL regex contains unsupported or expensive construct")
            try:
                re.compile(self.url_regex)
            except re.error as exc:
                raise ValueError(f"invalid custom rule URL regex: {exc}") from exc


@dataclass(frozen=True, slots=True)
class CustomRuleMatch:
    rule_id: str
    matches: tuple[str, ...]

    @property
    def count(self) -> int:
        return len(self.matches)


@dataclass(frozen=True, slots=True)
class CustomRuleDocument:
    version: str
    rules: tuple[CustomRule, ...]
    rule_hash: str


def _unsafe_regex(pattern: str) -> bool:
    """Reject constructs with poor or implementation-dependent worst cases."""
    return bool(
        re.search(r"\\[1-9]", pattern)
        or re.search(r"\(\?[=!<]", pattern)
        or re.search(r"\([^)]*[+*]\)[+*?]", pattern)
        or re.search(r"\{\d{4,}(?:,\d*)?\}", pattern)
    )


def _document_payload(payload: Mapping[str, object] | str) -> Mapping[str, object]:
    if isinstance(payload, str):
        if len(payload.encode("utf-8")) > MAX_INPUT_BYTES:
            raise ValueError("custom rules document exceeds input limit")
        try:
            loaded = yaml.safe_load(payload)
        except yaml.YAMLError as exc:
            raise ValueError(f"invalid custom rules document: {exc}") from exc
    else:
        loaded = payload
    if not isinstance(loaded, Mapping):
        raise ValueError("custom rules document must be a mapping")
    return loaded


def compile_rules(payload: Mapping[str, object] | str) -> CustomRuleDocument:
    """Validate and compile the declarative v1 rules document without eval."""
    document = _document_payload(payload)
    version = str(document.get("version", ""))
    if version != CUSTOM_RULE_VERSION:
        raise ValueError("unsupported custom rules version")
    raw_rules = document.get("rules")
    if not isinstance(raw_rules, list) or not raw_rules or len(raw_rules) > MAX_RULES:
        raise ValueError("rules must contain between 1 and 100 entries")
    compiled: list[CustomRule] = []
    seen: set[str] = set()
    for raw in raw_rules:
        if not isinstance(raw, Mapping):
            raise ValueError("each custom rule must be a mapping")
        unknown_fields = set(raw) - {"id", "title", "scope", "when", "assert", "severity"}
        if unknown_fields:
            raise ValueError("unsupported custom rule fields")
        rule_id = str(raw.get("id", ""))
        if rule_id in seen:
            raise ValueError("custom rule ids must be unique")
        assertion = raw.get("assert")
        if not isinstance(assertion, Mapping):
            raise ValueError("custom rule assert must be a mapping")
        if set(assertion) - {"kind", "pattern", "max_matches"}:
            raise ValueError("unsupported custom rule assertion fields")
        when = raw.get("when", {})
        if not isinstance(when, Mapping) or set(when) - {"url_regex"}:
            raise ValueError("unsupported custom rule condition")
        kind = CustomRuleKind(str(assertion.get("kind", "")))
        pattern = str(assertion.get("pattern", ""))
        max_matches = int(assertion.get("max_matches", 100))
        compiled.append(CustomRule(
            rule_id,
            kind,
            pattern,
            max_matches,
            str(raw.get("title", "")),
            str(raw.get("scope", "page")),
            str(raw.get("severity", "info")),
            str(when["url_regex"]) if "url_regex" in when else None,
        ))
        seen.add(rule_id)
    canonical = {"version": version, "rules": [{"id": item.id, "title": item.title, "scope": item.scope, "when": {"url_regex": item.url_regex} if item.url_regex else {}, "assert": {"kind": item.kind.value, "pattern": item.pattern, "max_matches": item.max_matches}, "severity": item.severity} for item in sorted(compiled, key=lambda rule: rule.id)]}
    rule_hash = hashlib.sha256(json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    logger.info("custom rules compiled version=%s rules=%d hash=%s", version, len(compiled), rule_hash[:16])
    return CustomRuleDocument(version, tuple(compiled), rule_hash)


def validate_rules(payload: Mapping[str, object] | str) -> dict[str, object]:
    document = compile_rules(payload)
    return {"valid": True, "version": document.version, "rule_hash": document.rule_hash, "rules": [rule.id for rule in document.rules]}


def apply_rules(document: CustomRuleDocument, **representation: object) -> dict[str, object]:
    text = str(representation.get("text", ""))
    if len(text.encode("utf-8")) > MAX_INPUT_BYTES:
        raise ValueError("custom rule representation exceeds input limit")
    url = str(representation.get("url", ""))
    matches = []
    for rule in document.rules:
        url_regex = rule.url_regex
        if url_regex and not re.search(str(url_regex), url):
            continue
        values = apply_rule(document_rule := rule, text=text, headers=representation.get("headers"), structured_data=representation.get("structured_data", ()), links=representation.get("links", ()), resources=representation.get("resources", ()), css_matches=representation.get("css_matches", ()))
        matches.append({"rule_id": rule.id, "title": rule.title, "severity": rule.severity, "matches": list(values), "count": len(values), "rule_version": document.version, "rule_hash": document.rule_hash})
    logger.info("custom rules applied version=%s hash=%s rules=%d matches=%d", document.version, document.rule_hash[:16], len(document.rules), sum(item["count"] for item in matches))
    return {"version": document.version, "rule_hash": document.rule_hash, "matches": matches}


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
