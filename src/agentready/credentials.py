"""Secure credential storage for GA4/Search Console analytics checks.

Google APIs authenticate with OAuth2 service accounts (JSON key files), not
login/password pairs. This module stores the service-account JSON in the OS
credential vault (Windows Credential Manager via ``keyring``) and falls back
to ``GOOGLE_APPLICATION_CREDENTIALS`` when no stored credential exists.
"""
from __future__ import annotations

import json
import logging
import os

logger = logging.getLogger(__name__)

SERVICE_NAME = "agentready-tools"
ACCOUNT_KEY = "ga-gsc-service-account"


class CredentialsError(RuntimeError):
    pass


def _keyring():
    try:
        import keyring
    except ImportError as exc:
        raise CredentialsError("Install analytics extras: pip install 'agentready-tools[analytics]'") from exc
    return keyring


def store_service_account(path: str) -> None:
    """Read a service-account JSON file and store it in the OS credential vault."""
    with open(path, encoding="utf-8") as handle:
        content = handle.read()
    data = json.loads(content)
    if data.get("type") != "service_account" or not data.get("client_email"):
        raise CredentialsError("not a valid Google service-account JSON (expected type=service_account)")
    _keyring().set_password(SERVICE_NAME, ACCOUNT_KEY, content)
    logger.info("Stored GA/GSC service account for %s in the OS credential vault", data.get("client_email"))


def load_service_account_info() -> dict | None:
    """Return service-account info from the vault or GOOGLE_APPLICATION_CREDENTIALS."""
    try:
        stored = _keyring().get_password(SERVICE_NAME, ACCOUNT_KEY)
    except CredentialsError:
        stored = None
    if stored:
        logger.debug("Loaded GA/GSC credentials from the OS credential vault")
        return json.loads(stored)
    env_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if env_path and os.path.isfile(env_path):
        logger.debug("Loaded GA/GSC credentials from GOOGLE_APPLICATION_CREDENTIALS")
        with open(env_path, encoding="utf-8") as handle:
            return json.load(handle)
    return None


def credential_status() -> dict:
    """Describe the current credential configuration without exposing secrets."""
    info = load_service_account_info()
    if info is None:
        return {"configured": False, "source": None, "client_email": None}
    source = "keyring" if _keyring().get_password(SERVICE_NAME, ACCOUNT_KEY) else "env"
    return {"configured": True, "source": source, "client_email": info.get("client_email")}


def clear_service_account() -> bool:
    """Remove the stored credential from the OS vault. Returns True if removed."""
    kr = _keyring()
    if kr.get_password(SERVICE_NAME, ACCOUNT_KEY) is None:
        return False
    kr.delete_password(SERVICE_NAME, ACCOUNT_KEY)
    logger.info("Removed stored GA/GSC service account from the OS credential vault")
    return True
