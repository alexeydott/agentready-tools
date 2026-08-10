"""RFC 9309 robots policy parsing, evaluation, and safe simulation."""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from urllib.parse import urlsplit

logger = logging.getLogger(__name__)
MAX_ROBOTS_BYTES = 500 * 1024


class RobotsInterpretation(StrEnum):
    RFC9309 = "rfc9309"
    GOOGLE = "google"


class RobotsFetchStatus(StrEnum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    UNREACHABLE = "unreachable"


@dataclass(frozen=True, slots=True)
class RobotsRule:
    path: str
    allow: bool
    line: int


@dataclass(frozen=True, slots=True)
class RobotsGroup:
    user_agents: tuple[str, ...]
    rules: tuple[RobotsRule, ...]


@dataclass(frozen=True, slots=True)
class RobotsFetchState:
    fetch_status: RobotsFetchStatus
    fetched_at: datetime | None = None
    source_fetch_id: str | None = None
    effective_until: datetime | None = None
    http_status: int | None = None


@dataclass(frozen=True, slots=True)
class RobotsPolicy:
    origin: str
    groups: tuple[RobotsGroup, ...]
    sitemaps: tuple[str, ...] = ()
    parse_warnings: tuple[str, ...] = ()
    fetch: RobotsFetchState | None = None


@dataclass(frozen=True, slots=True)
class RobotsDecision:
    allowed: bool
    matched_rule: RobotsRule | None
    interpretation: RobotsInterpretation
    reason: str


@dataclass(frozen=True, slots=True)
class RobotsPolicyDiff:
    newly_allowed_urls: tuple[str, ...]
    newly_blocked_urls: tuple[str, ...]
    sitemap_urls_affected: tuple[str, ...]
    observed_search_pages_affected: tuple[str, ...]
    label: str = "SIMULATION - site not changed"


def parse_robots(text: str, origin: str, *, fetch: RobotsFetchState | None = None) -> RobotsPolicy:
    raw = text.encode("utf-8")
    if len(raw) > MAX_ROBOTS_BYTES:
        raise ValueError(f"robots.txt exceeds RFC parsing limit of 500 KiB ({MAX_ROBOTS_BYTES} bytes)")
    groups: list[RobotsGroup] = []
    agents: list[str] = []
    rules: list[RobotsRule] = []
    sitemaps: list[str] = []
    warnings: list[str] = []

    def flush() -> None:
        nonlocal agents, rules
        if agents:
            groups.append(RobotsGroup(tuple(dict.fromkeys(agents)), tuple(rules)))
        agents, rules = [], []

    for line_number, raw_line in enumerate(text.splitlines(), 1):
        line = raw_line.split("#", 1)[0].strip()
        if not line or ":" not in line:
            if line:
                warnings.append(f"line {line_number}: ignored malformed directive")
            continue
        name, value = (part.strip() for part in line.split(":", 1))
        key = name.lower()
        if key == "user-agent":
            if rules:
                flush()
            if value:
                agents.append(value.lower())
            else:
                warnings.append(f"line {line_number}: empty user-agent")
        elif key in {"allow", "disallow"}:
            if not agents:
                warnings.append(f"line {line_number}: rule without user-agent")
                continue
            if not value and key == "disallow":
                continue
            rules.append(RobotsRule(value, key == "allow", line_number))
        elif key == "sitemap":
            if value:
                sitemaps.append(value)
        else:
            warnings.append(f"line {line_number}: unknown directive {name}")
    flush()
    logger.debug("[WP5.1] parsed robots origin=%s groups=%d sitemaps=%d warnings=%d", origin, len(groups), len(sitemaps), len(warnings))
    return RobotsPolicy(origin, tuple(groups), tuple(dict.fromkeys(sitemaps)), tuple(warnings), fetch)


def robots_fetch_state(status_code: int | None, *, interpretation: RobotsInterpretation = RobotsInterpretation.RFC9309) -> RobotsFetchStatus:
    if status_code is None or status_code >= 500:
        return RobotsFetchStatus.UNREACHABLE
    if status_code == 429:
        return RobotsFetchStatus.UNREACHABLE
    if 400 <= status_code < 500:
        return RobotsFetchStatus.UNAVAILABLE
    return RobotsFetchStatus.AVAILABLE


def evaluate_robots(
    policy: RobotsPolicy,
    user_agent: str,
    url: str,
    *,
    interpretation: RobotsInterpretation = RobotsInterpretation.RFC9309,
) -> RobotsDecision:
    if policy.fetch and policy.fetch.fetch_status == RobotsFetchStatus.UNAVAILABLE:
        return RobotsDecision(True, None, interpretation, "robots.txt unavailable under RFC 9309")
    if policy.fetch and policy.fetch.fetch_status == RobotsFetchStatus.UNREACHABLE:
        return RobotsDecision(False, None, interpretation, "robots.txt unreachable; fail closed")
    path = urlsplit(url).path or "/"
    if urlsplit(url).query:
        path += "?" + urlsplit(url).query
    ua = user_agent.lower()
    matches = [group for group in policy.groups if any(token == "*" or token in ua for token in group.user_agents)]
    if not matches:
        return RobotsDecision(True, None, interpretation, "no matching user-agent group")
    best = max(
        (group for group in matches),
        key=lambda group: max((len(token) for token in group.user_agents if token == "*" or token in ua), default=0),
    )
    applicable = [rule for rule in best.rules if _pattern_matches(rule.path, path)]
    if not applicable:
        return RobotsDecision(True, None, interpretation, "no matching rule")
    selected = max(applicable, key=lambda rule: (_match_length(rule.path, path), int(rule.allow)))
    return RobotsDecision(selected.allow, selected, interpretation, "matched longest rule")


def simulate_robots(
    live: RobotsPolicy,
    simulated: RobotsPolicy,
    urls: list[str] | tuple[str, ...],
    *,
    user_agent: str = "*",
    observed_search_pages: list[str] | tuple[str, ...] = (),
) -> RobotsPolicyDiff:
    newly_allowed: list[str] = []
    newly_blocked: list[str] = []
    for url in dict.fromkeys(urls):
        before = evaluate_robots(live, user_agent, url).allowed
        after = evaluate_robots(simulated, user_agent, url).allowed
        if after and not before:
            newly_allowed.append(url)
        elif before and not after:
            newly_blocked.append(url)
    affected_sitemaps = sorted(set(live.sitemaps) ^ set(simulated.sitemaps))
    observed = tuple(url for url in observed_search_pages if url in newly_allowed or url in newly_blocked)
    logger.info("[WP5.2] robots simulation urls=%d allowed_delta=%d blocked_delta=%d", len(urls), len(newly_allowed), len(newly_blocked))
    return RobotsPolicyDiff(tuple(newly_allowed), tuple(newly_blocked), tuple(affected_sitemaps), observed)


def sensitive_path_diagnostic(policy: RobotsPolicy) -> tuple[str, ...]:
    """Return informational diagnostics; robots.txt never grants authorization."""
    sensitive = tuple(
        rule.path for group in policy.groups for rule in group.rules
        if rule.allow is False and re.search(r"(?:admin|login|private|secret|backup)", rule.path, re.I)
    )
    return tuple(f"robots rule mentions sensitive path {path}; robots.txt is not an access control" for path in sensitive)


def _pattern_matches(pattern: str, path: str) -> bool:
    regex = re.escape(pattern).replace(r"\*", ".*")
    if pattern.endswith("$"):
        regex = regex[:-2] + "$"
    return re.match("^" + regex, path, re.I) is not None


def _match_length(pattern: str, path: str) -> int:
    return len(re.match(r"^[^$*]*", pattern).group(0)) if _pattern_matches(pattern, path) else 0
