# 采集效率验收（真实 A/B）

- **生成时间：** 2026-11-01T00:53:52.842652+00:00
- **来源数：** 3

## A/B 对比

| 指标 | Round 1 (冷) | Round 2 (热) | 变化 |
|---|---|---|---|
| HTTP 请求 | 3 | 3 | = |
| 下载字节 | 308,648 | 308,648 | = |
| 来源数 | 3 | 3 | |

## 明细

- **FlyNext.hk** R1: {'round': 1, 'source': 'FlyNext.hk', 'http_requests': 1, 'bytes': 88369, 'elapsed_sec': 0.8, 'status': 'ok', 'parsed': 18, 'duplicate_content': False}
- **MainlyMiles RSS** R1: {'round': 1, 'source': 'MainlyMiles RSS', 'http_requests': 1, 'bytes': 199003, 'elapsed_sec': 0.87, 'status': 'ok', 'entries': 70, 'parsed': 70, 'duplicate_content': False}
- **Premium-Flights RSS** R1: {'round': 1, 'source': 'Premium-Flights RSS', 'http_requests': 1, 'bytes': 21276, 'elapsed_sec': 1.54, 'status': 'ok', 'entries': 12, 'parsed': 12, 'duplicate_content': False}
- **FlyNext.hk** R2: {'round': 2, 'source': 'FlyNext.hk', 'http_requests': 1, 'bytes': 88369, 'elapsed_sec': 0.31, 'status': 'ok', 'parsed': 18, 'duplicate_content': False}
- **MainlyMiles RSS** R2: {'round': 2, 'source': 'MainlyMiles RSS', 'http_requests': 1, 'bytes': 199003, 'elapsed_sec': 1.51, 'status': 'ok', 'entries': 70, 'parsed': 70, 'duplicate_content': False}
- **Premium-Flights RSS** R2: {'round': 2, 'source': 'Premium-Flights RSS', 'http_requests': 1, 'bytes': 21276, 'elapsed_sec': 0.75, 'status': 'ok', 'entries': 12, 'parsed': 12, 'duplicate_content': False}