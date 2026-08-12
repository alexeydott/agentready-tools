"""Secret redaction helpers for logs and persisted audit evidence."""
from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

_SECRET_KEY = re.compile(r"(authorization|proxy-authorization|cookie|set-cookie|token|secret|password|api[-_]?key)", re.IGNORECASE)
_BEARER = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+")


class SecretRedactor:
    """Redact credential-shaped values without retaining the original secret."""

    replacement = "[REDACTED]"

    def mapping(self, values: Mapping[str, Any]) -> dict[str, Any]:
        return {
            str(key): self.replacement if _SECRET_KEY.search(str(key)) else self.value(value)
            for key, value in values.items()
        }

    def value(self, value: Any) -> Any:
        if isinstance(value, Mapping):
            return self.mapping(value)
        if isinstance(value, list):
            return [self.value(item) for item in value]
        if isinstance(value, tuple):
            return tuple(self.value(item) for item in value)
        if isinstance(value, str):
            return _BEARER.sub(self.replacement, value)
        return value

    def text(self, value: str) -> str:
        return _BEARER.sub(self.replacement, value)
