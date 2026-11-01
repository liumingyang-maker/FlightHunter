"""P1-3 测试：ETag/304 条件请求。"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx

from app.adapters.html_fetcher import HttpxFetchAdapter
from app.config import Settings
from app.services.discovery.incremental import handle_response, should_fetch


class FakeSource:
    def __init__(self):
        self.name = "test"
        self.fetch_interval_hours = 1
        self.last_attempt_at = None
        self.last_result = None
        self.consecutive_failures = 0
        self.etag = None
        self.last_modified = None
        self.content_hash = None


def test_etag_conditional_request():
    """有 ETag 时发送 If-None-Match。"""
    src = FakeSource()
    src.last_attempt_at = None
    ok, headers = should_fetch(src, None, use_conditional=True)
    assert ok is True
    assert "If-None-Match" not in headers  # 首次无 ETag

    # 设置 ETag
    src.etag = "abc123"
    src.last_attempt_at = None
    ok2, headers2 = should_fetch(src, None, use_conditional=True)
    assert ok2 is True
    assert headers2.get("If-None-Match") == "abc123"
    print("PASS: ETag conditional request")


def test_304_handling():
    """304 → 复用缓存，不当新文章。"""
    src = FakeSource()
    result = handle_response(
        src,
        {"etag": "new-etag", "last-modified": "Wed, 01 Jan 2026 00:00:00 GMT"},
        b"same content",
        status_code=304,
    )
    assert result["status"] == "not_modified"
    assert result["content_changed"] is False
    assert result["cached"] is True
    print("PASS: 304 handling")


def test_content_hash_detection():
    """内容哈希不变 → 不重复解析。"""
    src = FakeSource()
    result1 = handle_response(
        src,
        {},
        b"hello world",
        status_code=200,
    )
    assert result1["content_changed"] is True

    result2 = handle_response(
        src,
        {},
        b"hello world",
        status_code=200,
    )
    assert result2["content_changed"] is False
    assert result2["cached"] is True
    print("PASS: content hash detection")


def test_etag_change_triggers_refetch():
    """ETag 改变 → 重新处理。"""
    src = FakeSource()
    result1 = handle_response(
        src,
        {"etag": "v1"},
        b"content v1",
        status_code=200,
    )
    assert result1["content_changed"] is True

    result2 = handle_response(
        src,
        {"etag": "v2"},
        b"content v2",
        status_code=200,
    )
    assert result2["content_changed"] is True
    assert src.etag == "v2"
    print("PASS: ETag change triggers refetch")


if __name__ == "__main__":
    test_etag_conditional_request()
    test_304_handling()
    test_content_hash_detection()
    test_etag_change_triggers_refetch()
    print("\nALL P1-3 TESTS PASSED")
