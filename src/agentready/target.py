from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit


class TargetError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class Target:
    url: str
    origin: str
    hostname: str
    port: int
    scheme: str


def normalize_url(value: str) -> str:
    value = value.strip()
    if not value:
        raise TargetError("Empty URL")
    if "://" not in value:
        value = "https://" + value
    p = urlsplit(value)
    if p.scheme not in {"http", "https"}:
        raise TargetError("Only http:// and https:// targets are supported")
    if not p.hostname:
        raise TargetError("URL must contain a hostname")
    path = p.path or "/"
    return urlunsplit((p.scheme, p.netloc, path, p.query, ""))


def parse_target(value: str) -> Target:
    url = normalize_url(value)
    p = urlsplit(url)
    port = p.port or (443 if p.scheme == "https" else 80)
    host = p.hostname or ""
    origin_netloc = host
    if (p.scheme == "https" and port != 443) or (p.scheme == "http" and port != 80):
        origin_netloc = f"{host}:{port}"
    return Target(url=url, origin=f"{p.scheme}://{origin_netloc}", hostname=host, port=port, scheme=p.scheme)


def resolved_ips(hostname: str, port: int) -> list[ipaddress._BaseAddress]:
    out: list[ipaddress._BaseAddress] = []
    for row in socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM):
        raw = row[4][0]
        try:
            ip = ipaddress.ip_address(raw)
        except ValueError:
            continue
        if ip not in out:
            out.append(ip)
    return out


def ip_is_non_public(ip: ipaddress._BaseAddress) -> bool:
    return any(
        (
            ip.is_private,
            ip.is_loopback,
            ip.is_link_local,
            ip.is_multicast,
            ip.is_reserved,
            ip.is_unspecified,
        )
    )


def ensure_public_url(url: str) -> None:
    t = parse_target(url)
    try:
        ips = resolved_ips(t.hostname, t.port)
    except socket.gaierror as exc:
        raise TargetError(f"DNS resolution failed for {t.hostname}: {exc}") from exc
    if not ips:
        raise TargetError(f"No IP addresses resolved for {t.hostname}")
    bad = [str(ip) for ip in ips if ip_is_non_public(ip)]
    if bad:
        raise TargetError(f"Target resolves to non-public IP address(es): {', '.join(bad)}")
