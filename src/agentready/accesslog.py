from __future__ import annotations

import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable

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


def analyze_ai_bot_log(lines: Iterable[str], *, top_paths: int = 20) -> dict[str, object]:
    counts: Counter[str] = Counter()
    statuses: dict[str, Counter[str]] = defaultdict(Counter)
    paths: dict[str, Counter[str]] = defaultdict(Counter)
    total_lines = 0
    matched_lines = 0
    for line in lines:
        total_lines += 1
        found = next((bot for bot in BOT_TOKENS if bot.lower() in line.lower()), None)
        if not found:
            continue
        matched_lines += 1
        counts[found] += 1
        m = _REQUEST.search(line)
        if m:
            statuses[found][m.group("status")] += 1
            paths[found][m.group("path")] += 1
    return {
        "total_lines": total_lines,
        "matched_ai_bot_lines": matched_lines,
        "bots": {
            bot: {
                "requests": counts[bot],
                "status_codes": dict(statuses[bot].most_common()),
                "top_paths": [{"path": path, "requests": count} for path, count in paths[bot].most_common(max(0, top_paths))],
            }
            for bot in BOT_TOKENS
            if counts[bot]
        },
    }


def analyze_ai_bot_log_file(path: str | Path, *, top_paths: int = 20) -> dict[str, object]:
    with Path(path).open("r", encoding="utf-8", errors="replace") as fh:
        return analyze_ai_bot_log(fh, top_paths=top_paths)
