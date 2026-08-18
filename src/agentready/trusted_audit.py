"""CLI-only trusted local authenticated-audit boundary."""
from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlsplit

from .credentials import CredentialsError, load_secret
from .egress import TrustedLocalCredentialContext


@dataclass(frozen=True, slots=True)
class TrustedLocalAuditConfig:
    """Explicit local origin and vault reference; never contains secret material."""

    trusted_origin: str
    credential_ref: str
    header_name: str = "Authorization"
    scheme: str = "Bearer"

    def __post_init__(self) -> None:
        parsed = urlsplit(self.trusted_origin)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("trusted_origin must be an absolute HTTP(S) origin")
        if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
            raise ValueError("trusted_origin must not contain a path, query, or fragment")
        if parsed.hostname.lower() not in {"localhost", "127.0.0.1", "::1"}:
            raise ValueError("trusted authenticated audits require a loopback origin")
        if not self.credential_ref.strip():
            raise ValueError("credential_ref is required")
        if self.header_name.lower() not in {"authorization", "cookie", "x-api-key"}:
            raise ValueError("header_name is not allowed")
        if self.header_name.lower() == "authorization" and self.scheme.lower() not in {"bearer", "basic"}:
            raise ValueError("authorization scheme must be Bearer or Basic")

    @property
    def origin(self) -> str:
        parsed = urlsplit(self.trusted_origin)
        return f"{parsed.scheme}://{parsed.netloc}"

    def resolve(self) -> tuple[dict[str, str], TrustedLocalCredentialContext]:
        try:
            secret = load_secret(self.credential_ref)
        except CredentialsError:
            raise
        if not secret:
            raise CredentialsError(f"trusted-audit credential is not configured: {self.credential_ref}")
        value = f"{self.scheme} {secret}" if self.header_name.lower() == "authorization" else secret
        context = TrustedLocalCredentialContext(
            credential_ref=self.credential_ref,
            allowed_headers=frozenset({self.header_name.lower()}),
            allowed_origins=frozenset({self.origin}),
        )
        return {self.header_name: value}, context
