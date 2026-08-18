from __future__ import annotations

import re
import hashlib
from datetime import datetime
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from .crawler_identity import (
    CrawlerIntent,
    IdentityEvidenceSource,
    observe_crawler,
    verify_crawler,
)

BOT_TOKENS = (
    "OAI-SearchBot",
    "ChatGPT-User",
    "GPTBot",
    "Claude-SearchBot",
    "Claude-User",
    "ClaudeBot",
    "PerplexityBot",
    "Perplexity-User",
    "Googlebot",
)

_REQUEST = re.compile(r'"(?P<method>[A-Z]+)\s+(?P<path>\S+)\s+HTTP/[^\"]+"\s+(?P<status>\d{3})')
_CLIENT_IP = re.compile(r"^(?P<ip>\S+)")
_CLIENT_IP_ANY = re.compile(r"(?P<ip>(?:\d{1,3}\.){3}\d{1,3}|[0-9a-fA-F:]{3,})")
_TIMESTAMP = re.compile(r"\[(?P<timestamp>[^\]]+)\]")


def _safe_path(value: str) -> str:
    parsed = urlsplit(value)
    if not parsed.query and not parsed.fragment:
        return value
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "[REDACTED]", ""))


def analyze_ai_bot_log(
    lines: Iterable[str],
    *,
    top_paths: int = 20,
    verified_ips: Mapping[str, set[str] | frozenset[str]] | None = None,
) -> dict[str, object]:
    """Summarize observed bot traffic and independently verified identities.

    ``verified_ips`` is optional external verification evidence. A matching
    User-Agent alone remains ``observed`` and is never reported as verified.
    """
    counts: Counter[str] = Counter()
    verified_counts: Counter[str] = Counter()
    statuses: dict[str, Counter[str]] = defaultdict(Counter)
    paths: dict[str, Counter[str]] = defaultdict(Counter)
    identities = {}
    total_lines = 0
    matched_lines = 0
    for line in lines:
        total_lines += 1
        found = next((bot for bot in BOT_TOKENS if bot.lower() in line.lower()), None)
        if not found:
            continue
        matched_lines += 1
        counts[found] += 1
        client_ip_match = _CLIENT_IP.search(line)
        client_ip = client_ip_match.group("ip") if client_ip_match else None
        observation = observe_crawler(
            found,
            known_tokens=BOT_TOKENS,
            intent=CrawlerIntent.DISCOVERY,
            source=IdentityEvidenceSource.ACCESS_LOG,
            client_ip=client_ip,
        )
        verified = verify_crawler(
            observation,
            network_identity_verified=bool(
                client_ip
                and verified_ips
                and client_ip in verified_ips.get(found, frozenset())
            ),
            verification_locator="access_log.client_ip" if client_ip else None,
        )
        if found not in identities or verified.is_verified:
            identities[found] = verified
        if verified.is_verified:
            verified_counts[found] += 1
        m = _REQUEST.search(line)
        if m:
            statuses[found][m.group("status")] += 1
            paths[found][_safe_path(m.group("path"))] += 1
    return {
        "total_lines": total_lines,
        "matched_ai_bot_lines": matched_lines,
        "observed_traffic": dict(counts),
        "verified_traffic": dict(verified_counts),
        "bots": {
            bot: {
                "requests": counts[bot],
                "observed_requests": counts[bot],
                "verified_requests": verified_counts[bot],
                "identity": identities[bot].to_dict(),
                "status_codes": dict(statuses[bot].most_common()),
                "top_paths": [{"path": path, "requests": count} for path, count in paths[bot].most_common(max(0, top_paths))],
            }
            for bot in BOT_TOKENS
            if counts[bot]
        },
    }


def analyze_ai_bot_log_file(
    path: str | Path,
    *,
    top_paths: int = 20,
    verified_ips: Mapping[str, set[str] | frozenset[str]] | None = None,
) -> dict[str, object]:
    with Path(path).open("r", encoding="utf-8", errors="replace") as fh:
        return analyze_ai_bot_log(fh, top_paths=top_paths, verified_ips=verified_ips)


def analyze_project_ai_bot_log(
    lines: Iterable[str],
    *,
    project_target: str,
    start_at: str | None = None,
    end_at: str | None = None,
    verified_ips: Mapping[str, set[str] | frozenset[str]] | None = None,
    max_lines: int = 100_000,
) -> dict[str, object]:
    """Aggregate user-supplied AI-bot logs for one project without collecting logs."""
    if max_lines <= 0 or max_lines > 1_000_000:
        raise ValueError("access-log line limit must be between 1 and 1000000")
    target = urlsplit(project_target)
    if target.scheme not in {"http", "https"} or not target.netloc or target.username or target.password:
        raise ValueError("project target must be an HTTP(S) URL without credentials")
    start = _parse_log_time(start_at) if start_at else None
    end = _parse_log_time(end_at) if end_at else None
    if start and end and start > end:
        raise ValueError("start_at must not exceed end_at")
    totals = Counter()
    bots: dict[str, Counter[str]] = defaultdict(Counter)
    unmatched = Counter()
    seen: set[str] = set()
    malformed = 0
    for index, line in enumerate(lines):
        if index >= max_lines:
            break
        digest = hashlib.sha256(line.encode("utf-8", "replace")).hexdigest()
        if digest in seen:
            totals["duplicate_lines"] += 1
            continue
        seen.add(digest)
        found = next((bot for bot in BOT_TOKENS if bot.lower() in line.lower()), None)
        if not found:
            continue
        timestamp = _line_time(line)
        if timestamp is None and (start or end):
            unmatched["missing_timestamp"] += 1
            continue
        if timestamp is not None and start and timestamp < start:
            unmatched["out_of_window"] += 1
            continue
        if timestamp is not None and end and timestamp > end:
            unmatched["out_of_window"] += 1
            continue
        request = _REQUEST.search(line)
        if not request:
            malformed += 1
            unmatched["malformed"] += 1
            continue
        raw_path = request.group("path")
        parsed_path = urlsplit(raw_path)
        if parsed_path.scheme and parsed_path.netloc and parsed_path.netloc.lower() != target.netloc.lower():
            unmatched["cross_origin"] += 1
            continue
        path = _safe_path(raw_path)
        ip_source = line.split("]", 1)[1] if line.lstrip().startswith("[") and "]" in line else line
        ip_match = _CLIENT_IP_ANY.search(ip_source)
        client_ip = ip_match.group("ip") if ip_match else None
        verified = bool(client_ip and verified_ips and client_ip in verified_ips.get(found, frozenset()))
        totals["matched_requests"] += 1
        bots[found]["requests"] += 1
        bots[found]["verified_requests"] += int(verified)
        bots[found]["observed_requests"] += 1
        bots[found][f"status_{request.group('status')}"] += 1
        bots[found]["paths_seen"] += 1
        # Store only a redacted path fingerprint in the project metric projection.
        bots[found][f"path_{hashlib.sha256(path.encode()).hexdigest()[:12]}"] += 1
    totals["malformed_lines"] = malformed
    totals["unmatched_requests"] = sum(unmatched.values())
    return {
        "schema": "agentready.access-log.project.v2",
        "project_origin": f"{target.scheme.lower()}://{target.netloc.lower()}",
        "window": {"start_at": start_at, "end_at": end_at},
        "totals": dict(totals),
        "bots": {bot: dict(values) for bot, values in sorted(bots.items())},
        "unmatched": dict(sorted(unmatched.items())),
        "redaction": "query strings and raw log lines are never returned",
    }


def _parse_log_time(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("log time must be ISO-8601") from exc
    if parsed.tzinfo is None:
        raise ValueError("log time must include timezone")
    return parsed


def _line_time(line: str) -> datetime | None:
    match = _TIMESTAMP.search(line)
    if not match:
        return None
    value = match.group("timestamp")
    for parser in (lambda item: datetime.strptime(item, "%d/%b/%Y:%H:%M:%S %z"), lambda item: datetime.fromisoformat(item.replace("Z", "+00:00"))):
        try:
            parsed = parser(value)
            return parsed if parsed.tzinfo is not None else None
        except ValueError:
            continue
    return None
