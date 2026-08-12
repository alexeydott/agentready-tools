from __future__ import annotations

import re
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
