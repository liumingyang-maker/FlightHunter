"""ID 与内容哈希工具。"""

from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any


def new_id() -> str:
    return str(uuid.uuid4())


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def stable_json_hash(payload: Any) -> str:
    """对 JSON 可序列化对象做稳定哈希（排序键）。"""
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return sha256_text(raw)


def content_hash_of_html(html: str) -> str:
    # 规范化空白，避免仅格式差异导致哈希变化
    normalized = " ".join(html.split())
    return sha256_text(normalized)


def idempotency_key(*parts: str) -> str:
    return sha256_text("|".join(parts))
