"""P2-6 测试：文章/OCR 缓存读写。"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select

from app.config import load_settings
from app.db.session import create_db_engine, make_session_factory, prepare_engine
from app.models import ArticleCache, OCRCache
from app.services.discovery.cache import (
    get_article_cache,
    get_ocr_cache,
    save_article_cache,
    save_ocr_cache,
)


def test_article_cache_crud():
    """文章缓存 CRUD。"""
    tmp = Path(tempfile.mkdtemp(prefix="cache_test_"))
    cfg = tmp / "config.yaml"
    db = tmp / "test.db"
    cfg.write_text(f"storage:\n  sqlite_path: {db.as_posix()}\n", encoding="utf-8")

    s = load_settings(str(cfg), project_root=tmp)
    engine, factory, mig = prepare_engine(s)

    with factory() as session:
        # 保存
        ac = save_article_cache(
            session,
            "https://example.com/article/1",
            guid="guid-1",
            source_id="src-1",
            content_hash="hash-1",
            title="Test Article",
            published_at="2026-01-01",
        )
        session.commit()
        assert ac is not None

        # 查询
        found = get_article_cache(session, "https://example.com/article/1", guid="guid-1", source_id="src-1")
        assert found is not None
        assert found.title == "Test Article"

        # 更新内容哈希
        save_article_cache(
            session,
            "https://example.com/article/1",
            guid="guid-1",
            source_id="src-1",
            content_hash="hash-2",
        )
        session.commit()
        updated = get_article_cache(session, "https://example.com/article/1", guid="guid-1", source_id="src-1")
        assert updated.content_hash == "hash-2"

    engine.dispose()
    print("PASS: article cache CRUD")


def test_ocr_cache():
    """OCR 缓存读写。"""
    tmp = Path(tempfile.mkdtemp(prefix="ocr_test_"))
    cfg = tmp / "config.yaml"
    db = tmp / "test.db"
    cfg.write_text(f"storage:\n  sqlite_path: {db.as_posix()}\n", encoding="utf-8")

    s = load_settings(str(cfg), project_root=tmp)
    engine, factory, mig = prepare_engine(s)

    with factory() as session:
        # 保存
        save_ocr_cache(session, "img-hash-1", "OCR result text", ocr_lang="chi_sim+eng")
        session.commit()

        # 查询
        text = get_ocr_cache(session, "img-hash-1", "chi_sim+eng")
        assert text == "OCR result text"

        # 未命中
        text2 = get_ocr_cache(session, "img-hash-2", "chi_sim+eng")
        assert text2 is None

    engine.dispose()
    print("PASS: OCR cache")


def test_guid_scoped_by_source():
    """GUID 需考虑来源作用域。"""
    tmp = Path(tempfile.mkdtemp(prefix="guid_test_"))
    cfg = tmp / "config.yaml"
    db = tmp / "test.db"
    cfg.write_text(f"storage:\n  sqlite_path: {db.as_posix()}\n", encoding="utf-8")

    s = load_settings(str(cfg), project_root=tmp)
    engine, factory, mig = prepare_engine(s)

    with factory() as session:
        # 同 GUID 不同来源 → 不同缓存条目
        ac1 = save_article_cache(session, "https://a.com/1", guid="same-guid", source_id="src-a")
        ac2 = save_article_cache(session, "https://b.com/1", guid="same-guid", source_id="src-b")
        session.commit()
        assert ac1.id != ac2.id, "不同来源的同 GUID 应产生不同缓存键"

    engine.dispose()
    print("PASS: GUID scoped by source")


if __name__ == "__main__":
    test_article_cache_crud()
    test_ocr_cache()
    test_guid_scoped_by_source()
    print("\nALL P2-6 TESTS PASSED")
