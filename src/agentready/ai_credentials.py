"""OS-vault credentials for the opt-in AI provider."""
from __future__ import annotations

import logging
import os
import re

logger = logging.getLogger(__name__)

SERVICE_NAME = "agentready-tools"
DEFAULT_CREDENTIAL_ID = "openai-api-key"
_CREDENTIAL_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


class AICredentialsError(RuntimeError):
    """Raised when AI credentials cannot be accessed or validated."""


def validate_credential_id(credential_id: str) -> str:
    if not isinstance(credential_id, str) or not _CREDENTIAL_ID.fullmatch(credential_id):
        raise AICredentialsError("credential_id must contain only letters, numbers, dot, underscore, or hyphen")
    return credential_id


def _keyring():
    try:
        import keyring
    except ImportError as exc:
        raise AICredentialsError("Install AI extras: pip install 'agentready-tools[ai]'") from exc
    return keyring


def store_api_key(api_key: str, credential_id: str = DEFAULT_CREDENTIAL_ID) -> None:
    """Store an API key in the operating system credential vault."""
    validate_credential_id(credential_id)
    if not isinstance(api_key, str) or not api_key.strip():
        raise AICredentialsError("API key must be non-empty")
    if any(char.isspace() for char in api_key):
        raise AICredentialsError("API key must not contain whitespace")
    _keyring().set_password(SERVICE_NAME, credential_id, api_key)
    logger.info("Stored AI credential %s in the OS credential vault", credential_id)


def load_api_key(credential_id: str = DEFAULT_CREDENTIAL_ID) -> tuple[str | None, str | None]:
    """Return ``(key, source)`` without logging or exposing the key."""
    validate_credential_id(credential_id)
    try:
        stored = _keyring().get_password(SERVICE_NAME, credential_id)
    except AICredentialsError:
        stored = None
    if stored:
        logger.debug("Loaded AI credential %s from the OS credential vault", credential_id)
        return stored, "keyring"
    fallback = os.environ.get("OPENAI_API_KEY")
    if fallback:
        logger.debug("Loaded AI credential %s from OPENAI_API_KEY", credential_id)
        return fallback, "env"
    return None, None


def api_key_status(credential_id: str = DEFAULT_CREDENTIAL_ID) -> dict[str, str | bool | None]:
    _, source = load_api_key(credential_id)
    return {"configured": source is not None, "source": source, "credential_id": credential_id}


def clear_api_key(credential_id: str = DEFAULT_CREDENTIAL_ID) -> bool:
    validate_credential_id(credential_id)
    kr = _keyring()
    if kr.get_password(SERVICE_NAME, credential_id) is None:
        return False
    kr.delete_password(SERVICE_NAME, credential_id)
    logger.info("Removed AI credential %s from the OS credential vault", credential_id)
    return True
