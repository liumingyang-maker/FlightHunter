# 社交论坛来源集成

- **HEAD:** 4b0572eb4e27b156fb0ea367e7f76088453a35ae

## 数据契约（SocialPost）

| 字段 | 说明 |
|---|---|
| platform | reddit/bluesky/mastodon/flyertalk/kezhan |
| post_id | 稳定帖子键 |
| published_at | 发布时间 |
| route/currency/price | 机票语义 |
| source_trust | verified/community/unknown |
| is_bug_fare/is_fuel_dump | 风险标记 |
| cursor/sync_status | 增量同步状态 |

## 合法公开来源评估

| 平台 | 可用性 | 授权 | 状态 |
|---|---|---|---|
| Reddit | 公开 JSON | 免授权 | **候选** |
| FlyerTalk | 公开论坛 | 免授权 | **候选** |
| Mastodon | 公开 API | 免授权 | **候选** |
| Bluesky | API | 需授权 | **待授权** |
| 小红书/微博/抖音 | 无官方API | 需授权 | **候选导入** |

## 限制

- 不宣称全站采集
- 不绕过访问控制
- 不用未授权 Cookie
