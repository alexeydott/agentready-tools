from __future__ import annotations

import base64
import binascii
import hashlib
import json
import logging
import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from html.parser import HTMLParser
from typing import Any
from urllib import robotparser
from urllib.parse import urljoin, urlsplit

import dns.exception
import dns.resolver

from .http import Fetched, FetchError, HttpClient
from .models import CheckResult, Evidence
from .registry import CheckSpec
from .remediation import remediation_for
from .structured_data import article_nodes as _article_nodes
from .structured_data import node_types as _types
from .structured_data import parse_jsonld_blocks
from .target import Target, ip_is_non_public, resolved_ips

logger = logging.getLogger(__name__)

AI_BOTS = {
    "gptbot",
    "chatgpt-user",
    "oai-searchbot",
    "claudebot",
    "claude-searchbot",
    "claude-user",
    "perplexitybot",
    "perplexity-user",
    "google-extended",
    "googleother",
    "googleother-image",
    "googleother-video",
    "applebot-extended",
    "meta-externalagent",
    "amazonbot",
    "ccbot",
    "bytespider",
    "cohere-ai",
}

_CONTENT_SIGNAL_KEYS = {"search", "ai-input", "ai-train", "use"}
_CONTENT_SIGNAL_BOOL = {"yes", "no"}
_CONTENT_SIGNAL_USE = {"immediate", "reference", "full"}
_SKILL_NAME = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_DATE_VERSION = re.compile(r"^\d{4}-\d{2}-\d{2}$")


@dataclass(slots=True)
class CheckContext:
    target: Target
    client: HttpClient
    content_url: str
    commerce_url: str | None = None
    verify_skill_digests: bool = False


def _url(origin: str, path: str) -> str:
    return urljoin(origin.rstrip("/") + "/", path.lstrip("/"))


def _elapsed(start: float) -> int:
    return max(0, round((time.perf_counter() - start) * 1000))


def _result(
    spec: CheckSpec,
    target_url: str,
    status: str,
    details: str,
    start: float,
    evidence: list[Evidence] | None = None,
) -> CheckResult:
    return CheckResult(
        id=spec.id,
        title=spec.title,
        category=spec.category,
        status=status,  # type: ignore[arg-type]
        scored=spec.scored,
        details=details,
        duration_ms=_elapsed(start),
        evidence=evidence or [],
        remediation=None if status == "pass" else remediation_for(spec, target_url),
        experimental=spec.experimental,
        supplemental=spec.supplemental,
        geo_scored=spec.geo_scored,
    )


def _json(response: Fetched) -> tuple[Any | None, str | None]:
    if response.status_code != 200:
        return None, f"HTTP {response.status_code}"
    ct = response.content_type
    if ct not in {"application/json", "application/ld+json"} and not ct.endswith("+json"):
        return None, f"expected JSON content type, got {ct or 'missing'}"
    try:
        return json.loads(response.text), None
    except json.JSONDecodeError as exc:
        return None, f"invalid JSON: {exc.msg}"


def _fetch(ctx: CheckContext, url: str, headers: dict[str, str] | None = None, *, use_cache: bool = True) -> Fetched:
    return ctx.client.get(url, headers=headers, use_cache=use_cache)


def _fetch_failure(spec: CheckSpec, ctx: CheckContext, start: float, action: str, exc: Exception) -> CheckResult:
    return _result(spec, ctx.target.url, "fail", str(exc), start, [Evidence(action=action, url=ctx.target.url, finding=str(exc))])


def _robots(ctx: CheckContext) -> Fetched:
    return _fetch(ctx, _url(ctx.target.origin, "/robots.txt"))


def _homepage(ctx: CheckContext) -> Fetched:
    return _fetch(ctx, ctx.target.url)


def check_robots(ctx: CheckContext, spec: CheckSpec) -> CheckResult:
    start = time.perf_counter()
    url = _url(ctx.target.origin, "/robots.txt")
    try:
        r = _fetch(ctx, url)
    except FetchError as exc:
        return _fetch_failure(spec, ctx, start, "fetch robots.txt", exc)
    valid_ct = not r.content_type or r.content_type == "text/plain"
    has_agent = bool(re.search(r"(?im)^\s*user-agent\s*:\s*\S+", r.text))
    ok = r.status_code == 200 and valid_ct and has_agent
    details = "valid robots.txt with User-agent directive" if ok else "robots.txt must be HTTP 200 plain text and contain a User-agent directive"
    return _result(spec, ctx.target.url, "pass" if ok else "fail", details, start, [r.evidence("fetch robots.txt")])


def check_sitemap(ctx: CheckContext, spec: CheckSpec) -> CheckResult:
    start = time.perf_counter()
    candidates = [_url(ctx.target.origin, "/sitemap.xml")]
    try:
        rr = _robots(ctx)
        for line in rr.text.splitlines():
            if line.lower().startswith("sitemap:"):
                value = line.split(":", 1)[1].strip()
                if value:
                    candidates.append(urljoin(ctx.target.origin + "/", value))
                    break
    except FetchError:
        pass
    evidence: list[Evidence] = []
    for url in dict.fromkeys(candidates):
        try:
            r = _fetch(ctx, url)
        except FetchError as exc:
            evidence.append(Evidence(action="fetch sitemap", url=url, finding=str(exc)))
            continue
        evidence.append(r.evidence("fetch sitemap"))
        body = r.text.lstrip().lower()
        xmlish = body.startswith(("<?xml", "<urlset", "<sitemapindex"))
        ctype = r.content_type in {"application/xml", "text/xml", "application/rss+xml"} or r.content_type.endswith("+xml")
        if r.status_code == 200 and ctype and xmlish:
            return _result(spec, ctx.target.url, "pass", f"valid sitemap found at {r.url}", start, evidence)
    return _result(spec, ctx.target.url, "fail", "no valid XML sitemap found at /sitemap.xml or first robots.txt Sitemap directive", start, evidence)


def check_link_headers(ctx: CheckContext, spec: CheckSpec) -> CheckResult:
    start = time.perf_counter()
    try:
        r = _homepage(ctx)
    except FetchError as exc:
        return _fetch_failure(spec, ctx, start, "fetch target for Link headers", exc)
    raw = r.headers.get("link", "")
    relations = re.findall(r"<([^>]+)>\s*;[^,]*?\brel\s*=\s*(?:\"([^\"]+)\"|([^;,\s]+))", raw, flags=re.IGNORECASE)
    recognized: list[str] = []
    for href, quoted, bare in relations:
        rels = (quoted or bare).lower().split()
        if any(x in {"api-catalog", "service-desc", "service-doc", "alternate"} for x in rels):
            recognized.append(f"{href} rel={' '.join(rels)}")
    if recognized:
        return _result(spec, ctx.target.url, "pass", "recognized discovery Link header: " + recognized[0], start, [r.evidence("inspect Link headers", preview=False)])
    detail = "no recognized agent/API discovery relation in Link header"
    return _result(spec, ctx.target.url, "fail", detail, start, [r.evidence("inspect Link headers", preview=False)])


def check_dns_aid(ctx: CheckContext, spec: CheckSpec) -> CheckResult:
    start = time.perf_counter()
    try:
        ips = resolved_ips(ctx.target.hostname, ctx.target.port)
        if ips and all(ip_is_non_public(ip) for ip in ips):
            return _result(spec, ctx.target.url, "skip", "DNS-AID skipped for local/private target", start)
    except OSError as exc:
        # DNS-AID is supplemental: resolver failures must not prevent the
        # regular DNS record checks from running, but remain diagnosable.
        logger.debug(
            "DNS-AID private-target probe failed hostname=%s error=%s",
            ctx.target.hostname,
            type(exc).__name__,
        )
    qname = f"_index._agents.{ctx.target.hostname.rstrip('.')}"
    findings: list[str] = []
    evidence: list[Evidence] = []
    for qtype in ("HTTPS", "SVCB"):
        try:
            answers = dns.resolver.resolve(qname, qtype, lifetime=ctx.client.timeout)
            values = [a.to_text() for a in answers]
            if values:
                findings.extend(values)
                evidence.append(Evidence(action=f"DNS {qtype} query", url=qname, finding="; ".join(values)[:1200]))
        except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN, dns.resolver.NoNameservers, dns.exception.Timeout) as exc:
            evidence.append(Evidence(action=f"DNS {qtype} query", url=qname, finding=type(exc).__name__))
    if findings:
        return _result(spec, ctx.target.url, "pass", f"DNS-AID service record found at {qname}", start, evidence)
    return _result(spec, ctx.target.url, "warn", f"no SVCB/HTTPS DNS-AID record found at {qname}; draft protocol, DNSSEC AD status not verified", start, evidence)


def check_markdown(ctx: CheckContext, spec: CheckSpec) -> CheckResult:
    start = time.perf_counter()
    try:
        r = _fetch(ctx, ctx.content_url, {"Accept": "text/markdown"})
    except FetchError as exc:
        return _fetch_failure(spec, ctx, start, "request Markdown representation", exc)
    body = r.text.lstrip()
    htmlish = body[:500].lower().startswith("<!doctype html") or bool(re.search(r"(?is)^\s*<html\b", body[:1000]))
    ok = r.status_code == 200 and r.content_type == "text/markdown" and bool(body.strip()) and not htmlish
    details = "Accept: text/markdown returned a non-empty Markdown representation" if ok else f"expected HTTP 200 text/markdown non-HTML response; got {r.status_code} {r.content_type or 'no content-type'}"
    return _result(spec, ctx.target.url, "pass" if ok else "fail", details, start, [r.evidence("request Markdown representation")])


def _robots_user_agents(text: str) -> set[str]:
    out: set[str] = set()
    for m in re.finditer(r"(?im)^\s*user-agent\s*:\s*([^#\r\n]+)", text):
        out.add(m.group(1).strip().lower())
    return out


def check_ai_bot_rules(ctx: CheckContext, spec: CheckSpec) -> CheckResult:
    start = time.perf_counter()
    try:
        r = _robots(ctx)
    except FetchError as exc:
        return _fetch_failure(spec, ctx, start, "inspect AI bot robots rules", exc)
    agents = _robots_user_agents(r.text)
    matches = sorted(agents & AI_BOTS)
    if matches:
        return _result(spec, ctx.target.url, "pass", "explicit AI agent/crawler group(s): " + ", ".join(matches), start, [r.evidence("inspect AI bot robots rules")])
    wildcard = "*" in agents
    detail = "robots.txt has only generic User-agent policy; no maintained AI bot/user-agent is named explicitly" if wildcard else "no maintained AI bot/user-agent is named explicitly in robots.txt"
    return _result(spec, ctx.target.url, "fail", detail, start, [r.evidence("inspect AI bot robots rules")])


def _parse_content_signal(raw: str) -> tuple[bool, dict[str, str], str]:
    if not raw.strip():
        return False, {}, "empty"
    values: dict[str, str] = {}
    for item in re.split(r"[,;]", raw):
        item = item.strip()
        if not item or "=" not in item:
            continue
        k, v = [x.strip().lower() for x in item.split("=", 1)]
        if k in _CONTENT_SIGNAL_KEYS:
            values[k] = v
    if not values:
        return False, {}, "no recognized directives"
    for k, v in values.items():
        if k == "use":
            if v not in _CONTENT_SIGNAL_USE:
                return False, values, f"invalid use={v}"
        elif v not in _CONTENT_SIGNAL_BOOL:
            return False, values, f"invalid {k}={v}"
    return True, values, "valid"


def check_content_signals(ctx: CheckContext, spec: CheckSpec) -> CheckResult:
    start = time.perf_counter()
    evidence: list[Evidence] = []
    candidates: list[tuple[str, str]] = []
    try:
        r = _fetch(ctx, ctx.content_url)
        if "content-signal" in r.headers:
            candidates.append(("HTTP header", r.headers["content-signal"]))
        evidence.append(r.evidence("inspect Content-Signal header", preview=False))
    except FetchError as exc:
        evidence.append(Evidence(action="inspect Content-Signal header", url=ctx.content_url, finding=str(exc)))
    try:
        rr = _robots(ctx)
        for m in re.finditer(r"(?im)^\s*content-signal\s*:\s*([^\r\n#]+)", rr.text):
            candidates.append(("robots.txt", m.group(1).strip()))
        evidence.append(rr.evidence("inspect Content-Signal in robots.txt"))
    except FetchError as exc:
        evidence.append(Evidence(action="inspect Content-Signal in robots.txt", url=_url(ctx.target.origin, "/robots.txt"), finding=str(exc)))
    invalid: list[str] = []
    for source, raw in candidates:
        ok, values, why = _parse_content_signal(raw)
        if ok:
            policy = ", ".join(f"{k}={v}" for k, v in values.items())
            return _result(spec, ctx.target.url, "pass", f"valid explicit Content-Signal policy from {source}: {policy}", start, evidence)
        invalid.append(f"{source}: {why}")
    details = "no explicit Content-Signal policy found" if not candidates else "Content-Signal found but invalid: " + "; ".join(invalid)
    return _result(spec, ctx.target.url, "fail", details, start, evidence)


def check_web_bot_auth(ctx: CheckContext, spec: CheckSpec) -> CheckResult:
    start = time.perf_counter()
    url = _url(ctx.target.origin, "/.well-known/http-message-signatures-directory")
    try:
        r = _fetch(ctx, url)
    except FetchError as exc:
        return _fetch_failure(spec, ctx, start, "fetch Web Bot Auth key directory", exc)
    data, err = _json(r)
    keys = data if isinstance(data, list) else data.get("keys") if isinstance(data, dict) else None
    ok = not err and isinstance(keys, list) and any(isinstance(x, dict) and (x.get("kid") or x.get("kty")) for x in keys)
    detail = "JWK-like public key directory found" if ok else f"invalid Web Bot Auth key directory: {err or 'missing keys/kid/kty'}"
    return _result(spec, ctx.target.url, "pass" if ok else "fail", detail, start, [r.evidence("fetch Web Bot Auth key directory")])


def check_api_catalog(ctx: CheckContext, spec: CheckSpec) -> CheckResult:
    start = time.perf_counter()
    url = _url(ctx.target.origin, "/.well-known/api-catalog")
    try:
        r = _fetch(ctx, url)
    except FetchError as exc:
        return _fetch_failure(spec, ctx, start, "fetch API Catalog", exc)
    data, err = _json(r)
    linkset = data if isinstance(data, list) else data.get("linkset") if isinstance(data, dict) else None
    ok = not err and isinstance(linkset, list) and len(linkset) > 0
    detail = "RFC 9727-style API Catalog linkset found" if ok else f"invalid API Catalog: {err or 'missing non-empty linkset'}"
    return _result(spec, ctx.target.url, "pass" if ok else "fail", detail, start, [r.evidence("fetch API Catalog")])


def check_oauth_discovery(ctx: CheckContext, spec: CheckSpec) -> CheckResult:
    start = time.perf_counter()
    url = _url(ctx.target.origin, "/.well-known/oauth-authorization-server")
    try:
        r = _fetch(ctx, url)
    except FetchError as exc:
        return _fetch_failure(spec, ctx, start, "fetch OAuth Authorization Server Metadata", exc)
    data, err = _json(r)
    issuer = data.get("issuer") if isinstance(data, dict) else None
    ok = not err and isinstance(issuer, str) and bool(issuer.strip())
    detail = f"OAuth issuer: {issuer}" if ok else f"invalid OAuth Authorization Server Metadata: {err or 'missing issuer'}"
    return _result(spec, ctx.target.url, "pass" if ok else "fail", detail, start, [r.evidence("fetch OAuth Authorization Server Metadata")])


def check_oauth_protected(ctx: CheckContext, spec: CheckSpec) -> CheckResult:
    start = time.perf_counter()
    url = _url(ctx.target.origin, "/.well-known/oauth-protected-resource")
    try:
        r = _fetch(ctx, url)
    except FetchError as exc:
        return _fetch_failure(spec, ctx, start, "fetch OAuth Protected Resource Metadata", exc)
    data, err = _json(r)
    resource = data.get("resource") if isinstance(data, dict) else None
    ok = not err and isinstance(resource, str) and bool(resource.strip())
    detail = f"OAuth protected resource: {resource}" if ok else f"invalid OAuth Protected Resource Metadata: {err or 'missing resource'}"
    return _result(spec, ctx.target.url, "pass" if ok else "fail", detail, start, [r.evidence("fetch OAuth Protected Resource Metadata")])


def check_auth_md(ctx: CheckContext, spec: CheckSpec) -> CheckResult:
    start = time.perf_counter()
    url = _url(ctx.target.origin, "/auth.md")
    try:
        r = _fetch(ctx, url)
    except FetchError as exc:
        return _result(spec, ctx.target.url, "warn", f"auth.md not verifiable: {exc}", start, [Evidence(action="fetch auth.md", url=url, finding=str(exc))])
    ct_ok = r.content_type in {"text/markdown", "text/plain"}
    heading = bool(re.search(r"(?im)^#\s*auth\.md\s*$", r.text))
    authoritative = "/.well-known/oauth-protected-resource" in r.text or "agent_auth" in r.text.lower()
    ok = r.status_code == 200 and ct_ok and heading and authoritative
    detail = "auth.md points agents toward structured authorization metadata" if ok else "auth.md is absent or does not contain the expected heading and OAuth protected-resource pointer"
    return _result(spec, ctx.target.url, "pass" if ok else "warn", detail, start, [r.evidence("fetch auth.md")])


def check_mcp_card(ctx: CheckContext, spec: CheckSpec) -> CheckResult:
    start = time.perf_counter()
    url = _url(ctx.target.origin, "/.well-known/mcp/server-card.json")
    try:
        r = _fetch(ctx, url)
    except FetchError as exc:
        return _fetch_failure(spec, ctx, start, "fetch MCP Server Card", exc)
    data, err = _json(r)
    info = data.get("serverInfo") if isinstance(data, dict) else None
    transport = data.get("transport") if isinstance(data, dict) else None
    ok = (
        not err
        and isinstance(data, dict)
        and isinstance(info, dict)
        and isinstance(info.get("name"), str)
        and bool(info["name"].strip())
        and isinstance(transport, (str, dict))
    )
    detail = f"MCP server card for {info.get('name') if isinstance(info, dict) else '?'}" if ok else f"invalid MCP Server Card: {err or 'requires serverInfo.name and transport'}"
    return _result(spec, ctx.target.url, "pass" if ok else "fail", detail, start, [r.evidence("fetch MCP Server Card")])


def check_a2a_card(ctx: CheckContext, spec: CheckSpec) -> CheckResult:
    start = time.perf_counter()
    url = _url(ctx.target.origin, "/.well-known/agent-card.json")
    try:
        r = _fetch(ctx, url)
    except FetchError as exc:
        return _fetch_failure(spec, ctx, start, "fetch A2A Agent Card", exc)
    data, err = _json(r)
    errors: list[str] = []
    if not isinstance(data, dict):
        errors.append("card is not an object")
    else:
        for k in ("name", "description", "version"):
            if not isinstance(data.get(k), str) or not data[k].strip():
                errors.append(f"missing/invalid {k}")
        if not isinstance(data.get("capabilities"), dict):
            errors.append("missing/invalid capabilities")
        for k in ("defaultInputModes", "defaultOutputModes"):
            if not isinstance(data.get(k), list) or not data[k] or not all(isinstance(x, str) and x for x in data[k]):
                errors.append(f"missing/invalid {k}")

        interfaces = data.get("supportedInterfaces")
        if not isinstance(interfaces, list) or not interfaces:
            errors.append("supportedInterfaces must be a non-empty array")
        else:
            for i, interface in enumerate(interfaces):
                if not isinstance(interface, dict):
                    errors.append(f"supportedInterfaces[{i}] is not an object")
                    continue
                for field in ("url", "protocolBinding", "protocolVersion"):
                    if not isinstance(interface.get(field), str) or not interface[field].strip():
                        errors.append(f"supportedInterfaces[{i}].{field} missing/invalid")

        skills = data.get("skills")
        if not isinstance(skills, list) or not skills:
            errors.append("skills must be a non-empty array")
        else:
            for i, skill in enumerate(skills):
                if not isinstance(skill, dict):
                    errors.append(f"skills[{i}] is not an object")
                    continue
                for field in ("id", "name", "description"):
                    if not isinstance(skill.get(field), str) or not skill[field].strip():
                        errors.append(f"skills[{i}].{field} missing/invalid")
                if not isinstance(skill.get("tags"), list) or not all(isinstance(x, str) for x in skill.get("tags", [])):
                    errors.append(f"skills[{i}].tags missing/invalid")
    ok = not err and not errors
    detail = "A2A Agent Card matches the current core discovery shape" if ok else f"invalid A2A Agent Card: {err or '; '.join(errors[:6])}"
    return _result(spec, ctx.target.url, "pass" if ok else "fail", detail, start, [r.evidence("fetch A2A Agent Card")])

def _valid_skill_entry(entry: Any) -> tuple[bool, str]:
    if not isinstance(entry, dict):
        return False, "entry is not an object"
    name = entry.get("name")
    if not isinstance(name, str) or not _SKILL_NAME.fullmatch(name) or "--" in name:
        return False, "invalid skill name"
    if entry.get("type") not in {"skill-md", "archive"}:
        return False, "invalid skill type"
    desc = entry.get("description")
    if not isinstance(desc, str) or not (1 <= len(desc) <= 1024):
        return False, "invalid description"
    if not isinstance(entry.get("url"), str) or not entry["url"].startswith(("http://", "https://", "/")):
        return False, "invalid URL"
    if not isinstance(entry.get("digest"), str) or not _SHA256.fullmatch(entry["digest"]):
        return False, "invalid SHA-256 digest"
    return True, "ok"


def check_agent_skills(ctx: CheckContext, spec: CheckSpec) -> CheckResult:
    start = time.perf_counter()
    url = _url(ctx.target.origin, "/.well-known/agent-skills/index.json")
    try:
        r = _fetch(ctx, url)
    except FetchError as exc:
        return _fetch_failure(spec, ctx, start, "fetch Agent Skills index", exc)
    data, err = _json(r)
    errors: list[str] = []
    skills: list[Any] = []
    if isinstance(data, dict):
        schema = data.get("$schema", "")
        if not isinstance(schema, str) or "/0.2.0/" not in schema:
            errors.append("$schema is not Agent Skills discovery v0.2.0")
        raw_skills = data.get("skills")
        if isinstance(raw_skills, list) and raw_skills:
            skills = raw_skills
        else:
            errors.append("skills must be a non-empty array")
    else:
        errors.append("index is not an object")
    names: set[str] = set()
    for i, skill in enumerate(skills):
        ok, why = _valid_skill_entry(skill)
        if not ok:
            errors.append(f"skills[{i}]: {why}")
            continue
        name = skill["name"]
        if name in names:
            errors.append(f"duplicate skill name {name}")
        names.add(name)
    evidence = [r.evidence("fetch Agent Skills index")]
    if not errors and ctx.verify_skill_digests:
        for skill in skills:
            artifact_url = urljoin(ctx.target.origin + "/", skill["url"])
            try:
                artifact = _fetch(ctx, artifact_url)
                actual = hashlib.sha256(artifact.body).hexdigest()
                evidence.append(artifact.evidence(f"verify digest for {skill['name']}", preview=False, finding=f"sha256={actual}"))
                if artifact.status_code != 200 or actual != skill["digest"]:
                    errors.append(f"digest mismatch for {skill['name']}")
            except FetchError as exc:
                errors.append(f"could not fetch {skill['name']}: {exc}")
    ok = not err and not errors
    detail = f"valid Agent Skills v0.2.0 index with {len(skills)} skill(s)" if ok else f"invalid Agent Skills index: {err or '; '.join(errors[:5])}"
    return _result(spec, ctx.target.url, "pass" if ok else "fail", detail, start, evidence)


def check_webmcp(ctx: CheckContext, spec: CheckSpec) -> CheckResult:
    start = time.perf_counter()
    evidence: list[Evidence] = []
    url = _url(ctx.target.origin, "/.well-known/webmcp")
    try:
        r = _fetch(ctx, url)
        evidence.append(r.evidence("fetch WebMCP discovery"))
        data, err = _json(r)
        if not err and isinstance(data, dict) and data:
            return _result(spec, ctx.target.url, "pass", "WebMCP discovery JSON found", start, evidence)
    except FetchError as exc:
        evidence.append(Evidence(action="fetch WebMCP discovery", url=url, finding=str(exc)))
    try:
        home = _homepage(ctx)
        evidence.append(home.evidence("inspect inline WebMCP registration"))
        body = home.text
        if "navigator.modelContext" in body or "modelContext.registerTool" in body or "modelContext.register" in body:
            return _result(spec, ctx.target.url, "pass", "inline WebMCP/modelContext registration signal found", start, evidence)
    except FetchError as exc:
        evidence.append(Evidence(action="inspect inline WebMCP registration", url=ctx.target.url, finding=str(exc)))
    return _result(spec, ctx.target.url, "warn", "WebMCP not proven by fetch-only inspection; external/runtime JavaScript may still register tools", start, evidence)


def _decode_b64_json(value: str) -> Any | None:
    raw = value.strip()
    padding = "=" * (-len(raw) % 4)
    for decoder in (base64.b64decode, base64.urlsafe_b64decode):
        try:
            return json.loads(decoder(raw + padding).decode("utf-8"))
        except (binascii.Error, UnicodeDecodeError, json.JSONDecodeError) as exc:
            logger.debug(
                "x402 token decode attempt failed decoder=%s error=%s",
                decoder.__name__,
                type(exc).__name__,
            )
            continue
    return None


def check_x402(ctx: CheckContext, spec: CheckSpec) -> CheckResult:
    start = time.perf_counter()
    if not ctx.commerce_url:
        return _result(spec, ctx.target.url, "skip", "x402 requires --commerce-url pointing to a real paid resource; no payment is ever attempted", start)
    try:
        r = _fetch(ctx, ctx.commerce_url, use_cache=False)
    except FetchError as exc:
        return _fetch_failure(spec, ctx, start, "probe x402 paid resource without payment", exc)
    encoded = r.headers.get("payment-required", "")
    data = _decode_b64_json(encoded) if encoded else None
    ok = r.status_code == 402 and isinstance(data, dict) and data.get("x402Version") == 2 and isinstance(data.get("accepts"), list) and bool(data["accepts"])
    detail = "valid x402 v2 HTTP 402 challenge found" if ok else "expected HTTP 402 with PAYMENT-REQUIRED Base64 JSON containing x402Version=2 and a non-empty accepts array"
    return _result(spec, ctx.target.url, "pass" if ok else "fail", detail, start, [r.evidence("probe x402 paid resource without payment", preview=False)])


def check_mpp(ctx: CheckContext, spec: CheckSpec) -> CheckResult:
    start = time.perf_counter()
    if not ctx.commerce_url:
        return _result(spec, ctx.target.url, "skip", "MPP requires --commerce-url pointing to a real paid resource; no credentials/payment are ever sent", start)
    try:
        r = _fetch(ctx, ctx.commerce_url, use_cache=False)
    except FetchError as exc:
        return _fetch_failure(spec, ctx, start, "probe MPP resource without payment", exc)
    challenge = r.headers.get("www-authenticate", "")
    ok = r.status_code == 402 and bool(re.search(r"(?:^|,)\s*Payment(?:\s|$)", challenge, flags=re.IGNORECASE))
    detail = "HTTP 402 Payment authentication challenge found" if ok else "expected HTTP 402 with WWW-Authenticate: Payment challenge"
    return _result(spec, ctx.target.url, "pass" if ok else "fail", detail, start, [r.evidence("probe MPP resource without payment", preview=False)])


def check_ucp(ctx: CheckContext, spec: CheckSpec) -> CheckResult:
    start = time.perf_counter()
    url = _url(ctx.target.origin, "/.well-known/ucp")
    try:
        r = _fetch(ctx, url)
    except FetchError as exc:
        return _result(spec, ctx.target.url, "warn", f"UCP discovery not found/verifiable: {exc}", start, [Evidence(action="fetch UCP profile", url=url, finding=str(exc))])
    data, err = _json(r)
    ucp = data.get("ucp") if isinstance(data, dict) else None
    version = ucp.get("version") if isinstance(ucp, dict) else None
    services = ucp.get("services") if isinstance(ucp, dict) else None
    ok = (
        not err
        and isinstance(version, str)
        and bool(_DATE_VERSION.fullmatch(version))
        and isinstance(services, dict)
        and bool(services)
    )
    detail = f"UCP business profile version {version} with {len(services)} service(s)" if ok else f"UCP profile absent/invalid: {err or 'requires ucp.version (YYYY-MM-DD) and a non-empty services object'}"
    return _result(spec, ctx.target.url, "pass" if ok else "warn", detail, start, [r.evidence("fetch UCP profile")])


def check_acp(ctx: CheckContext, spec: CheckSpec) -> CheckResult:
    start = time.perf_counter()
    paths = ("/.well-known/acp.json", "/.well-known/acp", "/.well-known/acp/config.json")
    evidence: list[Evidence] = []
    for path in paths:
        url = _url(ctx.target.origin, path)
        try:
            r = _fetch(ctx, url)
        except FetchError as exc:
            evidence.append(Evidence(action="probe ACP discovery", url=url, finding=str(exc)))
            continue
        evidence.append(r.evidence("probe ACP discovery"))
        data, err = _json(r)
        if not err and isinstance(data, dict) and data and any(k.lower() in {"acp", "version", "capabilities", "checkout", "endpoints", "merchant", "agenticcommerce"} for k in data):
            return _result(spec, ctx.target.url, "pass", f"ACP-like discovery JSON found at {path}; detection is heuristic because public discovery is still evolving", start, evidence)
    return _result(spec, ctx.target.url, "warn", "no ACP-like discovery document found at common experimental paths; this is informational, not a standards-conformance failure", start, evidence)


def check_llms_txt(ctx: CheckContext, spec: CheckSpec) -> CheckResult:
    start = time.perf_counter()
    url = _url(ctx.target.origin, "/llms.txt")
    try:
        r = _fetch(ctx, url)
    except FetchError as exc:
        return _fetch_failure(spec, ctx, start, "fetch llms.txt", exc)
    body = r.text.lstrip()
    htmlish = body[:500].lower().startswith("<!doctype html") or bool(re.search(r"(?is)^\s*<html\b", body[:1000]))
    valid_ct = r.content_type in {"text/plain", "text/markdown", "text/x-markdown"} or not r.content_type
    links = re.findall(r"\[([^\]]+)\]\(([^)]+)\)", body)
    has_h1 = bool(re.search(r"(?m)^#\s+\S+", body))
    nested = [href for _label, href in links if href.lower().split("?", 1)[0].endswith("/llms.txt") or href.lower().split("?", 1)[0].endswith("llms.txt")]
    evidence = [r.evidence("fetch llms.txt", finding=f"bytes={len(r.body)} links={len(links)} nested_llms={len(nested)}")]
    evidence[0].metrics = {"bytes": len(r.body), "link_count": len(links), "nested_llms_count": len(nested)}
    base_ok = r.status_code == 200 and valid_ct and bool(body.strip()) and not htmlish and has_h1 and bool(links)
    if not base_ok:
        detail = "llms.txt must be HTTP 200 text, non-HTML, include an H1 title and at least one Markdown link"
        return _result(spec, ctx.target.url, "fail", detail, start, evidence)
    # Cloudflare's docs case study warns that giant flat llms.txt files force agents into grep loops.
    oversized = len(r.body) > 256 * 1024 or len(links) > 500
    if oversized and not nested:
        return _result(
            spec, ctx.target.url, "warn",
            f"valid llms.txt with {len(links)} links, but it is large/flat; consider hierarchical per-section llms.txt files",
            start, evidence,
        )
    detail = f"valid llms.txt with {len(links)} link(s)"
    if nested:
        detail += f" and {len(nested)} hierarchical llms.txt reference(s)"
    return _result(spec, ctx.target.url, "pass", detail, start, evidence)


def _index_md_url(value: str) -> str:
    p = urlsplit(value)
    path = p.path or "/"
    if not path.endswith("/"):
        path += "/"
    path += "index.md"
    return p._replace(path=path, query="", fragment="").geturl()


def check_markdown_index_fallback(ctx: CheckContext, spec: CheckSpec) -> CheckResult:
    start = time.perf_counter()
    url = _index_md_url(ctx.content_url)
    try:
        r = _fetch(ctx, url)
    except FetchError as exc:
        return _fetch_failure(spec, ctx, start, "fetch /index.md fallback", exc)
    body = r.text.lstrip()
    htmlish = body[:500].lower().startswith("<!doctype html") or bool(re.search(r"(?is)^\s*<html\b", body[:1000]))
    ok = r.status_code == 200 and r.content_type in {"text/markdown", "text/plain", "text/x-markdown"} and bool(body.strip()) and not htmlish
    detail = f"agent-friendly Markdown fallback available at {r.url}" if ok else f"no valid Markdown /index.md fallback at {url}"
    return _result(spec, ctx.target.url, "pass" if ok else "fail", detail, start, [r.evidence("fetch /index.md fallback")])


def check_markdown_efficiency(ctx: CheckContext, spec: CheckSpec) -> CheckResult:
    start = time.perf_counter()
    evidence: list[Evidence] = []
    try:
        html_r = _fetch(ctx, ctx.content_url, {"Accept": "text/html,application/xhtml+xml"})
        md_r = _fetch(ctx, ctx.content_url, {"Accept": "text/markdown"})
    except FetchError as exc:
        return _fetch_failure(spec, ctx, start, "compare HTML and Markdown representations", exc)
    evidence.extend([html_r.evidence("fetch HTML for efficiency", preview=False), md_r.evidence("fetch Markdown for efficiency", preview=False)])
    html_bytes = len(html_r.body)
    md_bytes = len(md_r.body)
    valid_md = md_r.status_code == 200 and md_r.content_type == "text/markdown" and md_bytes > 0
    if not valid_md or html_bytes == 0:
        return _result(spec, ctx.target.url, "warn", "cannot compare efficiency until a valid Markdown representation and HTML baseline are both available", start, evidence)
    reduction = round((1 - (md_bytes / html_bytes)) * 100, 1)
    metrics = {"html_bytes": html_bytes, "markdown_bytes": md_bytes, "byte_reduction_percent": reduction}
    evidence[1].metrics = metrics
    if reduction >= 0:
        return _result(spec, ctx.target.url, "pass", f"Markdown is {reduction:.1f}% smaller than HTML by bytes (token-efficiency proxy, not a tokenizer measurement)", start, evidence)
    return _result(spec, ctx.target.url, "warn", f"Markdown is {-reduction:.1f}% larger than HTML by bytes; inspect conversion noise (byte proxy, not token count)", start, evidence)


_SEARCH_INDEX_UAS = ("OAI-SearchBot", "Claude-SearchBot", "PerplexityBot", "Googlebot")
_USER_FETCH_UAS = ("ChatGPT-User", "Claude-User", "Perplexity-User")
_TRAINING_UAS = ("GPTBot", "ClaudeBot")
_ROBOTS_ONLY_AI_TOKENS = ("Google-Extended",)


class _HTMLAuditParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.jsonld: list[str] = []
        self.paragraphs: list[str] = []
        self.visible_chunks: list[str] = []
        self.time_datetimes: list[str] = []
        self.article_elements = 0
        self.table_count = 0
        self.code_blocks = 0
        self.list_items = 0
        self.heading_count = 0
        self.headings: list[str] = []
        self.canonical_links: list[str] = []
        self.meta_robots: list[str] = []
        self.og_type: str | None = None
        self._jsonld_depth = 0
        self._jsonld_buf: list[str] = []
        self._p_depth = 0
        self._p_buf: list[str] = []
        self._hidden_depth = 0
        self._pre_depth = 0
        self._heading_depth = 0
        self._heading_buf: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        amap = {k.lower(): (v or "") for k, v in attrs}
        if tag in {"script", "style", "noscript", "svg"}:
            if tag == "script" and "ld+json" in amap.get("type", "").lower():
                self._jsonld_depth += 1
                self._jsonld_buf = []
            else:
                self._hidden_depth += 1
        if tag == "p":
            self._p_depth += 1
            self._p_buf = []
        elif tag == "article":
            self.article_elements += 1
        elif tag == "table":
            self.table_count += 1
        elif tag == "pre":
            self.code_blocks += 1
            self._pre_depth += 1
        elif tag == "code" and not self._pre_depth:
            self.code_blocks += 1
        elif tag == "li":
            self.list_items += 1
        elif tag in {"h1", "h2", "h3", "h4"}:
            self.heading_count += 1
            self._heading_depth += 1
            self._heading_buf = []
        elif tag == "link" and "canonical" in {x.strip().lower() for x in amap.get("rel", "").split()}:
            href = amap.get("href", "").strip()
            if href:
                self.canonical_links.append(href)
        elif tag == "meta" and amap.get("name", "").lower() in {"robots", "googlebot", "bingbot"}:
            content = amap.get("content", "").strip()
            if content:
                self.meta_robots.append(content)
        elif tag == "time" and amap.get("datetime"):
            self.time_datetimes.append(amap["datetime"].strip())
        elif tag == "meta" and amap.get("property", "").lower() == "og:type":
            self.og_type = amap.get("content", "").strip().lower() or None

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag == "script" and self._jsonld_depth:
            self._jsonld_depth -= 1
            raw = "".join(self._jsonld_buf).strip()
            if raw:
                self.jsonld.append(raw)
            self._jsonld_buf = []
        elif tag in {"style", "noscript", "svg"} and self._hidden_depth:
            self._hidden_depth -= 1
        if tag == "p" and self._p_depth:
            self._p_depth -= 1
            text = re.sub(r"\s+", " ", "".join(self._p_buf)).strip()
            if text:
                self.paragraphs.append(text)
            self._p_buf = []
        elif tag == "pre" and self._pre_depth:
            self._pre_depth -= 1
        elif tag in {"h1", "h2", "h3", "h4"} and self._heading_depth:
            self._heading_depth -= 1
            text = re.sub(r"\s+", " ", "".join(self._heading_buf)).strip()
            if text:
                self.headings.append(text)
            self._heading_buf = []

    def handle_data(self, data: str) -> None:
        if self._jsonld_depth:
            self._jsonld_buf.append(data)
            return
        if self._hidden_depth:
            return
        text = re.sub(r"\s+", " ", data).strip()
        if text:
            self.visible_chunks.append(text)
            if self._p_depth:
                self._p_buf.append(" " + text)
            if self._heading_depth:
                self._heading_buf.append(" " + text)

    @property
    def visible_text(self) -> str:
        return " ".join(self.visible_chunks)


def _parse_html_audit(html_text: str) -> _HTMLAuditParser:
    parser = _HTMLAuditParser()
    parser.feed(html_text)
    parser.close()
    return parser


def _jsonld_nodes(parser: _HTMLAuditParser) -> tuple[list[dict[str, Any]], list[str]]:
    return parse_jsonld_blocks(parser.jsonld)


def _is_article_like(parser: _HTMLAuditParser, articles: list[dict[str, Any]]) -> bool:
    return bool(articles or parser.article_elements or parser.og_type == "article")


def _author_is_linked(article: dict[str, Any], nodes: list[dict[str, Any]]) -> tuple[bool, bool]:
    author = article.get("author")
    authors = author if isinstance(author, list) else [author]
    by_id = {n.get("@id"): n for n in nodes if isinstance(n.get("@id"), str)}
    linked = False
    has_same_as = False
    for item in authors:
        person: dict[str, Any] | None = None
        if isinstance(item, dict):
            if "person" in _types(item) and isinstance(item.get("name"), str):
                person = item
                linked = True
            elif isinstance(item.get("@id"), str):
                candidate = by_id.get(item["@id"])
                if isinstance(candidate, dict) and "person" in _types(candidate):
                    person = candidate
                    linked = True
        if person is not None:
            same_as = person.get("sameAs")
            if isinstance(same_as, str) and same_as.strip() or isinstance(same_as, list) and any(isinstance(x, str) and x.strip() for x in same_as):
                has_same_as = True
    return linked, has_same_as


def _robots_can_fetch(text: str, user_agent: str, url: str) -> bool:
    rp = robotparser.RobotFileParser()
    rp.set_url(url)
    rp.parse(text.splitlines())
    try:
        return rp.can_fetch(user_agent, url)
    except (KeyError, ValueError) as exc:
        # A malformed robots document should not turn indexability into a
        # hard failure; preserve the historical fail-open behavior and make
        # the assumption visible to operators.
        logger.warning(
            "robots parser failed; allowing fetch user_agent=%s error=%s",
            user_agent,
            type(exc).__name__,
        )
        return True


def check_search_indexability(ctx: CheckContext, spec: CheckSpec) -> CheckResult:
    """Check the minimum page-level SEO signals that AI search still depends on.

    This deliberately does not attempt to predict ranking. It only checks whether
    the selected page is fetchable, is not explicitly marked noindex, and exposes
    a non-conflicting canonical URL.
    """
    start = time.perf_counter()
    try:
        r = _fetch(ctx, ctx.content_url, {"Accept": "text/html,application/xhtml+xml"})
    except FetchError as exc:
        return _fetch_failure(spec, ctx, start, "fetch HTML for search indexability", exc)
    evidence = [r.evidence("inspect indexability and canonical", preview=False)]
    if r.status_code != 200 or "html" not in r.content_type:
        return _result(spec, ctx.target.url, "fail", f"selected content URL must resolve to HTTP 200 HTML for search indexing; got {r.status_code} {r.content_type or 'no content-type'}", start, evidence)

    parser = _parse_html_audit(r.text)
    directives: list[str] = []
    directives.extend(parser.meta_robots)
    if r.headers.get("x-robots-tag"):
        directives.append(r.headers["x-robots-tag"])
    noindex = any(re.search(r"(?:^|[,;\s])noindex(?:$|[,;\s])", x, re.IGNORECASE) for x in directives)

    canonicals = [urljoin(r.url, x) for x in parser.canonical_links]
    unique_canonicals = list(dict.fromkeys(canonicals))
    current = r.url.split("#", 1)[0]
    self_canonical = any(x.split("#", 1)[0] == current for x in unique_canonicals)
    evidence[0].metrics = {
        "robots_directives": directives,
        "noindex": noindex,
        "canonical_urls": unique_canonicals,
        "self_canonical": self_canonical,
    }
    if noindex:
        return _result(spec, ctx.target.url, "fail", "page is explicitly marked noindex in meta robots or X-Robots-Tag", start, evidence)
    if len(unique_canonicals) > 1:
        return _result(spec, ctx.target.url, "warn", "multiple canonical URLs are declared; keep one authoritative canonical", start, evidence)
    if not unique_canonicals:
        return _result(spec, ctx.target.url, "warn", "page is indexable but does not declare a canonical URL", start, evidence)
    if not self_canonical:
        return _result(spec, ctx.target.url, "warn", f"page is indexable but canonical points elsewhere: {unique_canonicals[0]}", start, evidence)
    return _result(spec, ctx.target.url, "pass", "page is HTTP 200, not marked noindex, and declares a self-canonical URL", start, evidence)


def check_ai_crawler_live_access(ctx: CheckContext, spec: CheckSpec) -> CheckResult:
    start = time.perf_counter()
    evidence: list[Evidence] = []
    try:
        rr = _robots(ctx)
        robots_text = rr.text if rr.status_code == 200 else ""
        evidence.append(rr.evidence("fetch robots.txt for live crawler access"))
    except FetchError as exc:
        robots_text = ""
        evidence.append(Evidence(action="fetch robots.txt for live crawler access", url=_url(ctx.target.origin, "/robots.txt"), finding=str(exc)))

    rows: list[dict[str, Any]] = []
    for role, agents in (("search", _SEARCH_INDEX_UAS), ("user", _USER_FETCH_UAS), ("training", _TRAINING_UAS)):
        for ua in agents:
            allowed = _robots_can_fetch(robots_text, ua, ctx.content_url) if robots_text else True
            try:
                r = _fetch(ctx, ctx.content_url, {"User-Agent": ua, "Accept": "text/html,application/xhtml+xml,*/*;q=0.8"}, use_cache=False)
                network_ok = 200 <= r.status_code < 400
                rows.append({"ua": ua, "role": role, "robots_allowed": allowed, "status": r.status_code, "network_ok": network_ok})
                ev = r.evidence(f"probe live access as {ua}", preview=False, finding=f"role={role}; robots_allowed={allowed}; HTTP={r.status_code}")
                ev.metrics = {"role": role, "robots_allowed": allowed, "network_ok": network_ok, "spoofed_user_agent_probe": True}
                evidence.append(ev)
            except FetchError as exc:
                rows.append({"ua": ua, "role": role, "robots_allowed": allowed, "status": None, "network_ok": False})
                evidence.append(Evidence(action=f"probe live access as {ua}", url=ctx.content_url, finding=f"role={role}; robots_allowed={allowed}; {exc}", metrics={"spoofed_user_agent_probe": True}))

    for token in _ROBOTS_ONLY_AI_TOKENS:
        allowed = _robots_can_fetch(robots_text, token, ctx.content_url) if robots_text else True
        rows.append({"ua": token, "role": "training-policy", "robots_allowed": allowed, "status": None, "network_ok": None})
        evidence.append(
            Evidence(
                action=f"inspect robots policy for {token}",
                url=_url(ctx.target.origin, "/robots.txt"),
                finding=f"role=training-policy; robots_allowed={allowed}; no separate HTTP User-Agent",
                metrics={"role": "training-policy", "robots_allowed": allowed, "network_ok": None, "spoofed_user_agent_probe": False},
            )
        )

    search_rows = [x for x in rows if x["role"] == "search"]
    robots_blocked_search = [x for x in search_rows if not x["robots_allowed"]]
    transport_blocked_search = [x for x in search_rows if x["robots_allowed"] and not x["network_ok"]]
    blocked_user = [x for x in rows if x["role"] == "user" and not x["network_ok"]]
    blocked_training = [
        x
        for x in rows
        if x["role"] in {"training", "training-policy"}
        and (not x["robots_allowed"] or (x["role"] == "training" and not x["network_ok"]))
    ]

    if robots_blocked_search:
        names = ", ".join(x["ua"] for x in robots_blocked_search)
        return _result(spec, ctx.target.url, "fail", f"robots.txt blocks AI/search crawler access for: {names}", start, evidence)
    if transport_blocked_search:
        names = ", ".join(f"{x['ua']}(HTTP {x['status']})" for x in transport_blocked_search)
        return _result(
            spec,
            ctx.target.url,
            "warn",
            "spoofed crawler User-Agent probes were blocked or failed despite robots permission: "
            + names
            + "; this can indicate a WAF/CDN block, but anti-spoofing may also reject requests that do not originate from the crawler's official IP ranges, so confirm with server/WAF logs",
            start,
            evidence,
        )
    if blocked_user:
        names = ", ".join(f"{x['ua']}(HTTP {x['status']})" for x in blocked_user)
        return _result(spec, ctx.target.url, "warn", f"search crawler probes succeeded, but user-directed fetcher probes have access problems: {names}; confirm with server/WAF logs", start, evidence)
    training_note = "; training crawlers are restricted: " + ", ".join(x["ua"] for x in blocked_training) if blocked_training else ""
    return _result(spec, ctx.target.url, "pass", "search and user-directed crawler User-Agent probes can fetch the selected content URL" + training_note + "; spoofed-UA probes are a diagnostic, not proof that requests from official crawler IPs will be accepted", start, evidence)

def check_structured_data_graph(ctx: CheckContext, spec: CheckSpec) -> CheckResult:
    start = time.perf_counter()
    try:
        r = _fetch(ctx, ctx.content_url, {"Accept": "text/html,application/xhtml+xml"})
    except FetchError as exc:
        return _fetch_failure(spec, ctx, start, "fetch HTML for structured data", exc)
    if r.status_code != 200 or "html" not in r.content_type:
        return _result(spec, ctx.target.url, "skip", "selected content URL is not an HTTP 200 HTML page; JSON-LD article audit is not applicable", start, [r.evidence("fetch HTML for structured data")])
    parser = _parse_html_audit(r.text)
    nodes, errors = _jsonld_nodes(parser)
    articles = _article_nodes(nodes)
    evidence = [r.evidence("inspect Schema.org JSON-LD", preview=False)]
    evidence[0].metrics = {"jsonld_blocks": len(parser.jsonld), "valid_nodes": len(nodes), "parse_errors": len(errors), "article_nodes": len(articles)}
    if not _is_article_like(parser, articles):
        return _result(spec, ctx.target.url, "skip", "selected page is not detectably article-like; Article/TechArticle graph is not required for this page type", start, evidence)
    if not articles:
        detail = "article-like page has no valid Article/TechArticle/BlogPosting/NewsArticle JSON-LD node"
        if errors:
            detail += f"; JSON-LD parse errors: {len(errors)}"
        return _result(spec, ctx.target.url, "fail", detail, start, evidence)

    article = articles[0]
    missing = [k for k in ("headline", "datePublished", "dateModified", "mainEntityOfPage", "author") if not article.get(k)]
    linked_author, author_same_as = _author_is_linked(article, nodes)
    breadcrumbs = any("breadcrumblist" in _types(n) for n in nodes)
    metrics = evidence[0].metrics
    metrics.update({"missing_core_fields": missing, "linked_author": linked_author, "author_same_as": author_same_as, "breadcrumb_list": breadcrumbs})
    if missing or not linked_author:
        problems = (["missing " + ", ".join(missing)] if missing else []) + (["author is not linked to a Person node via @id/inline Person"] if not linked_author else [])
        return _result(spec, ctx.target.url, "fail", "incomplete/disconnected article JSON-LD graph: " + "; ".join(problems), start, evidence)
    extras: list[str] = []
    if errors:
        extras.append(f"{len(errors)} JSON-LD block(s) failed to parse")
    if not author_same_as:
        extras.append("Person.sameAs is absent")
    if not breadcrumbs:
        extras.append("BreadcrumbList is absent")
    detail = "connected article JSON-LD graph with author, publication/update dates and mainEntityOfPage"
    if extras:
        return _result(spec, ctx.target.url, "warn", detail + "; recommended fixes: " + ", ".join(extras), start, evidence)
    return _result(spec, ctx.target.url, "pass", detail + "; Person.sameAs and BreadcrumbList are present", start, evidence)


def _faq_valid(node: dict[str, Any]) -> tuple[bool, str]:
    items = node.get("mainEntity")
    if not isinstance(items, list) or not items:
        return False, "FAQPage.mainEntity must be a non-empty array"
    for idx, item in enumerate(items):
        if not isinstance(item, dict) or "question" not in _types(item) or not isinstance(item.get("name"), str) or not item.get("name", "").strip():
            return False, f"FAQ item {idx} must be a Question with name"
        answer = item.get("acceptedAnswer")
        if not isinstance(answer, dict) or "answer" not in _types(answer) or not isinstance(answer.get("text"), str) or not answer.get("text", "").strip():
            return False, f"FAQ item {idx} must contain acceptedAnswer Answer.text"
    return True, ""


def check_faq_structured_data(ctx: CheckContext, spec: CheckSpec) -> CheckResult:
    start = time.perf_counter()
    try:
        r = _fetch(ctx, ctx.content_url, {"Accept": "text/html,application/xhtml+xml"})
    except FetchError as exc:
        return _fetch_failure(spec, ctx, start, "fetch HTML for FAQ structured data", exc)
    evidence = [r.evidence("inspect FAQ structured data", preview=False)]
    if r.status_code != 200 or "html" not in r.content_type:
        return _result(spec, ctx.target.url, "skip", "selected content URL is not an HTTP 200 HTML page; FAQ audit is not applicable", start, evidence)
    parser = _parse_html_audit(r.text)
    nodes, errors = _jsonld_nodes(parser)
    faq_nodes = [n for n in nodes if "faqpage" in _types(n)]
    question_headings = [h for h in parser.headings if h.rstrip().endswith("?") or h.rstrip().endswith("？")]
    evidence[0].metrics = {
        "faq_nodes": len(faq_nodes),
        "question_like_headings": len(question_headings),
        "jsonld_parse_errors": len(errors),
    }
    if faq_nodes:
        for node in faq_nodes:
            ok, why = _faq_valid(node)
            if not ok:
                return _result(spec, ctx.target.url, "fail", "FAQPage JSON-LD is present but invalid: " + why, start, evidence)
        return _result(spec, ctx.target.url, "pass", f"valid FAQPage structured data found with {sum(len(n.get('mainEntity', [])) for n in faq_nodes)} question(s)", start, evidence)
    if len(question_headings) >= 2:
        return _result(spec, ctx.target.url, "warn", f"page has {len(question_headings)} question-like headings but no FAQPage JSON-LD; add FAQ markup only if these are genuine visible questions and answers", start, evidence)
    return _result(spec, ctx.target.url, "skip", "no clear FAQ/Q&A section detected; FAQPage markup is not required", start, evidence)


def _parse_iso_date(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    raw = value.strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError:
        try:
            dt = datetime.fromisoformat(raw[:10])
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def _date_visible(value: str, parser: _HTMLAuditParser) -> bool:
    date_part = value[:10]
    if value in parser.visible_text or date_part in parser.visible_text:
        return True
    return any(x.startswith(date_part) for x in parser.time_datetimes)


def check_date_transparency(ctx: CheckContext, spec: CheckSpec) -> CheckResult:
    start = time.perf_counter()
    try:
        r = _fetch(ctx, ctx.content_url, {"Accept": "text/html,application/xhtml+xml"})
    except FetchError as exc:
        return _fetch_failure(spec, ctx, start, "fetch HTML for date transparency", exc)
    if r.status_code != 200 or "html" not in r.content_type:
        return _result(spec, ctx.target.url, "skip", "selected content URL is not an HTTP 200 HTML page; publication date audit is not applicable", start, [r.evidence("fetch HTML for date transparency")])
    parser = _parse_html_audit(r.text)
    nodes, _ = _jsonld_nodes(parser)
    articles = _article_nodes(nodes)
    evidence = [r.evidence("inspect publication/update dates", preview=False)]
    if not _is_article_like(parser, articles):
        return _result(spec, ctx.target.url, "skip", "selected page is not detectably article-like; publication/update date audit is not applicable", start, evidence)
    if not articles:
        return _result(spec, ctx.target.url, "fail", "article-like page has no parseable Article JSON-LD dates", start, evidence)
    article = articles[0]
    pub_raw = article.get("datePublished")
    mod_raw = article.get("dateModified")
    pub = _parse_iso_date(pub_raw)
    mod = _parse_iso_date(mod_raw)
    now = datetime.now(UTC)
    pub_visible = _date_visible(str(pub_raw), parser) if isinstance(pub_raw, str) else False
    mod_visible = _date_visible(str(mod_raw), parser) if isinstance(mod_raw, str) else False
    evidence[0].metrics = {
        "datePublished": pub_raw,
        "dateModified": mod_raw,
        "published_visible": pub_visible,
        "modified_visible": mod_visible,
        "history_verifiable_remotely": False,
    }
    problems: list[str] = []
    if not pub:
        problems.append("datePublished is missing/invalid ISO date")
    if not mod:
        problems.append("dateModified is missing/invalid ISO date")
    if pub and mod and mod < pub:
        problems.append("dateModified precedes datePublished")
    if pub and pub > now:
        problems.append("datePublished is in the future")
    if mod and mod > now:
        problems.append("dateModified is in the future")
    if pub and not pub_visible:
        problems.append("datePublished is not visible in page text or a <time datetime> element")
    if mod and not mod_visible:
        problems.append("dateModified is not visible in page text or a <time datetime> element")
    if problems:
        return _result(spec, ctx.target.url, "fail", "date transparency problems: " + "; ".join(problems), start, evidence)
    return _result(spec, ctx.target.url, "pass", "publication and modification dates are valid, ordered and visibly exposed; whether dateModified reflects a real content change requires repository/history verification", start, evidence)


def _intent_facets(headings: list[str]) -> set[str]:
    joined = "\n".join(headings).lower()
    patterns = {
        "price": r"\b(price|pricing|cost|tariff|тариф|цен[аы]|стоимост)\w*",
        "requirements": r"\b(requirements?|system requirements?|требован|системн\w+ требован)\w*",
        "availability": r"\b(availability|available|compatib|support|доступ|работает|совместим|поддерж)\w*",
        "troubleshooting": r"\b(troubleshoot|problem|error|doesn.?t work|ошибк|проблем|не работает|что делать)\w*",
        "comparison": r"\b(compare|comparison|versus|\bvs\b|сравнен|отличи|альтернатив)\w*",
    }
    return {name for name, pattern in patterns.items() if re.search(pattern, joined, re.IGNORECASE)}


def check_citation_readiness(ctx: CheckContext, spec: CheckSpec) -> CheckResult:
    start = time.perf_counter()
    try:
        r = _fetch(ctx, ctx.content_url, {"Accept": "text/html,application/xhtml+xml"})
    except FetchError as exc:
        return _fetch_failure(spec, ctx, start, "fetch HTML for citation-readiness heuristic", exc)
    if r.status_code != 200 or "html" not in r.content_type:
        return _result(spec, ctx.target.url, "skip", "citation-readiness heuristic currently requires an HTML page", start, [r.evidence("fetch HTML for citation-readiness heuristic")])
    parser = _parse_html_audit(r.text)
    visible = parser.visible_text
    numeric_mentions = len(re.findall(r"(?<!\w)\d+(?:[.,]\d+)?(?:\s?(?:%|[$€£₽¥]|[A-Za-zА-Яа-я]{1,8}))?", visible))
    substantive = sum(len(p) >= 100 for p in parser.paragraphs)
    concrete_paragraphs = sum(
        len(p) >= 80 and bool(re.search(r"\d|`|https?://|\b(?:if|when|requires?|limit|price|version|если|при|лимит|цена|верси)\w*", p, re.IGNORECASE))
        for p in parser.paragraphs
    )
    deictic = re.compile(r"^(?:this|that|these|those|it|they|above|below|here|there|это|этот|эта|эти|такой|такая|он|она|они|здесь|выше|ниже)\b", re.IGNORECASE)
    self_contained = sum(len(p) >= 100 and not deictic.search(p.strip()) for p in parser.paragraphs)
    first = next((p.strip() for p in parser.paragraphs if len(p.strip()) >= 40), "")
    answer_first = bool(first and len(first) <= 600 and not first.endswith("?") and (re.search(r"\d", first) or len(first.split()) >= 8))
    facets = _intent_facets(parser.headings)
    families = {
        "numbers": numeric_mentions >= 3,
        "code": parser.code_blocks >= 1,
        "tables": parser.table_count >= 1,
        "structured_lists": parser.list_items >= 3,
        "substantive_paragraphs": substantive >= 3,
        "concrete_paragraphs": concrete_paragraphs >= 2,
        "self_contained_paragraphs": self_contained >= 2,
        "answer_first": answer_first,
        "section_structure": parser.heading_count >= 2,
    }
    signal_count = sum(families.values())
    evidence = [r.evidence("analyze citation-ready content signals", preview=False)]
    evidence[0].metrics = {
        "visible_chars": len(visible),
        "paragraphs": len(parser.paragraphs),
        "substantive_paragraphs": substantive,
        "concrete_paragraphs": concrete_paragraphs,
        "self_contained_paragraphs": self_contained,
        "numeric_mentions": numeric_mentions,
        "code_blocks": parser.code_blocks,
        "tables": parser.table_count,
        "list_items": parser.list_items,
        "headings": parser.heading_count,
        "answer_first": answer_first,
        "intent_facets_in_headings": sorted(facets),
        "signal_families": families,
        "heuristic": True,
        "ranking_factor_claimed": False,
    }
    if len(visible) < 400:
        return _result(spec, ctx.target.url, "warn", "content is too short for a meaningful citation-readiness assessment; heuristic only, not a ranking factor", start, evidence)
    if signal_count >= 5:
        return _result(spec, ctx.target.url, "pass", f"citation-readiness heuristic found {signal_count}/9 extractable signal families; metrics include concrete facts, complete code/tables, self-contained paragraphs and answer-first structure", start, evidence)
    return _result(spec, ctx.target.url, "warn", f"citation-readiness heuristic found only {signal_count}/9 extractable signal families; add concrete facts/conditions, complete commands, comparison tables and self-contained answer-first paragraphs where appropriate; intent coverage still requires human judgment", start, evidence)


CHECK_FUNCTIONS: dict[str, Callable[[CheckContext, CheckSpec], CheckResult]] = {
    "robots-txt": check_robots,
    "sitemap": check_sitemap,
    "link-headers": check_link_headers,
    "dns-aid": check_dns_aid,
    "markdown-negotiation": check_markdown,
    "ai-bot-rules": check_ai_bot_rules,
    "content-signals": check_content_signals,
    "web-bot-auth": check_web_bot_auth,
    "api-catalog": check_api_catalog,
    "oauth-discovery": check_oauth_discovery,
    "oauth-protected-resource": check_oauth_protected,
    "auth-md": check_auth_md,
    "mcp-server-card": check_mcp_card,
    "a2a-agent-card": check_a2a_card,
    "agent-skills": check_agent_skills,
    "webmcp": check_webmcp,
    "x402": check_x402,
    "mpp": check_mpp,
    "ucp": check_ucp,
    "acp": check_acp,
    "llms-txt": check_llms_txt,
    "markdown-index-fallback": check_markdown_index_fallback,
    "markdown-efficiency": check_markdown_efficiency,
    "search-indexability": check_search_indexability,
    "ai-crawler-live-access": check_ai_crawler_live_access,
    "structured-data-graph": check_structured_data_graph,
    "faq-structured-data": check_faq_structured_data,
    "date-transparency": check_date_transparency,
    "citation-readiness": check_citation_readiness,
}


def run_check(ctx: CheckContext, spec: CheckSpec) -> CheckResult:
    fn = CHECK_FUNCTIONS.get(spec.id)
    if not fn:
        return CheckResult(spec.id, spec.title, spec.category, "error", spec.scored, "check implementation missing")
    try:
        return fn(ctx, spec)
    except Exception as exc:  # Defensive boundary: one audit must not abort the scan.
        logger.exception(
            "check execution failed check_id=%s target_host=%s error=%s",
            spec.id,
            ctx.target.hostname,
            type(exc).__name__,
        )
        return CheckResult(
            id=spec.id,
            title=spec.title,
            category=spec.category,
            status="error",
            scored=spec.scored,
            details=f"unexpected check error: {type(exc).__name__}: {exc}",
            remediation=remediation_for(spec, ctx.target.url),
            experimental=spec.experimental,
            supplemental=spec.supplemental,
            geo_scored=spec.geo_scored,
        )
