"""URL / 网络目标安全校验：私网、数字别名、元数据一律拒绝。

审核 I10 / FH-AUDIT-P0-04：
- 拦截十进制/十六进制/八进制/缩写 IPv4（如 2130706433、0x7f000001、127.1）
- 抓取时禁止自动 follow_redirects；逐跳校验后再请求
"""

from __future__ import annotations

import ipaddress
import re
from urllib.parse import urlparse

from app.core.errors import ErrorCode, FlightHunterError

SAFE_SCHEMES = frozenset({"http", "https"})

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

# 2130706433 / 0x7f000001 / 017700000001 等数字主机
_NUM_HOST_RE = re.compile(r"^(0x[0-9a-f]+|0[0-7]+|[0-9]+)$", re.I)


def _blocked_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    return bool(
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
        or str(ip) == "169.254.169.254"
    )


def _parse_numeric_host(h: str) -> ipaddress.IPv4Address | None:
    """解析常见 IPv4 别名写法；无法解析返回 None。"""
    s = h.strip()
    try:
        if s.lower().startswith("0x"):
            return ipaddress.IPv4Address(int(s, 16))
        if re.fullmatch(r"0[0-7]+", s):
            return ipaddress.IPv4Address(int(s, 8))
        if re.fullmatch(r"[0-9]+", s):
            return ipaddress.IPv4Address(int(s, 10))
    except ValueError:
        return None
    # 127.1 / 10.1 等缩写点分
    if re.fullmatch(r"[0-9]{1,3}(\.[0-9]{1,3}){0,3}", s):
        try:
            return ipaddress.IPv4Address(s)
        except ValueError:
            # 127.1 → 尝试补全
            parts = s.split(".")
            try:
                nums = [int(p) for p in parts]
            except ValueError:
                return None
            while len(nums) < 4:
                nums.append(0)
            if any(n > 255 for n in nums):
                return None
            try:
                return ipaddress.IPv4Address(".".join(str(n) for n in nums))
            except ValueError:
                return None
    return None


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
    # 仅数字与点的主机（含 0177.0.0.1、2130706433 等别名）一律拒绝
    if re.fullmatch(r"[0-9.]+", h):
        return True
    if _NUM_HOST_RE.match(h):
        return True
    return bool(h.startswith("ip6-localhost") or h.endswith(".localhost"))


def resolve_and_assert_public_host(host: str, *, field: str = "url") -> list[str]:
    """DNS 解析主机，全部 A/AAAA 必须为公网地址；返回通过的 IP 列表。

    用于连接前校验（含 rebinding 防护的第一道）。无法解析 → 拒绝（fail-closed）。
    """
    import socket

    if is_blocked_hostname(host):
        raise FlightHunterError(
            ErrorCode.URL_NOT_PUBLIC,
            f"主机名不安全或禁止: {host}",
            details={"field": field, "host": host},
        )
    try:
        infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    except OSError as exc:
        raise FlightHunterError(
            ErrorCode.URL_NOT_PUBLIC,
            f"无法解析主机（fail-closed）: {host} ({exc})",
            details={"field": field, "host": host},
        ) from exc
    ips: list[str] = []
    for info in infos:
        addr = info[4][0]
        try:
            ip = ipaddress.ip_address(addr)
        except ValueError:
            continue
        if _blocked_ip(ip):
            raise FlightHunterError(
                ErrorCode.URL_NOT_PUBLIC,
                f"DNS 解析到私网/保留地址，已拒绝: {host} -> {addr}",
                details={"field": field, "host": host, "ip": str(ip)},
            )
        ips.append(str(ip))
    if not ips:
        raise FlightHunterError(
            ErrorCode.URL_NOT_PUBLIC,
            f"无有效公网解析结果: {host}",
            details={"field": field, "host": host},
        )
    return ips


def assert_public_http_url(url: str, *, field: str = "url", resolve_dns: bool = False) -> None:
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
            f"目标主机属于本地/私网/保留/数字别名，已拒绝: {host}",
            details={"field": field, "host": host},
        )
    if parsed.port is not None and parsed.port == 0:
        raise FlightHunterError(ErrorCode.URL_NOT_PUBLIC, "非法端口")
    if resolve_dns:
        resolve_and_assert_public_host(host, field=field)


def safe_redirect_target(url: str) -> None:
    assert_public_http_url(url, field="redirect")


def is_safe_local_next(next_url: str | None) -> str:
    """登录后跳转：仅允许站内相对路径，拒绝 // 与外部 scheme。"""
    if not next_url:
        return "/"
    n = next_url.strip()
    if not n.startswith("/"):
        return "/"
    if n.startswith("//") or n.startswith("/\\"):
        return "/"
    if n.startswith("/") and re.match(r"^/[A-Za-z][A-Za-z0-9+.-]*:", n):
        return "/"
    if "\\" in n:
        return "/"
    return n
