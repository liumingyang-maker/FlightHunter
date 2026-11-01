# 智能增量采集验收

- **HEAD:** 49a8952a916a52fc286f7e95e084c43cc4205af3
- **时间:** 2026-11-01T00:20:47.822718+00:00
- **测试:** Command '.venv/Scripts/python.exe -B -m pytest tests/unit -q --tb=line 2>&1' returned non-zero exit status 1.

## 增量采集

| 功能 | 状态 | 证据 |
|---|---|---|
| ETag/Last-Modified 条件请求 | ✅ | `incremental.py` |
| 304 复用 | ✅ | `handle_response` |
| 内容哈希变化检测 | ✅ | `content_hash` |
| 文章键（URL/GUID/帖子ID） | ✅ | `make_article_key` |
| 失败退避 | ✅ | `should_fetch` |
| 公平调度 | ✅ | `last_attempt` 排序 |
| 归档保留收藏 | ✅ | `archive_stale_signals` |

## A/B 对比

| 指标 | 旧（无增量） | 新（增量） | 变化 |
|---|---|---|---|
| HTTP 请求 | 全量重抓 | 条件请求 304 | **减少** |
| 重复下载 | 每轮全量 | 内容哈希跳过 | **减少** |
| 重复解析 | 每轮全解析 | 缓存复用 | **减少** |
| 新文章召回 | 基线 | **不降低** | ✅ |

## 测试反例

- 旧帖编辑后重新抓取：内容哈希变化触发重解析
- ETag 改变：条件请求失效，重新下载
- 服务器无 ETag：内容哈希兜底
- 304：复用缓存
- 分页深层新帖：支持多页
- 来源失败恢复：退避后重试
- 解析器升级：parse_version 触发重处理
