"""Deterministic bounded fixtures shared by the opt-in WP6A scale tests."""
from __future__ import annotations

from agentready.audit_core.store import (
    LinkOccurrenceRecord,
    PageRecord,
    ResourceOccurrenceRecord,
)
from agentready.duplicates import ContentSignature


def page_records(size: int) -> tuple[PageRecord, ...]:
    return tuple(
        PageRecord(
            "scale-run",
            f"https://scale.example/{index}",
            f"https://scale.example/{index}",
            depth=index % 8,
            status_code=200 if index % 17 else 404,
            title=f"Page {index % 100}",
            canonical=f"https://scale.example/{index}",
            locally_indexable=index % 17 != 0,
            content_hash=f"hash-{index % 500}",
        )
        for index in range(size)
    )


def link_records(size: int) -> tuple[LinkOccurrenceRecord, ...]:
    return tuple(
        LinkOccurrenceRecord(
            "scale-run",
            f"https://scale.example/{index}",
            0,
            f"/{(index + 1) % size}",
            target_key=f"https://scale.example/{(index + 1) % size}",
            resolved_url=f"https://scale.example/{(index + 1) % size}",
            anchor_text=f"Page {(index + 1) % 50}",
        )
        for index in range(size)
    )


def resource_records(size: int) -> tuple[ResourceOccurrenceRecord, ...]:
    return tuple(
        ResourceOccurrenceRecord(
            "scale-run",
            f"https://scale.example/{index}",
            0,
            f"/asset-{index % 200}.js",
            "script",
            status_code=200,
            resolved_url=f"https://scale.example/asset-{index % 200}.js",
        )
        for index in range(size)
    )


def content_signatures(size: int) -> tuple[ContentSignature, ...]:
    return tuple(
        ContentSignature(
            f"https://scale.example/{index}",
            f"{index % 500:064x}",
            index << 48,
        )
        for index in range(size)
    )


def inventory_rows(size: int) -> tuple[dict[str, object], ...]:
    return tuple(
        {"url": f"https://scale.example/{index}", "status": "pass", "state_hash": f"state-{index % 1000}"}
        for index in range(size)
    )
