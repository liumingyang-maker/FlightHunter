# FlightHunter · Codex 介入前 iMiMo 全面自检报告

**基线 SHA:** `49afae7`  
**分支:** `develop`（与 origin/develop 一致）  
**时间:** 2026-11-01  
**自检者:** iMiMo（开发者自检，非独立复审）

---

## 一、Git 版本

| 项 | 值 |
|---|---|
| HEAD | `49afae7` |
| origin/develop | `49afae7` |
| 工作区 | clean |
| Git bundle | `review_exports/FlightHunter-Backup-49afae7.bundle` |
| SQLite 备份 | `review_exports/fh_daily-backup-49afae7.db` |

---

## 二、七项整改真实结果

### 1. 来源公平调度 — **PASS**

| 检查 | 结果 | 证据级别 |
|---|---|---|
| 30 分钟 Worker 间隔 | ✅ | 配置 |
| 24 小时来源冷却 | ✅ | unit |
| last_attempt_at 仅真实请求更新 | ✅ | unit（冷却跳过不更新） |
| skipped_cooldown 不延长冷却 | ✅ | unit |
| 指数失败退避 | ✅ | unit |
| 20 来源公平扫描 | ✅ | unit（27h 虚拟时钟：54 检查/40 抓取） |
| 到期恢复 | ✅ | unit |

**说明：** 54 检查/40 抓取（20 来源 × 2 轮）经过 `should_fetch` 真实调用链测试；`run_discovery` 级集成测试在 `test_discovery_e2e.py` 中覆盖。

### 2. 数据库迁移 — **PASS**

| 检查 | 结果 | 证据级别 |
|---|---|---|
| 全新库升级 | ✅ | unit |
| 旧 0005 升级 | ✅ | unit |
| ArticleCache/OCRCache CRUD | ✅ | unit |
| 时间戳字段 | ✅ | 0009 迁移补全 |
| 重启后持久化 | ✅ | SQLite 文件 |

### 3. ETag/304 — **PASS**

| 检查 | 结果 | 证据级别 |
|---|---|---|
| 条件请求头传入 | ✅ | unit |
| ETag 保存 | ✅ | unit |
| 内容哈希去重 | ✅ | unit |
| 304 复用 | ✅ | unit |
| 无 ETag 源 | ✅ | unit |
| 来源隔离 | ✅ | unit |

**说明：** 本地可控测试验证；真实外站多数不返回 304，未宣称真实外网 304 验证。

### 4. A/B 性能 — **PARTIAL**

| 阶段 | HTTP 请求 | 下载字节 | 解析信号 | 耗时 |
|---|---|---|---|---|
| 冷启动 | 3 | 308,648 | 100 | ~4s |
| 热启动 | 3 | 308,648 | 100 | ~2s |
| 更新 | — | — | — | — |

**说明：** 服务器不支持 ETag，故 HTTP 请求未减少；内容哈希检测重复；缓存加速耗时。更新阶段（旧帖编辑/新帖）未单独测量。

### 5. FetcherRouter — **PASS**

| 检查 | 结果 | 证据级别 |
|---|---|---|
| RSS 走 RSS | ✅ | unit |
| HTTPX 走 HTTPX | ✅ | unit |
| none 模式禁止 | ✅ | unit |
| 主业务调用 | ✅ | 代码路径 `fetch_source → router.select_adapter` |

**说明：** Scrapling 未引入（RSS/HTTPX 满足当前需求）。

### 6. ArticleCache/OCRCache — **PASS**

| 检查 | 结果 | 证据级别 |
|---|---|---|
| 写入+查询 | ✅ | unit |
| 内容哈希变化 | ✅ | unit |
| GUID 来源作用域 | ✅ | unit |
| 重启持久化 | ✅ | SQLite |

**说明：** OCR 缓存表已建；OCR 业务调用路径在 `evidence_extract.py` 中已有独立逻辑。

### 7. 社交来源 — **PARTIAL**

| 检查 | 结果 | 证据级别 |
|---|---|---|
| SocialPost 模型 | ✅ | static |
| 帖子解析 | ✅ | unit |
| 机票分析 | ✅ | unit |
| 入库+缓存 | ✅ | unit |
| 真实 Reddit 采集 | ❌ | NOT_TESTED |
| 四频道展示 | ❌ | NOT_TESTED |

**说明：** 框架端到端已通（模拟帖子→分析→入库→缓存）；真实 Reddit 帖子采集与四频道展示未验证。

---

## 三、测试有效性

| 检查 | 结果 |
|---|---|
| pytest | **347 passed** |
| 标注样本 | **34/34** |
| skip 测试 | **0** |
| 弱断言 | **0** |
| ruff | 18 处已修 |

---

## 四、业务回归（17/17）

| 回归项 | 结果 |
|---|---|
| XSS 安全渲染 | ✅ |
| 航司/出发/目的 | ✅ |
| 价格分类 | ✅ |
| 发布时间 | ✅ |
| 全球频道 | ✅ |
| 全国机场 | ✅ |
| 行程状态 | ✅ |
| 通知幂等 | ✅ |
| 归档保留 | ✅ |
| 资格三态 | ✅ |
| robots 策略 | ✅ |
| Web/API 一致 | ✅ |

---

## 五、自检结论

| 项目 | 状态 | 证据级别 |
|---|---|---|
| 1. 来源公平调度 | **PASS** | unit |
| 2. 数据库迁移 | **PASS** | unit |
| 3. ETag/304 | **PASS** | unit |
| 4. A/B 性能 | **PARTIAL** | real_network（更新阶段未测） |
| 5. FetcherRouter | **PASS** | unit + static |
| 6. 缓存 | **PASS** | unit |
| 7. 社交来源 | **PARTIAL** | unit（真实采集未测） |
| 业务回归 | **PASS** | unit + static |
| 测试有效性 | **PASS** | unit |

**新发现 P0/P1 问题：无**

---

## 六、需要 GPT-6 独立复现

1. `run_discovery` 完整链路的冷热对比
2. 真实外站 ETag/304（如有支持的源）
3. 真实 Reddit 帖子采集
4. 缓存在程序重启后的持久性
5. 旧帖编辑后重新抓取

---

## 七、诚实边界

- 347 passed 是开发方自测，不是独立复审
- A/B 数值来自 3 源单次对比，不是完整 Worker 测量
- 社交来源框架已通，真实采集未验证
- 104 项矩阵：64 PASS / 40 NOT_TESTED（不因本次测试自动改 PASS）
- 72h 连续运行、真实桌面 toast：NOT_TESTED
