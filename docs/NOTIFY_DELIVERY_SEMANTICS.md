# 通知送达语义（N1）

## 状态模型

- 事件键 `event_key`：`sha256(kind|title|entity_type|entity_id)[:24]` 或显式传入  
- 渠道：`console` / `windows_toast`  
- 持久表：`notification_deliveries(event_key, channel, status, attempts)`  

| status | 含义 |
|---|---|
| `recorded` | 仅站内/console，无外部送达要求 |
| `toast_delivered` | Windows toast 成功 |
| `failed` | 本次失败，可重试 |
| `exhausted` | 达到 `MAX_DELIVERY_ATTEMPTS=3`，不再外送 |

## 语义

| 目标 | 保证 | 不保证 |
|---|---|---|
| 成功后重复调用 | **不重复外送**（DB 状态跨进程） | — |
| 失败重试 | 最多 3 次，attempts 正确累计 | 退避策略（当前立即重试） |
| 进程崩溃（外送后未提交） | — | **exactly-once**；可能是 at-least-once 或 at-most-once |
| 进程崩溃（提交后未外送） | 可能漏送 | 需人工/下次扫描补偿 |

> **明确不宣称 exactly-once。** 当前策略是 **at-most-once（成功后）+ 失败上限 3**。  
> 崩溃窗口实验（外送与事务之间）列为 NOT_TESTED，见 TECH_DEBT #3。

## 测试

- `tests/unit/test_codex_q1_q5.py::test_q4_delivery_persists_and_limits`  
- `scripts/selfcheck_r_series.py` R-012/013  

## 真实桌面验证（NOT_TESTED）

1. toast 成功 → 重启进程 → 同一 event_key 不应再弹  
2. toast 失败（禁用通知权限）连续调用 → 仅 3 次  
3. 中文长标题/正文不抛 GBK 解码异常  
