from __future__ import annotations

import json
import logging
from html.parser import HTMLParser
from typing import Any, Iterable

logger = logging.getLogger(__name__)

_ARTICLE_TYPES = {"article", "techarticle", "newsarticle", "blogposting", "scholarlyarticle"}


class _JsonLdHtmlParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.blocks: list[str] = []
        self._depth = 0
        self._buffer: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "script":
            return
        attributes = {key.lower(): (value or "") for key, value in attrs}
        if "ld+json" in attributes.get("type", "").lower():
            self._depth += 1
            self._buffer = []

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() != "script" or not self._depth:
            return
        self._depth -= 1
        raw = "".join(self._buffer).strip()
        if raw:
            self.blocks.append(raw)
        self._buffer = []

    def handle_data(self, data: str) -> None:
        if self._depth:
            self._buffer.append(data)


def parse_jsonld_blocks(blocks: Iterable[str]) -> tuple[list[dict[str, Any]], list[str]]:
    block_list = list(blocks)
    nodes: list[dict[str, Any]] = []
    errors: list[str] = []
    for raw in block_list:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            errors.append(exc.msg)
            continue
        items = data if isinstance(data, list) else [data]
        for item in items:
            if not isinstance(item, dict):
                continue
            graph = item.get("@graph")
            if isinstance(graph, list):
                nodes.extend(node for node in graph if isinstance(node, dict))
            else:
                nodes.append(item)
    logger.debug(
        "Parsed JSON-LD blocks: block_count=%d node_count=%d error_count=%d",
        len(block_list),
        len(nodes),
        len(errors),
    )
    return nodes, errors


def extract_jsonld_nodes(html_text: str) -> tuple[list[dict[str, Any]], list[str], int]:
    parser = _JsonLdHtmlParser()
    parser.feed(html_text)
    parser.close()
    nodes, errors = parse_jsonld_blocks(parser.blocks)
    return nodes, errors, len(parser.blocks)


def node_types(node: dict[str, Any]) -> set[str]:
    value = node.get("@type")
    values = value if isinstance(value, list) else [value]
    return {str(item).split("/")[-1].lower() for item in values if isinstance(item, str)}


def article_nodes(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [node for node in nodes if node_types(node) & _ARTICLE_TYPES]


def google_indexing_eligible_types(nodes: list[dict[str, Any]]) -> set[str]:
    eligible: set[str] = set()
    if any("jobposting" in node_types(node) for node in nodes):
        eligible.add("job-posting")

    nodes_by_id = {node.get("@id"): node for node in nodes if isinstance(node.get("@id"), str)}
    for node in nodes:
        if "videoobject" not in node_types(node):
            continue
        publications = node.get("publication")
        values = publications if isinstance(publications, list) else [publications]
        for value in values:
            candidate = value
            if isinstance(value, dict) and isinstance(value.get("@id"), str):
                candidate = nodes_by_id.get(value["@id"], value)
            elif isinstance(value, str):
                candidate = nodes_by_id.get(value)
            if isinstance(candidate, dict) and "broadcastevent" in node_types(candidate):
                eligible.add("broadcast-event")
                break
    logger.debug("Detected Google Indexing API eligible types: types=%s", sorted(eligible))
    return eligible
