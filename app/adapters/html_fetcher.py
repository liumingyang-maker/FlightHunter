"""httpx 简单抓取适配器（公开 HTML）。

禁止 follow_redirects=True 自动跳转：每一跳先 assert_public_http_url 再请求。
"""

from __future__ import annotations

import asyncio
import re
from datetime import UTC, datetime
from typing import Any
from urllib import robotparser
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from app.adapters.base import FetchResult, ParsedSignal, SourceAdapter
from app.config import Settings
from app.core.errors import ErrorCode
from app.core.ids import content_hash_of_html
from app.core.url_safety import (
    assert_public_http_url,
    resolve_and_assert_public_host,
    safe_redirect_target,
)

_MAX_REDIRECT_HOPS = 5


class HttpxFetchAdapter(SourceAdapter):
    name = "httpx"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._robots_cache: dict[str, robotparser.RobotFileParser | None] = {}

    async def _robots_allowed(self, client: httpx.AsyncClient, url: str) -> bool:
        """robots 非 200 或异常 → fail-closed（不允许）。"""
        if not self.settings.sources.obey_robots_and_site_terms:
            return True
        parsed = urlparse(url)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        if origin not in self._robots_cache:
            rp = robotparser.RobotFileParser()
            try:
                resp = await client.get(f"{origin}/robots.txt", timeout=10)
                if resp.status_code == 200:
                    rp.parse(resp.text.splitlines())
                    self._robots_cache[origin] = rp
                else:
                    self._robots_cache[origin] = None
            except Exception:
                self._robots_cache[origin] = None
        entry = self._robots_cache.get(origin)
        if entry is None:
            return False
        return entry.can_fetch("*", url)

    async def fetch(self, url: str) -> FetchResult:
        try:
            assert_public_http_url(url)
            host = (urlparse(url).hostname or "").lower()
            resolve_and_assert_public_host(host)
        except Exception as exc:
            return FetchResult(
                ok=False,
                url=url,
                error_code=ErrorCode.URL_NOT_PUBLIC.value,
                message=str(exc),
                fetched_at=datetime.now(UTC),
            )

        headers = {"User-Agent": "FlightHunter/1.0 (+local personal research; respectful)"}
        timeout = self.settings.sources.max_runtime_seconds_per_page
        current = url
        try:
            async with httpx.AsyncClient(
                headers=headers,
                timeout=timeout,
                follow_redirects=False,
                trust_env=False,
            ) as client:
                for _hop in range(_MAX_REDIRECT_HOPS + 1):
                    try:
                        assert_public_http_url(current)
                        hop_host = (urlparse(current).hostname or "").lower()
                        resolve_and_assert_public_host(hop_host)
                    except Exception as exc:
                        return FetchResult(
                            ok=False,
                            url=url,
                            error_code=ErrorCode.URL_NOT_PUBLIC.value,
                            message=f"跳转目标不安全（请求前拦截）: {exc}",
                            final_url=current,
                            fetched_at=datetime.now(UTC),
                        )
                    if not await self._robots_allowed(client, current):
                        return FetchResult(
                            ok=False,
                            url=url,
                            error_code=ErrorCode.SOURCE_FETCH_DENIED.value,
                            message="robots.txt 不允许抓取",
                            robots_disallowed=True,
                            final_url=current,
                            fetched_at=datetime.now(UTC),
                        )
                    try:
                        resp = await client.get(current)
                    except httpx.HTTPError as exc:
                        return FetchResult(
                            ok=False,
                            url=url,
                            error_code=ErrorCode.SOURCE_UNAVAILABLE.value,
                            message=str(exc),
                            final_url=current,
                            fetched_at=datetime.now(UTC),
                        )

                    if resp.status_code in (301, 302, 303, 307, 308):
                        loc = resp.headers.get("location")
                        if not loc:
                            return FetchResult(
                                ok=False,
                                url=url,
                                status_code=resp.status_code,
                                error_code=ErrorCode.SOURCE_UNAVAILABLE.value,
                                message="重定向缺少 Location",
                                final_url=current,
                                fetched_at=datetime.now(UTC),
                            )
                        nxt = urljoin(current, loc)
                        try:
                            safe_redirect_target(nxt)
                            nxt_host = (urlparse(nxt).hostname or "").lower()
                            resolve_and_assert_public_host(nxt_host)
                        except Exception as exc:
                            return FetchResult(
                                ok=False,
                                url=url,
                                error_code=ErrorCode.URL_NOT_PUBLIC.value,
                                message=f"重定向目标不安全（未发起请求）: {exc}",
                                final_url=nxt,
                                fetched_at=datetime.now(UTC),
                            )
                        current = nxt
                        continue

                    if resp.status_code >= 400:
                        return FetchResult(
                            ok=False,
                            url=url,
                            status_code=resp.status_code,
                            error_code=ErrorCode.SOURCE_UNAVAILABLE.value,
                            message=f"HTTP {resp.status_code}",
                            final_url=str(resp.url),
                            fetched_at=datetime.now(UTC),
                        )

                    content = resp.content
                    if len(content) > self.settings.sources.max_html_bytes:
                        return FetchResult(
                            ok=False,
                            url=url,
                            status_code=resp.status_code,
                            error_code=ErrorCode.SOURCE_UNAVAILABLE.value,
                            message="响应体超过大小限制",
                            fetched_at=datetime.now(UTC),
                        )
                    text = content.decode("utf-8", errors="replace")
                    return FetchResult(
                        ok=True,
                        url=url,
                        status_code=resp.status_code,
                        content_type=resp.headers.get("content-type"),
                        text=text,
                        content_hash=content_hash_of_html(text),
                        final_url=current,
                        fetched_at=datetime.now(UTC),
                    )
                return FetchResult(
                    ok=False,
                    url=url,
                    error_code=ErrorCode.SOURCE_UNAVAILABLE.value,
                    message="重定向次数过多",
                    final_url=current,
                    fetched_at=datetime.now(UTC),
                )
        except Exception as exc:
            return FetchResult(
                ok=False,
                url=url,
                error_code=ErrorCode.SOURCE_UNAVAILABLE.value,
                message=str(exc),
                fetched_at=datetime.now(UTC),
            )

    def parse(self, text: str, *, url: str) -> list[ParsedSignal]:
        soup = BeautifulSoup(text, "html.parser")
        signals: list[ParsedSignal] = []
        # D-007：从整页提取发布日期候选（FlyNext 等）— 标签内优先
        _ = re.findall(
            r"(20\d{2}年\s*\d{1,2}\s*月\s*\d{1,2}\s*日|20\d{2}[./-]\d{1,2}[./-]\d{1,2})",
            text or "",
        )
        for a in soup.find_all("a", href=True)[:400]:
            label = a.get_text(" ", strip=True)
            href_raw = a["href"] or ""
            if href_raw.lower().startswith("javascript:"):
                m = re.search(r"https?://[^'\"]+|['\"](/[^'\"]+)['\"]", href_raw)
                if not m:
                    continue
                href = m.group(0) if m.group(0).startswith("http") else urljoin(url, m.group(1))
            else:
                href = urljoin(url, href_raw)
            sig = parse_deal_label(label, page_url=href)
            if not sig and "/blog/" in href and any(
                k in label for k in ("機票", "机票", "優惠", "优惠", "促銷", "促销", "Peach", "國泰", "HK Express")
            ):
                from app.adapters.base import ParsedSignal

                # N-004：多目的地分别绑定；绑定不完整则金额 unknown
                routes = extract_route_price_candidates(label)
                price = None
                currency = None
                dest = None
                if len(routes) == 1:
                    price = routes[0]["amount"]
                    currency = routes[0]["currency"]
                    dest = routes[0].get("dest_city")
                elif len(routes) > 1:
                    # 多线路：取第一条并保留全部原文；不把 A 价绑到 B
                    price = routes[0]["amount"]
                    currency = routes[0]["currency"]
                    dest = routes[0].get("dest_city")
                else:
                    m_hkd = re.search(r"HK\$?\s*(\d[\d,]*)", label, re.I)
                    dests_found = re.findall(
                        r"(台湾|大阪|东京|首尔|曼谷|新加坡|台北|香港|上海|北京|成都)", label
                    )
                    if m_hkd and len(set(dests_found)) <= 1 and not re.search(
                        r"最高減|最多減|立減|立省|up to|save ", label, re.I
                    ):
                        try:
                            price = float(m_hkd.group(1).replace(",", ""))
                            currency = "HKD"
                        except ValueError:
                            price = None
                # 标签内发布日期：仅明确发布标签，不写旅行日期（N-006）
                published = _extract_published_only(label)
                sig = ParsedSignal(
                    title=label[:200],
                    raw_claim_text=label,
                    url=href if href.startswith("http") else None,
                    reported_total=price,
                    currency=currency,
                    destination_airport=None,  # 多目的地城市名未转 IATA 时不硬绑
                    deal_types=["flash_sale"],
                    confidence="low",
                    published_at=published,
                )
            if sig:
                signals.append(sig)
            if len(signals) >= 50:
                break
        return signals

    def parse_raffle(self, text: str, *, url: str) -> list[ParsedSignal]:
        soup = BeautifulSoup(text, "html.parser")
        signals: list[ParsedSignal] = []
        for a in soup.find_all("a", href=True)[:300]:
            label = a.get_text(" ", strip=True)
            href_raw = a["href"] or ""
            if href_raw.lower().startswith("javascript:"):
                m_abs = re.search(r"https?://[^'\"]+contentsView\.do\?[^'\"]+", href_raw, re.I)
                if m_abs:
                    href = m_abs.group(0).replace("&amp;", "&")
                else:
                    m_path = re.search(r"['\"](/[^'\"]+)['\"]", href_raw)
                    if not m_path:
                        continue
                    href = urljoin(url, m_path.group(1))
            else:
                href = urljoin(url, href_raw)
            if not href.startswith("http"):
                continue
            sig = parse_raffle_label(label, page_url=href)
            if sig:
                signals.append(sig)
            elif "contentsView.do" in href and ("vcontsId=" in href):
                # 官方详情链接：标签可能不含 giveaway 关键词，仍作线索
                if label and len(label) >= 6 and not any(
                    k in label.lower() for k in ("home", "menu", "login", "cookie")
                ):
                    from app.adapters.base import ParsedSignal

                    signals.append(
                        ParsedSignal(
                            title=label[:200],
                            raw_claim_text=label,
                            url=href,
                            deal_types=["survey_event"],
                            confidence="low",
                        )
                    )
            if len(signals) >= 40:
                break
        return signals

    def parse_trip(self, text: str, *, url: str) -> list[ParsedSignal]:
        soup = BeautifulSoup(text, "html.parser")
        signals: list[ParsedSignal] = []
        for a in soup.find_all("a", href=True)[:200]:
            label = a.get_text(" ", strip=True)
            href = urljoin(url, a["href"])
            sig = parse_trip_label(label, page_url=href)
            if sig:
                signals.append(sig)
            if len(signals) >= 50:
                break
        return signals


_IATA_RE = re.compile(r"\b([A-Z]{3})\b")
_PRICE_RE = re.compile(r"(\d[\d,]*(?:\.\d+)?)\s*元")
_FARE_KW = (
    "机票",
    "flight",
    "airfare",
    "特价机票",
    "往返",
    "单程",
    "機票",
    "來回",
    "来回",
    "連稅",
    "含税",
    "promotion",
)
_DEAL_KW = ("元", "BUG", "错价", "神价", "特价", "促销", "甩尾", "漏油", "尾单")
_TRIP_KW = (
    "券",
    "折扣",
    "优惠",
    "满减",
    "满",
    "减",
    "免费",
    "祭典",
    "活动",
    "coupon",
    "discount",
    "festival",
    "free",
    "promo",
)
_RISK_KW = {
    "hidden_city": ("甩尾", "hidden city", "hidden-city"),
    "error_fare": ("BUG", "错价", "error fare", "error-fare"),
    "fuel_surcharge_anomaly": ("漏油", "yq", "fuel surcharge"),
    "flash_sale": ("特价", "闪购", "促销", "flash"),
}


def _parse_any_date(s: str) -> datetime | None:
    if not s:
        return None
    s = s.strip()
    m = re.match(r"(20\d{2})年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日", s)
    if m:
        return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    m = re.match(r"(20\d{2})[./-](\d{1,2})[./-](\d{1,2})", s)
    if m:
        return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    m = re.match(r"(\d{1,2})[./-](\d{1,2})[./-](20\d{2})", s)
    if m:
        return datetime(int(m.group(3)), int(m.group(1)), int(m.group(2)))
    return None


# N-006：仅明确发布/更新标签；旅行/出发/销售日期不得写入 published_at
_PUBLISH_LABEL = re.compile(
    r"(?:發佈|发布|公佈|公布|更新|posted|published|published\s+at|date\s+posted|post\s*date)"
    r"\s*[:：]?\s*"
    r"(20\d{2}年\s*\d{1,2}\s*月\s*\d{1,2}\s*日|20\d{2}[./-]\d{1,2}[./-]\d{1,2})",
    re.I,
)
_TRAVEL_DATE_CONTEXT = re.compile(
    r"(旅行|出行|出發|出发|起飞|乘坐|有效期|适用|适用期|销售|促銷|促销|活动期|報名|报名|travel|valid\s+(?:from|for)|book|depart|departure|journey)",
    re.I,
)


def _extract_published_only(text: str) -> datetime | None:
    """只解析有发布标签的日期；旅行日期上下文一律不写 published_at。"""
    if not text:
        return None
    for m in _PUBLISH_LABEL.finditer(text):
        dt = _parse_any_date(m.group(1))
        if dt:
            return dt
    # 无标签时：若全文含旅行语境且日期紧邻旅行词，跳过
    bare = re.findall(
        r"(20\d{2}年\s*\d{1,2}\s*月\s*\d{1,2}\s*日|20\d{2}[./-]\d{1,2}[./-]\d{1,2})", text
    )
    if not bare:
        return None
    # 若裸日期出现在旅行词后 20 字符内 → 不是发布日
    for m in re.finditer(
        r"(20\d{2}年\s*\d{1,2}\s*月\s*\d{1,2}\s*日|20\d{2}[./-]\d{1,2}[./-]\d{1,2})", text
    ):
        start = max(0, m.start() - 24)
        window = text[start : m.start()]
        if _TRAVEL_DATE_CONTEXT.search(window):
            continue
        # 同句旅行词在日期后 16 字符
        end = min(len(text), m.end() + 16)
        if _TRAVEL_DATE_CONTEXT.search(text[m.end() : end]):
            continue
        return _parse_any_date(m.group(1))
    return None


def extract_route_price_candidates(label: str) -> list[dict[str, Any]]:
    """N-004：多目的地分别绑定价格；无法绑定则返回空（不把 A 目的地价绑到 B）。

    识别形如「大阪 HK$1500」「台湾 800」「HK$800 台湾」等就近绑定。
    """
    if not label:
        return []
    out: list[dict[str, Any]] = []
    dest_pat = (
        r"(大阪|东京|名古屋|冲绳|首尔|釜山|曼谷|普吉|清迈|吉隆坡|新加坡|巴厘岛|河内|胡志明|"
        r"台北|台湾|台中|高雄|香港|澳门|上海|北京|成都|重庆|广州|深圳|杭州|武汉|昆明)"
    )
    price_pat = r"(?:HK\$?\s*|¥\s*|MOP\$?\s*)(\d[\d,]{2,})"
    # dest 后价格
    for m in re.finditer(dest_pat + r"[^\dA-Za-z]{0,20}?" + price_pat, label, re.I):
        try:
            amt = float(m.group(2).replace(",", ""))
        except ValueError:
            continue
        cur = "HKD" if re.search(r"HK\$|MOP\$", m.group(1), re.I) else ("CNY" if "¥" in m.group(1) else "HKD")
        if re.search(r"最高減|最多減|立省|立減|up to|save ", label[max(0, m.start() - 8) : m.end()], re.I):
            continue
        out.append({"dest_city": m.group(1), "amount": amt, "currency": cur})
    # 价格后 dest
    for m in re.finditer(price_pat + r"[^\dA-Za-z]{0,16}?" + dest_pat, label, re.I):
        try:
            amt = float(m.group(1).replace(",", ""))
        except ValueError:
            continue
        cur = "HKD" if re.search(r"HK\$|MOP\$", m.group(0), re.I) else "HKD"
        city = m.group(2)
        if any(c.get("dest_city") == city and c.get("amount") == amt for c in out):
            continue
        if re.search(r"最高減|最多減|立省|立減|up to|save ", label[max(0, m.start() - 8) : m.end()], re.I):
            continue
        out.append({"dest_city": city, "amount": amt, "currency": cur})
    # 多目的地时仅有一个裸价 → 不绑定（返回空由调用方处理 unknown）
    dests = set(re.findall(dest_pat, label, re.I))
    if len(dests) >= 2 and len(out) < len(dests):
        # 绑定不完整：丢弃所有，避免错绑
        return []
    return out


def parse_deal_label(label: str, *, page_url: str) -> ParsedSignal | None:
    """机票线索：需机票语义 +（金额|双 IATA|促销词），过滤纯攻略标题。"""
    if not label or len(label) < 6:
        return None
    # 过期促销不应进入“当前可用”层
    if "过期" in label or "expired" in label.lower():
        return None
    _noise = (
        "怎么买",
        "如何买",
        "哪里订",
        "在哪买",
        "购买平台",
        "预订平台",
        "维权",
        "指南",
        "查询|",
        "选择",
        "潜规则",
        "手把手",
        "app",
        "App",
    )
    if any(n in label for n in _noise) and "元" not in label and "¥" not in label:
        return None
    low = label.lower()
    has_deal_kw = any(k in low or k in label for k in _DEAL_KW)
    has_flight_kw = any(k in low or k in label for k in _FARE_KW)
    if not has_deal_kw and not has_flight_kw:
        return None
    codes = [c for c in _IATA_RE.findall(label) if c.isalpha() and c.isupper()]
    skip = {
        "AND",
        "THE",
        "BUG",
        "YQ",
        "USA",
        "USD",
        "CNY",
        "VIP",
        "APP",
        "MAX",
        "MIN",
        "CEO",
        "NEW",
        "OLD",
        "FAQ",
        "PDF",
        "IPO",
        "ETF",
        "GDP",
        "UTC",
        "GMT",
        "FOR",
        "NOT",
        "ALL",
        "ONE",
        "TWO",
        "SET",
        "DAY",
        "GET",
        "WIN",
        "TOP",
        "BUS",
        "CAR",
        "TAX",
        "FEES",
        "FREE",
        "SALE",
        "DEAL",
        "HOT",
    }
    codes = [c for c in codes if c not in skip]
    origin = codes[0] if len(codes) >= 2 else None
    dest = codes[1] if len(codes) >= 2 else None
    price = None
    currency = None
    m = _PRICE_RE.search(label)
    if m:
        try:
            price = float(m.group(1).replace(",", ""))
            currency = "CNY"
        except ValueError:
            price = None
    if price is None:
        m_yen = re.search(r"[¥]\s*(\d[\d,]*)", label)
        if m_yen:
            try:
                price = float(m_yen.group(1).replace(",", ""))
                currency = "CNY"
            except ValueError:
                price = None
    if price is None:
        # N-004：多目的地就近绑定；不完整则不写 reported_total
        routes = extract_route_price_candidates(label)
        if len(routes) == 1:
            price = routes[0]["amount"]
            currency = routes[0]["currency"]
        elif len(routes) > 1:
            # 多线路各有价：取与 dest 更近的一条，无 dest 则第一条
            pick = routes[0]
            if dest:
                for r in routes:
                    if r.get("dest_city") and r["dest_city"] in (label or ""):
                        pick = r
                        break
            price = pick["amount"]
            currency = pick["currency"]
        else:
            m_hkd = re.search(r"HK\$?\s*(\d[\d,]*)", label, re.I)
            dests_found = set(
                re.findall(
                    r"(台湾|大阪|东京|首尔|曼谷|新加坡|台北|香港|上海|北京|成都|重庆|广州|深圳)",
                    label,
                )
            )
            if m_hkd and len(dests_found) <= 1:
                try:
                    price = float(m_hkd.group(1).replace(",", ""))
                    currency = "HKD"
                except ValueError:
                    price = None
            elif m_hkd and len(dests_found) >= 2:
                # 多目的地裸价：不绑定
                price = None
                currency = None
    if price is None:
        # 只匹配价格语境的 K/千：往返含税2.7K / 2.7k+ / 3.1K+；排除 20KG 行李
        m_k = re.search(
            r"(?<!\d)(\d+(?:\.\d+)?)\s*([Kk千])(?!\s*g)(?![A-Za-z])",
            label,
        )
        if m_k and has_flight_kw:
            try:
                price = float(m_k.group(1)) * 1000
                currency = "CNY"
            except ValueError:
                price = None
    # 仍需机票语义或双 IATA；金额/促销词再降噪
    if origin is None and not has_flight_kw:
        return None
    if price is None and origin is None and not has_deal_kw:
        return None
    # D-005/N-005：减免/优惠额/立省 ≠ 票价（简繁中英）
    if re.search(
        r"(最高减|最高減|最多减|最多減|立减|立減|立省|省下|可省|最多可省|节省|節省|優惠額|优惠额|折扣额|折上折|"
        r"up\s*to\s*HK\$|save\s*HK\$|save\s*¥|off\s*HK\$|減\s*HK\$|减\s*HK\$|省\s*HK\$|省\s*¥|立省)",
        label,
        re.I,
    ):
        if price is not None:
            # 保留原文，但不把减免当 reported_total
            price = None
            currency = None
    types: list[str] = []
    for t, kws in _RISK_KW.items():
        if any(k.lower() in low or k in label for k in kws):
            types.append(t)
    if not types:
        types = ["flash_sale"] if (has_flight_kw or origin) else ["unclassified"]
    return ParsedSignal(
        title=label[:200],
        raw_claim_text=label,
        url=page_url if page_url.startswith("http") else None,
        reported_total=price,
        currency=currency,
        origin_airport=origin,
        destination_airport=dest,
        deal_types=types,
        confidence="low",
    )


def parse_trip_label(label: str, *, page_url: str) -> ParsedSignal | None:
    """行程福利：券/折扣/祭典；区分门槛与减免额（满A减B）。"""
    if not label or len(label) < 4:
        return None
    low = label.lower()
    if not any(k in low or k in label for k in _TRIP_KW):
        return None
    if any(k in label for k in ("甩尾", "漏油", "错价票")):
        return None
    # 满X减Y：面值用减免额 Y，门槛记入 raw
    m_spent = re.search(r"满\s*(\d[\d,]*)\s*元\s*减\s*(\d[\d,]*)\s*元", label)
    price = None
    conditions_note = None
    if m_spent:
        try:
            price = float(m_spent.group(2).replace(",", ""))
            conditions_note = f"min_spend={m_spent.group(1).replace(',', '')}"
        except ValueError:
            price = None
    else:
        m = _PRICE_RE.search(label)
        if m:
            try:
                price = float(m.group(1).replace(",", ""))
            except ValueError:
                price = None
    return ParsedSignal(
        title=label[:200],
        raw_claim_text=(conditions_note + " " + label) if conditions_note else label,
        url=page_url if page_url.startswith("http") else None,
        reported_total=price,
        currency="CNY" if price is not None else None,
        deal_types=["unclassified"],
        confidence="low",
    )


_RAFFLE_NAV_LABELS = frozenset(
    {
        "contest archives",
        "blog giveaways",
        "add a sweepstakes",
        "monthly entry contests",
        "weekly entry contests",
        "daily entry contests",
        "single entry contests",
        "monthly sweepstakes",
        "weekly sweepstakes",
        "daily sweepstakes",
        "contest tips",
        "contests",
        "sweepstakes",
        "giveaways",
        "contestgirl",
        "sweepstakes today",
        "enter to win",
        "see more",
        "read more",
        "click here",
        "home",
        "about",
        "contact",
        "privacy",
        "terms",
        "submit",
        "login",
        "sign up",
        "register",
        "newsletter",
    }
)


def parse_raffle_label(label: str, *, page_url: str) -> ParsedSignal | None:
    """抽奖线索：giveaway/sweepstakes 等；并粗分奖品类别标签进 deal_types。"""
    if not label or len(label) < 8:
        return None
    low = " ".join(label.lower().split())
    if low in _RAFFLE_NAV_LABELS:
        return None
    # 聚合站导航/分类：纯 “Monthly/Weekly/Daily … Contests/Sweepstakes/Giveaways”
    if any(low.endswith(x) for x in (" contests", " sweepstakes", " giveaways")) and len(low.split()) <= 4:
        return None
    if low.startswith("add a ") or low in {"see all contests", "view all sweepstakes"}:
        return None
    keys = (
        "giveaway",
        "sweepstake",
        "contest",
        "enter to win",
        "win a trip",
        "win a free trip",
        "win flights",
        "free trip",
        "vacation package",
        "win a ",
        "win ",
        "airfare",
        "机票",
        "赠票",
        "免费旅行",
    )
    if not any(k in low or k in label for k in keys):
        return None
    types = ["unclassified"]
    if any(k in low for k in ("iphone", "android", "厨", "kitchen", "tripod", "手机")):
        types = ["prize_other"]
    elif any(k in low for k in ("mustang", "f-150", "bronco", "kia", "ev5", "truck", "suv", "vehicle", "car ", "汽车", "卡车")) and not any(
        k in low for k in ("flight", "airfare", "机票")
    ):
        types = ["prize_other"]  # 车辆/现金等非免费机票
    elif (
        any(k in low for k in ("cash", "$", "usd", "prize money", "现金"))
        and not any(k in low for k in ("trip", "vacation", "flight", "airfare", "hotel", "cruise"))
    ) or (
        any(k in low for k in ("boat", "lund", "fishing", "yacht", "船", "游艇"))
        and not any(k in low for k in ("flight", "airfare", "机票", "round-trip", "roundtrip"))
    ):
        types = ["prize_other"]
    elif any(k in low for k in ("hotel", "cruise", "resort", "邮轮", "酒店")) and not any(
        k in low for k in ("flight", "airfare", "机票", "round-trip", "roundtrip")
    ):
        types = ["lodging_or_cruise"]
    elif any(k in low or k in label for k in ("flight", "airfare", "机票", "round-trip", "roundtrip")):
        types = ["flight_giveaway"]
    elif any(
        k in low or k in label
        for k in ("trip", "vacation", "travel", "度假", "旅行", "vacation package")
    ):
        types = ["travel_package_unknown_air"]
    return ParsedSignal(
        title=label[:200],
        raw_claim_text=label,
        url=page_url if page_url.startswith("http") else None,
        confidence="low",
        deal_types=types,
    )


async def polite_delay(seconds: float) -> None:
    await asyncio.sleep(seconds)
