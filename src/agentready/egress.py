"""Shared HTTP/browser egress policy and redirect validation."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from urllib.parse import urlsplit

from collections.abc import Callable
import ipaddress

from .target import TargetError, ensure_public_url, parse_target

logger = logging.getLogger(__name__)
_SENSITIVE_HEADERS = {"authorization", "proxy-authorization", "cookie"}


class EgressPolicyError(TargetError):
    """Raised when a request violates the audit egress boundary."""


@dataclass(frozen=True, slots=True)
class EgressPolicy:
    block_private: bool = False
    max_redirects: int = 5
    max_response_bytes: int = 5 * 1024 * 1024
    allowed_origins: frozenset[str] | None = None
    allowed_schemes: frozenset[str] = frozenset({"http", "https"})
    denied_hosts: tuple[str, ...] = ()
    allow_cross_origin_credentials: bool = False
    resolver: Callable[[str, int], list[ipaddress._BaseAddress]] | None = None

    def __post_init__(self) -> None:
        if self.max_redirects < 0:
            raise ValueError("max_redirects must not be negative")
        if self.max_response_bytes <= 0:
            raise ValueError("max_response_bytes must be positive")

    def validate_request(self, url: str, *, purpose: str = "audit") -> None:
        logger.debug("[WP2.3] validating egress purpose=%s url=%s", purpose, url)
        parsed = urlsplit(url)
        if parsed.username or parsed.password:
            raise EgressPolicyError("credential-bearing URLs are not allowed")
        target = parse_target(url)
        if target.scheme not in self.allowed_schemes:
            raise EgressPolicyError(f"scheme is not allowed: {target.scheme}")
        if target.hostname.lower() in {host.lower() for host in self.denied_hosts}:
            raise EgressPolicyError(f"host is denied by egress policy: {target.hostname}")
        if self.allowed_origins and target.origin not in self.allowed_origins:
            raise EgressPolicyError(f"origin is outside the egress allowlist: {target.origin}")
        if self.block_private:
            if self.resolver is None:
                ensure_public_url(target.url)
            else:
                addresses = self.resolver(target.hostname, target.port)
                if not addresses:
                    raise EgressPolicyError(f"No IP addresses resolved for {target.hostname}")
                if any(address.is_private or address.is_loopback or address.is_link_local or address.is_reserved or address.is_unspecified for address in addresses):
                    raise EgressPolicyError(f"Target resolves to non-public IP address(es): {', '.join(map(str, addresses))}")

    def validate_redirect(self, source_url: str, target_url: str, hop: int, *, purpose: str = "audit") -> None:
        if hop > self.max_redirects:
            raise EgressPolicyError(f"Too many redirects (>{self.max_redirects})")
        self.validate_request(target_url, purpose=purpose)
        logger.debug("[WP2.3] redirect validated hop=%d source=%s target=%s", hop, source_url, target_url)

    def validate_browser_request(self, url: str, *, resource_type: str = "document") -> None:
        """Apply the same destination policy to browser documents and subresources."""
        self.validate_request(url, purpose=f"browser:{resource_type}")

    def validate_headers(self, headers: dict[str, str] | None, *, purpose: str = "audit") -> dict[str, str]:
        values = {key: value for key, value in (headers or {}).items()}
        blocked = sorted(key for key in values if key.lower() in _SENSITIVE_HEADERS)
        if blocked:
            raise EgressPolicyError(
                f"credential-bearing headers are forbidden for passive egress purpose {purpose}: {', '.join(blocked)}"
            )
        return values

    def validate_response_size(self, size: int) -> None:
        if size > self.max_response_bytes:
            raise EgressPolicyError(f"Response exceeds {self.max_response_bytes} byte limit")
