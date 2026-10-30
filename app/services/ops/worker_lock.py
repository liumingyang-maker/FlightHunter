"""Worker 单实例锁与心跳：当前用户目录下文件锁，防重复扫描。"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def _default_lock_path(settings) -> Path:
    from app.web.auth import _state_dir

    return _state_dir(settings) / "worker.lock"


def read_lock(lock_path: Path) -> dict[str, Any] | None:
    if not lock_path.is_file():
        return None
    try:
        data = json.loads(lock_path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _pid_alive(pid: int) -> bool:
    """Windows 上不能用 os.kill(pid,0) 探活（可能误杀/无效）。"""
    if pid <= 0:
        return False
    if os.name == "nt":
        import ctypes

        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        STILL_ACTIVE = 259
        handle = ctypes.windll.kernel32.OpenProcess(
            PROCESS_QUERY_LIMITED_INFORMATION, False, pid
        )
        if not handle:
            return False
        try:
            code = ctypes.c_ulong()
            ok = ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(code))
            return bool(ok) and code.value == STILL_ACTIVE
        finally:
            ctypes.windll.kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def acquire_worker_lock(settings, *, interval_seconds: int) -> tuple[bool, Path, str]:
    """返回 (acquired, lock_path, message)。崩溃残留锁且进程已死则接管。"""
    lock_path = _default_lock_path(settings)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    existing = read_lock(lock_path)
    now = datetime.now(UTC).isoformat(timespec="seconds")
    if existing:
        pid = int(existing.get("pid") or 0)
        if _pid_alive(pid) and pid != os.getpid():
            return False, lock_path, f"another worker alive pid={pid}"
        # stale lock → takeover
    payload = {
        "pid": os.getpid(),
        "acquired_at": now,
        "heartbeat_at": now,
        "interval_seconds": interval_seconds,
        "config": str(getattr(settings, "config_path", "") or ""),
        "sqlite": str(settings.storage.sqlite_path),
    }
    # O_EXCL create if absent; if exists and stale we rewrite
    tmp = lock_path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(lock_path)
    return True, lock_path, "acquired"


def heartbeat(lock_path: Path, *, interval_seconds: int, **extra: Any) -> None:
    payload = read_lock(lock_path) or {}
    payload.update(
        {
            "pid": os.getpid(),
            "heartbeat_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "interval_seconds": interval_seconds,
            **extra,
        }
    )
    lock_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def release_worker_lock(lock_path: Path, *, pid: int | None = None) -> None:
    cur = read_lock(lock_path)
    if not cur:
        return
    if pid is not None and int(cur.get("pid") or 0) != pid:
        return
    try:
        lock_path.unlink(missing_ok=True)
    except Exception:
        pass


def worker_status(settings) -> dict[str, Any]:
    lock_path = _default_lock_path(settings)
    data = read_lock(lock_path)
    alive = False
    if data and data.get("pid"):
        alive = _pid_alive(int(data["pid"]))
    return {
        "lock_path": str(lock_path),
        "exists": lock_path.is_file(),
        "alive": alive,
        "record": data,
    }
