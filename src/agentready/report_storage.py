"""Bounded local report persistence shared by CLI, HTTP, and dashboard flows."""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

_SAFE = re.compile(r"[^A-Za-z0-9._-]+")


def reports_dir() -> Path:
    """Return the report directory beside the executable or project root."""
    configured = os.environ.get("AGENTREADY_REPORT_DIR")
    if configured:
        path = Path(configured).expanduser().resolve()
    else:
        base = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parents[2]
        path = base / ".reports"
    path.mkdir(parents=True, exist_ok=True)
    return path


def save_report(content: str | dict[str, Any], *, target: str, surface: str, fmt: str) -> Path:
    """Write one timestamped report without logging content or credentials."""
    host = _SAFE.sub("-", urlsplit(target).netloc or "target").strip("-") or "target"
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    suffix = "json" if fmt == "json" else fmt
    path = reports_dir() / f"{stamp}-{_SAFE.sub('-', surface)}-{host}.{suffix}"
    if isinstance(content, dict):
        path.write_text(json.dumps(content, ensure_ascii=False, indent=2), encoding="utf-8")
    else:
        path.write_text(content, encoding="utf-8")
    return path
