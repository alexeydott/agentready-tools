"""Evidence and confidence model for crawler identity observations."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import StrEnum

logger = logging.getLogger(__name__)


class CrawlerIntent(StrEnum):
    DISCOVERY = "discovery"
    RENDER = "render"
    SYNTHETIC_PROBE = "synthetic_probe"
    PROVIDER_DATASET = "provider_dataset"


class IdentityConfidence(StrEnum):
    UNKNOWN = "unknown"
    OBSERVED = "observed"
    VERIFIED = "verified"
    DIAGNOSTIC = "diagnostic"
    PROVIDER_DATASET = "provider_dataset"


class IdentityEvidenceSource(StrEnum):
    ACCESS_LOG = "access_log"
    SYNTHETIC_PROBE = "synthetic_probe"
    PROVIDER_DATASET = "provider_dataset"


@dataclass(frozen=True, slots=True)
class CrawlerIdentityObservation:
    crawler: str | None
    user_agent: str | None
    intent: CrawlerIntent
    source: IdentityEvidenceSource
    confidence: IdentityConfidence
    client_ip: str | None = None
    verification_locator: str | None = None

    @property
    def is_verified(self) -> bool:
        return self.confidence is IdentityConfidence.VERIFIED

    def to_dict(self) -> dict[str, str | None]:
        return {
            "crawler": self.crawler,
            "user_agent": self.user_agent,
            "intent": self.intent.value,
            "source": self.source.value,
            "confidence": self.confidence.value,
            "client_ip": self.client_ip,
            "verification_locator": self.verification_locator,
        }


def _crawler_from_user_agent(user_agent: str | None, known_tokens: tuple[str, ...]) -> str | None:
    if not user_agent:
        return None
    lowered = user_agent.lower()
    return next((token for token in known_tokens if token.lower() in lowered), None)


def observe_crawler(
    user_agent: str | None,
    *,
    known_tokens: tuple[str, ...],
    intent: CrawlerIntent = CrawlerIntent.DISCOVERY,
    source: IdentityEvidenceSource = IdentityEvidenceSource.ACCESS_LOG,
    client_ip: str | None = None,
) -> CrawlerIdentityObservation:
    crawler = _crawler_from_user_agent(user_agent, known_tokens)
    confidence = IdentityConfidence.OBSERVED if crawler else IdentityConfidence.UNKNOWN
    observation = CrawlerIdentityObservation(crawler, user_agent, intent, source, confidence, client_ip)
    logger.debug("crawler observation crawler=%s confidence=%s source=%s", crawler, confidence, source)
    return observation


def verify_crawler(
    observation: CrawlerIdentityObservation,
    *,
    verification_locator: str | None = None,
    network_identity_verified: bool = False,
    provider_dataset_verified: bool = False,
) -> CrawlerIdentityObservation:
    """Upgrade identity only with independent evidence, never from User-Agent alone."""
    if observation.crawler is None:
        return observation
    if provider_dataset_verified:
        return CrawlerIdentityObservation(
            observation.crawler,
            observation.user_agent,
            CrawlerIntent.PROVIDER_DATASET,
            IdentityEvidenceSource.PROVIDER_DATASET,
            IdentityConfidence.PROVIDER_DATASET,
            observation.client_ip,
            verification_locator,
        )
    if not network_identity_verified:
        logger.debug("crawler verification refused crawler=%s reason=no independent evidence", observation.crawler)
        return observation
    return CrawlerIdentityObservation(
        observation.crawler,
        observation.user_agent,
        observation.intent,
        observation.source,
        IdentityConfidence.VERIFIED,
        observation.client_ip,
        verification_locator,
    )
