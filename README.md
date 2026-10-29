# FlightHunter V1.0（R3）

面向个人的三引擎全球旅行机会平台：

1. **全球免费旅行抽奖**（Campaign / CampaignRound / EntryAttempt）
2. **行程福利与旅行卡包**（Trip / BenefitOffer / Wallet）
3. **全球低价机票捡漏雷达**（FareWatch / FareDealSignal / FareQuote / Risk）

设计基线：2026-10-29 R3；**一次交付完整 V1.0，不拆多版本发布。**

## 重要说明

- 本工程**全新创建**。未找到可迁移的旧 `flight_raffle_starter`，故不迁移历史数据；详见 `docs/ADR/0001-project-bootstrap.md`。
- 设计包中的示例价格、URL、日本 2027 行程均为 **fixture/模拟**，不代表真实库存或用户行程。
- 不自动购票/出票/付款/改签；不绕过 CAPTCHA / 2FA / 平台自动化禁令；不虚构资格结论。

## 独立审核（ChatGPT / 外部）

请阅读 **[docs/REVIEW_FOR_GPT.md](docs/REVIEW_FOR_GPT.md)** 与仓库法则 **[AGENTS.md](AGENTS.md)**。  
外部审核意见为建议；实现方结合设计包与合规边界独立取舍，未完全遵守的项会在后续报告中说明原因。


## 技术栈

Python 3.12 · uv · httpx · Pydantic v2 · SQLAlchemy 2 · Alembic · SQLite(FTS5) · FastAPI · Jinja2/HTMX · Playwright · pytest · ruff · mypy

## 快速开始

```powershell
# 1. 安装依赖
uv sync

# 2. 环境体检
uv run python -m app.cli doctor

# 3. 初始化安全种子数据（仅演示 fixture，无真实抓取）
uv run python -m app.cli seed --safe

# 4. 发现任务 dry-run
uv run python -m app.cli discover --dry-run

# 5. 启动 Web 控制台
uv run python -m app.cli web --host 127.0.0.1 --port 8765
```

浏览器打开 <http://127.0.0.1:8765/>。

## 开发命令

```powershell
uv run ruff check .
uv run ruff format .
uv run mypy app
uv run pytest -q
```

## 目录结构

```
app/
  cli.py            # typer CLI
  config.py         # YAML + 环境配置
  core/             # 错误码、状态机、时间、ID
  schemas/          # Pydantic 契约
  models/           # SQLAlchemy ORM
  db/               # session / seed
  alembic/          # 迁移
  services/         # 领域服务（trips/benefits/fare/...）
  adapters/         # 来源抓取适配器
  web/              # FastAPI + Jinja2
  scheduler/        # 周期任务
tests/              # 单测 / 集成 / fixture
docs/ADR/           # 架构决策记录
```

## 安全与合规边界

- 本地优先；默认绑定 `127.0.0.1`。
- 私人身份、Cookies、邮件令牌不进入 Git / 模型提示词 / 公有云端。
- 报名/领券默认 `PREFILL_AND_REVIEW`；`unknown` 提交态禁止自动重试。
- 社区爆料 ≠ 实时可买价；无合法报价源时前端显示未知。

## 许可证

MIT（代码开源；用户数据不随仓库分发）。
