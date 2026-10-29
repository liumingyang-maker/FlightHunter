# FlightHunter V1.0 — 第一次真实运行测试包（基线 `1d69efb`）

这个工具包不修改业务代码，不接入外部 AI API，不上传用户个人数据。它在仓库的 `data/live_tests/<时间戳>/snapshot/` 下通过 `git archive HEAD` 创建**隔离代码快照**，使用独立 SQLite，分开启动 Web、只读监控与限量外网抓取窗口。不是替代 FlightHunter 正式产品的后台监控。

## 先决条件

- Windows 11 + PowerShell 5.1 或 PowerShell 7；项目本机 `develop` HEAD 必须以 `1d69efb` 开头。
- 项目已有 `.venv/Scripts/python.exe`，且安装好了依赖（通常为 `uv sync --extra dev --python 3.12`）。
- 网络可访问目标公共网站；但必须尊重 robots、网站条款、403/429。测试不保证任何网站一定能抓取。
- 禁止把真实 Cookie、API Key、卡密、券码、用户姓名、旅客身份信息贴给 MiMo 或本工具包。

## 运行方法

1. 解压时把整个 `_first_live_test` 文件夹放在 FlightHunter **Git 仓库根目录**，与 `app/`、`pyproject.toml` 同级。
2. 在**仓库根目录**打开 PowerShell，执行：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\_first_live_test\1_start.ps1
```

3. 窗口 A 是 Web（`http://127.0.0.1:8765/`）；窗口 B 是只读诊断；窗口 C 是限量真实来源抓取。原控制台只会给出隔离结果路径。
4. 登录令牌由隔离快照 Web 首次启动时生成在 `snapshot/data/auth.json`；只在本机查看和输入，不复制到 MiMo 聊天。
5. 测试结束后打开 `data/live_tests/<时间戳>/RESULTS.md`，检查候选标题、官方核实情况、优惠资格与误报；通过 `CTRL+C` 停止 Web 与监控窗口。

## 首轮的执行顺序

1. `migrate`（**只创建隔离新库**）→ Schema 校验 → 注册实际公共来源（不注入 seed demo）
2. `doctor` + 三模块 `discover --dry-run`
3. `discover --module raffle --execute --limit 1`
4. `raffle-provenance --limit 1`
5. `discover --module trip --execute --limit 1`
6. `jp-benefits-scan`（其创建的日本行程仍是 **demo**）
7. `discover --module fare --execute --limit 1`
8. 输出数据库计数、监控事件与人工验收清单

所有执行均限定为公开页面读取，不点击真实活动报名/领券/付款。扫描按模块分批，至少间隔 12 秒。源站拒绝时是受限，不是自动绕过的理由。`worker` 不在首次测试中常驻运行：先排查完上述链路，再决定是否启用调度。

## 你给 MiMo 的输入（仅脱敏信息）

让 MiMo 在自己的 Windows/IDE 终端读取以下文件（**不要将整个数据库或 auth.json 上传给模型**）：

- `data/live_tests/<时间戳>/RESULTS.md`
- `data/live_tests/<时间戳>/alerts.jsonl`
- `data/live_tests/<时间戳>/logs/sweep.log`（**先检查并脱敏**）
- 相关源码路径与 traceback（不包括账户信息）

监控窗口的 `monitor.py` 是确定性规则巡检（并不是 MiMo 模型本身）。MiMo 需要另外打开其代码环境，把最新日志与源码进行关联分析。如果想让 MiMo **真正自动跟踪、分类、修复**，应由它在 Git 仓库追加结构化 instrumentation/事件总线，并用单独进程处理；不要把 API 密钥或完整 HTML 快照发送给模型。

## 首次测试的验收标准

| 模块 | 一次必须实际核对的事项 | 不应被算作成功的情况 |
|---|---|---|
| 抽奖 | 真实列表、候选原始出处、主办方官方页面、官方规则与资格字段 | 只抓到聚合列表，未核实就称 `verified` |
| 日本福利 | 实际网页、候选地理位置、领券/使用时间、限制条件、中文指南 | Time Out 提到活动，就认定能领取或在 2027 年使用 |
| 机票 | 信号与可查实报价的分离、时间与人数、是否可信来源 | 只有社区标题就报「两人可购、历史最低」 |
| 系统 | 数据库完整性、重复扫描幂等、异常代码、UI 数据一致、真实状态 | HTTP200、CLI 返回零退出码，却有效记录为 0 且未提示 |

要把来源失败拆成 `robots/terms`、`network/TLS`、`parser`、`schema`、`eligibility/rules`、`UI`、`authorization` 等类型。不保证真实站点一定存在可参加的抽奖或能用的优惠；空结果要有原因，不能为了过测试制造假数据。

## 这份 HEAD 已发现的待修问题

- `app/alembic/env.py::_url()` 的 `load_settings()` 忽略 CLI 显式 `--config`。已复现指定测试 DB 未生成而默认 DB 被迁移；本工具包通过**隔离工作目录 + 同目录 config.yaml** 防止误触实际库，但根本问题仍需 MiMo 修复。
- `app/web/routes/pages.py:home` 使用 `.where(not Trip.demo_only)`，已复现 API 正确显示 1 条真实行程而首页显示 0。
- `app/web/templates/campaigns.html` 表头与单元格错位、重复主办方信息；无官方链接时当前 UI 无法点击关联来源页。
- `app/services/raffle/provenance.py` 保存来源快照，但不会自动从聚合活动入口找到主办方官方规则；重复成功的聚合抓取目前可能重复写快照。
- `app/config.py` 有每域名最小间隔设置，但抓取适配器尚未统一执行；工具包通过各步骤间隔暂时缓和，不等于源代码已修好。

**注意**：本工具包未在用户 Windows 本机验证。不要把首次运行环境错误直接归因于代码问题；先检查 Python 版本、路径、端口与依赖。任何大量抓取、报名、授权登录或自动领券均需要另行授权与核验。
