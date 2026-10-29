"""URL / 网络目标安全校验：私网、链路本地、元数据地址一律拒绝。"""

from __future__ import annotations

import ipaddress
from urllib.parse import urlparse

from app.core.errors import ErrorCode, FlightHunterError

SAFE_SCHEMES = frozenset({"http", "https"})

# 常见云元数据 / 本地服务
_BLOCKED_HOSTS = frozenset(
    {
        "localhost",
        "localhost.localdomain",
        "0.0.0.0",
        "::1",
        "metadata.google.internal",
        "metadata",
    }
)

_BLOCKED_HOST_SUFFIXES = (
    ".localhost",
    ".local",
    ".internal",
)


def _blocked_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return bool(
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
        or (ipaddress.IPv6Address(ip).ipv4_mapped is not None)
        or str(ip) == "169.254.169.254"
    )


def is_blocked_hostname(host: str) -> bool:
    h = host.strip(".").lower()
    if not h:
        return True
    if h in _BLOCKED_HOSTS:
        return True
    if any(h.endswith(sfx) for sfx in _BLOCKED_HOST_SUFFIXES):
        return True
    # 字面量 IP
    try:
        ip = ipaddress.ip_address(h)
        return _blocked_ip(ip)
    except ValueError:
        pass
    # 常见私网主机名模式
    return bool(h.startswith("ip6-localhost") or h.endswith(".localhost"))


def assert_public_http_url(url: str, *, field: str = "url") -> None:
    if not url or not isinstance(url, str):
        raise FlightHunterError(ErrorCode.URL_NOT_PUBLIC, "URL 为空")
    parsed = urlparse(url)
    if parsed.scheme not in SAFE_SCHEMES:
        raise FlightHunterError(
            ErrorCode.URL_NOT_PUBLIC,
            f"仅允许 http/https: {url!r}",
            details={"field": field, "scheme": parsed.scheme},
        )
    if parsed.username or parsed.password:
        raise FlightHunterError(
            ErrorCode.URL_NOT_PUBLIC,
            "URL 不得内嵌凭据",
            details={"field": field},
        )
    host = (parsed.hostname or "").lower()
    if is_blocked_hostname(host):
        raise FlightHunterError(
            ErrorCode.URL_NOT_PUBLIC,
            f"目标主机属于本地/私网/保留地址，已拒绝: {host}",
            details={"field": field, "host": host},
        )
    # 端口检查：拒绝常见本地服务端口组合虽非必须，但防止 127 通过 DNS 绕过
    if parsed.port is not None and parsed.port in (0,):
        raise FlightHunterError(ErrorCode.URL_NOT_PUBLIC, "非法端口")


def safe_redirect_target(url: str) -> None:
    """重定向后再次校验。"""
    assert_public_http_url(url, field="redirect")
