"""Lossless URL identity and deterministic fingerprint contracts."""
from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from urllib.parse import urlsplit

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class Origin:
    scheme: str
    host: str
    port: int | None = None

    def __post_init__(self) -> None:
        if self.scheme not in {"http", "https"}:
            raise ValueError("origin scheme must be http or https")
        if not self.host:
            raise ValueError("origin host must not be empty")

    def to_string(self) -> str:
        suffix = f":{self.port}" if self.port is not None else ""
        return f"{self.scheme}://{self.host}{suffix}"


@dataclass(frozen=True, slots=True)
class UrlIdentity:
    original: str
    scheme: str
    host: str
    port: int | None
    path: str
    query: str
    fragment: str

    @classmethod
    def parse(cls, value: str) -> "UrlIdentity":
        logger.debug("[WP1.2] parsing URL identity length=%d", len(value))
        if not value or not value.strip():
            raise ValueError("URL must not be empty")
        parts = urlsplit(value)
        if parts.scheme not in {"http", "https"} or not parts.hostname:
            raise ValueError("URL must be an absolute HTTP(S) URL")
        identity = cls(
            original=value,
            scheme=parts.scheme.lower(),
            host=parts.hostname.lower(),
            port=parts.port,
            path=parts.path or "/",
            query=parts.query,
            fragment=parts.fragment,
        )
        logger.debug("[WP1.2] parsed URL identity origin=%s path=%s", identity.origin.to_string(), identity.path)
        return identity

    @property
    def origin(self) -> Origin:
        return Origin(self.scheme, self.host, self.port)

    def lossless(self) -> str:
        return self.original

    def normalized(self) -> str:
        query = f"?{self.query}" if self.query else ""
        fragment = f"#{self.fragment}" if self.fragment else ""
        return f"{self.scheme}://{self.host}{f':{self.port}' if self.port else ''}{self.path}{query}{fragment}"

    def to_dict(self) -> dict[str, object]:
        return {
            "original": self.original,
            "normalized": self.normalized(),
            "origin": self.origin.to_string(),
            "path": self.path,
            "query": self.query,
            "fragment": self.fragment,
        }


def fingerprint(rule_id: str, rule_version: str, target: UrlIdentity, inputs: object) -> str:
    """Return a stable finding key without embedding raw secret-bearing inputs."""
    logger.debug("[WP1.3] fingerprinting rule_id=%s version=%s target=%s", rule_id, rule_version, target.origin.to_string())
    if not rule_id.strip() or not rule_version.strip():
        raise ValueError("rule_id and rule_version must not be empty")
    payload = {
        "rule_id": rule_id,
        "rule_version": rule_version,
        "target": target.normalized(),
        "inputs": _safe_inputs(inputs),
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    result = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
    logger.debug("[WP1.3] fingerprint generated rule_id=%s digest_prefix=%s", rule_id, result[:12])
    return result


def _safe_inputs(value: object) -> object:
    if isinstance(value, dict):
        return {
            str(key): "[REDACTED]"
            if any(token in str(key).lower() for token in ("authorization", "cookie", "secret", "token", "password"))
            else _safe_inputs(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_safe_inputs(item) for item in value]
    return value
