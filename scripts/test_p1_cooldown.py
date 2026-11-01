"""P1-1 测试：虚拟时钟跨 27 小时，验证冷却不饿死来源。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.services.discovery.incremental import should_fetch


class FakeSource:
    def __init__(self, name, interval_h=24):
        self.name = name
        self.fetch_interval_hours = interval_h
        self.last_attempt_at = None
        self.last_result = None
        self.consecutive_failures = 0
        self.etag = None
        self.last_modified = None


def test_cooldown_skip_does_not_starve():
    """冷却跳过不应刷新 last_attempt_at，来源到期时必须能抓。"""
    src = FakeSource("test", interval_h=24)
    now = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)

    # 首次：应抓取
    ok, _ = should_fetch(src, now)
    assert ok is True, "首次应抓取"

    # 模拟抓取后设置 last_attempt_at
    src.last_attempt_at = now

    # 30 分钟后（Worker 间隔）：仍在冷却，跳过但不更新 last_attempt_at
    now2 = now + timedelta(minutes=30)
    ok2, _ = should_fetch(src, now2)
    assert ok2 is False, "30 分钟后仍在冷却"
    # 关键：last_attempt_at 不应被更新（这是修复的核心）
    assert src.last_attempt_at == now, "冷却跳过不应更新 last_attempt_at"

    # 24 小时后（来源间隔到期）：应恢复抓取
    now3 = now + timedelta(hours=24)
    ok3, _ = should_fetch(src, now3)
    assert ok3 is True, "24 小时后应恢复抓取"

    # 短时间内不重复请求
    src.last_attempt_at = now3
    now4 = now3 + timedelta(minutes=30)
    ok4, _ = should_fetch(src, now4)
    assert ok4 is False, "30 分钟内不应重复请求"

    print("PASS: cooldown skip does not starve sources")


def test_failure_backoff_preserved():
    """失败退避不因跳过而丢失。"""
    src = FakeSource("test", interval_h=24)
    now = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)

    # 首次失败
    src.last_attempt_at = now
    src.last_result = "failed"
    src.consecutive_failures = 1

    # 1 小时后仍在退避
    now2 = now + timedelta(hours=1)
    ok2, _ = should_fetch(src, now2)
    assert ok2 is False, "失败后 1 小时应退避"

    # 24 小时后应恢复（退避上限）
    now3 = now + timedelta(hours=25)
    ok3, _ = should_fetch(src, now3)
    assert ok3 is True, "25 小时后应恢复"

    print("PASS: failure backoff preserved")


def test_virtual_27h_worker_cycle():
    """30 分钟 Worker 间隔、24 小时来源间隔，跨 27 小时。"""
    src = FakeSource("test", interval_h=24)
    now = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)

    fetches = 0
    checks = 0
    t = now
    end = now + timedelta(hours=27)

    while t < end:
        checks += 1
        ok, _ = should_fetch(src, t)
        if ok:
            fetches += 1
            src.last_attempt_at = t
        # Worker 间隔 30 分钟
        t += timedelta(minutes=30)

    # 27 小时 / 24 小时间隔 ≈ 2 次抓取（0h 和 24h）
    assert fetches == 2, f"27 小时内应抓 2 次，实际 {fetches}"
    assert checks == 54, f"27 小时应检查 54 次，实际 {checks}"
    print(f"PASS: 27h cycle: {checks} checks, {fetches} fetches")


if __name__ == "__main__":
    test_cooldown_skip_does_not_starve()
    test_failure_backoff_preserved()
    test_virtual_27h_worker_cycle()
    print("\nALL P1-1 TESTS PASSED")
