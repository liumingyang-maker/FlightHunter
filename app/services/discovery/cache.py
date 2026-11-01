"""P2-6: 文章/OCR 缓存真实读写。"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from sqlalchemy import select

from app.models import ArticleCache, OCRCache


def get_article_cache(session, url: str, guid: str | None = None, source_id: str | None = None) -> ArticleCache | None:
    """查询文章缓存。GUID 需要考虑来源作用域避免冲突。"""
    from app.services.discovery.incremental import make_article_key

    art_key = make_article_key(url, guid=guid, platform_id=source_id)
    return session.scalar(select(ArticleCache).where(ArticleCache.url_hash == art_key))


def save_article_cache(
    session,
    url: str,
    *,
    guid: str | None = None,
    source_id: str | None = None,
    content_hash: str | None = None,
    parse_version: str = "v1",
    title: str | None = None,
    published_at: str | None = None,
    etag: str | None = None,
    last_modified: str | None = None,
) -> ArticleCache:
    """保存/更新文章缓存。"""
    from app.services.discovery.incremental import make_article_key

    art_key = make_article_key(url, guid=guid, platform_id=source_id)
    existing = session.scalar(select(ArticleCache).where(ArticleCache.url_hash == art_key))
    now = datetime.now(timezone.utc).isoformat()

    if existing:
        existing.last_checked_at = now
        if content_hash and existing.content_hash != content_hash:
            existing.content_hash = content_hash
            existing.last_changed_at = now
        if etag:
            existing.etag = etag
        if last_modified:
            existing.last_modified = last_modified
        if title:
            existing.title = title
        if published_at:
            existing.published_at = published_at
        session.flush()
        return existing

    ac = ArticleCache(
        id=art_key,
        source_id=source_id,
        url_hash=art_key,
        guid=guid,
        content_hash=content_hash,
        parse_version=parse_version,
        title=title,
        published_at=published_at,
        first_seen_at=now,
        last_checked_at=now,
        last_changed_at=now,
        etag=etag,
        last_modified=last_modified,
    )
    session.add(ac)
    session.flush()
    return ac


def get_ocr_cache(session, image_hash: str, ocr_lang: str = "chi_sim+eng") -> str | None:
    """查询 OCR 缓存。"""
    row = session.scalar(
        select(OCRCache).where(
            OCRCache.image_hash == image_hash,
            OCRCache.ocr_lang == ocr_lang,
        )
    )
    return row.ocr_text if row else None


def save_ocr_cache(
    session,
    image_hash: str,
    ocr_text: str,
    *,
    ocr_lang: str = "chi_sim+eng",
    model_version: str = "tesseract-5.4",
) -> None:
    """保存 OCR 缓存。"""
    existing = session.scalar(
        select(OCRCache).where(
            OCRCache.image_hash == image_hash,
            OCRCache.ocr_lang == ocr_lang,
            OCRCache.model_version == model_version,
        )
    )
    if existing:
        existing.ocr_text = ocr_text
    else:
        session.add(
            OCRCache(
                id=hashlib.sha256(f"{image_hash}:{ocr_lang}:{model_version}".encode()).hexdigest()[:32],
                image_hash=image_hash,
                ocr_lang=ocr_lang,
                model_version=model_version,
                ocr_text=ocr_text,
            )
        )
    session.flush()
