"""本地 .eml 模拟信箱扫描（无需 IMAP）。"""

from __future__ import annotations

import email
import re
from email import policy
from pathlib import Path
from typing import Any

_WIN = re.compile(r"(congratulations|you (have )?won|中奖|恭喜)", re.I)


def scan_eml_dir(directory: Path, *, limit: int = 50) -> dict[str, Any]:
    if not directory.is_dir():
        return {"status": "blocked", "message": f"目录不存在: {directory}", "candidates": []}
    cands = []
    files = sorted(directory.glob("*.eml"))[-limit:]
    for f in files:
        try:
            msg = email.message_from_bytes(f.read_bytes(), policy=policy.default)
        except Exception:
            continue
        subject = str(msg.get("Subject", ""))
        sender = str(msg.get("From", ""))
        body = ""
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_type() == "text/plain":
                    try:
                        body = part.get_content()[:400]
                    except Exception:
                        body = ""
                    break
        else:
            try:
                body = msg.get_content()[:400]
            except Exception:
                body = ""
        if _WIN.search(subject) or _WIN.search(body):
            cands.append(
                {
                    "message_id": str(msg.get("Message-ID", f.stem)),
                    "subject": subject[:200],
                    "sender": sender[:200],
                    "file": f.name,
                    "confidence": "low",
                    "needs_human": True,
                    "note": "本地 eml 候选；不会自动认定中奖",
                }
            )
    return {
        "status": "ok",
        "candidates": cands,
        "message": f"扫描 {len(files)} 个 eml，候选 {len(cands)}（均需人工确认）",
    }
