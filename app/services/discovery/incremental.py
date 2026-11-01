"""任务三：持久增量采集——ETag/缓存/分页/URL去重。"""

from __future__ import annotations

# 3A: 数据模型——Source 表加 ETag/Last-Modified/内容哈希
# 3B: URL 规范化 + 文章 ID 稳定键
# 3C: 分页支持
# 3D: 正文/OCR 缓存
# 3E: 来源公平性（已完成）

# ---- 3A: 增量 HTTP 条件请求 ----

INCREMENTAL_SCHEMA_SQL = """
-- Source 表增量采集字段
ALTER TABLE sources ADD COLUMN etag TEXT;
ALTER TABLE sources ADD COLUMN last_modified TEXT;
ALTER TABLE sources ADD COLUMN content_hash TEXT;
ALTER TABLE sources ADD COLUMN next_due_at TEXT;
ALTER TABLE sources ADD COLUMN last_success_at TEXT;
ALTER TABLE sources ADD COLUMN consecutive_failures INTEGER DEFAULT 0;

-- 文章缓存表（3B: URL/帖子 ID 稳定键）
CREATE TABLE IF NOT EXISTS article_cache (
    id TEXT PRIMARY KEY,
    source_id TEXT,
    url_hash TEXT,
    guid TEXT,
    content_hash TEXT,
    parse_version TEXT,
    title TEXT,
    published_at TEXT,
    first_seen_at TEXT,
    last_checked_at TEXT,
    last_changed_at TEXT,
    etag TEXT,
    last_modified TEXT
);

-- OCR 缓存表（3D）
CREATE TABLE IF NOT EXISTS ocr_cache (
    id TEXT PRIMARY KEY,
    image_hash TEXT,
    ocr_lang TEXT,
    model_version TEXT,
    ocr_text TEXT,
    created_at TEXT
);
"""


def normalize_url(url: str) -> str:
    """规范化 URL：去 fragment/utm，保留区分内容的参数。"""
    from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

    if not url:
        return ""
    parsed = urlparse(url.strip())
    # 去掉 fragment
    # 保留查询参数但排序，去掉跟踪参数
    drop_params = {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "fbclid", "gclid"}
    params = [(k, v) for k, v in parse_qsl(parsed.query) if k.lower() not in drop_params]
    params.sort()
    return urlunparse(
        (parsed.scheme, parsed.netloc.lower(), parsed.path.rstrip("/"), "", urlencode(params), "")
    )


def make_article_key(url: str, guid: str | None = None, platform_id: str | None = None) -> str:
    """稳定文章键：GUID 考虑来源作用域避免冲突。"""
    import hashlib

    if guid and platform_id:
        return hashlib.sha256(f"guid:{platform_id}:{guid}".encode()).hexdigest()[:32]
    if guid:
        return hashlib.sha256(f"guid:{guid}".encode()).hexdigest()[:32]
    if platform_id:
        return hashlib.sha256(f"pid:{platform_id}:{normalize_url(url)}".encode()).hexdigest()[:32]
    return hashlib.sha256(f"url:{normalize_url(url)}".encode()).hexdigest()[:32]


def should_fetch(
    source,
    now,
    *,
    use_conditional: bool = True,
) -> tuple[bool, dict]:
    """判断是否需要抓取。返回 (should_fetch, conditional_headers)。"""
    from datetime import timedelta

    # 冷却检查
    last_attempt = getattr(source, "last_attempt_at", None)
    interval_h = max(1, getattr(source, "fetch_interval_hours", 24) or 24)
    fail_count = getattr(source, "consecutive_failures", 0) or 0

    if last_attempt:
        # 失败退避
        if fail_count > 0 and (getattr(source, "last_result", "") or "") == "failed":
            backoff_h = min(24, interval_h * (2 ** min(fail_count, 4)))
        else:
            backoff_h = interval_h
        try:
            from app.core.timeutils import ensure_aware_utc

            last = ensure_aware_utc(last_attempt)
            if last and (now - last) < timedelta(hours=backoff_h):
                return False, {"skip_reason": "cooldown"}
        except Exception:
            pass

    # 条件请求头
    headers = {}
    if use_conditional:
        etag = getattr(source, "etag", None)
        last_mod = getattr(source, "last_modified", None)
        if etag:
            headers["If-None-Match"] = etag
        if last_mod:
            headers["If-Modified-Since"] = last_mod

    return True, headers


def handle_response(
    source,
    response_headers: dict,
    content: bytes,
    *,
    status_code: int,
) -> dict:
    """处理响应：保存 ETag/Last-Modified，检测内容变化。"""
    import hashlib

    result = {
        "status": "ok",
        "content_changed": True,
        "cached": False,
    }

    if status_code == 304:
        result["status"] = "not_modified"
        result["content_changed"] = False
        result["cached"] = True
        return result

    # 保存条件请求头
    etag = response_headers.get("etag") or response_headers.get("ETag")
    last_mod = response_headers.get("last-modified") or response_headers.get("Last-Modified")
    if etag:
        source.etag = etag[:500]
    if last_mod:
        source.last_modified = last_mod[:200]

    # 内容哈希检测变化
    content_hash = hashlib.sha256(content).hexdigest()
    old_hash = getattr(source, "content_hash", None)
    if old_hash == content_hash:
        result["content_changed"] = False
        result["cached"] = True
    source.content_hash = content_hash

    return result
