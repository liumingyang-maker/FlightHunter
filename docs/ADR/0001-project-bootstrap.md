# ADR-0001：工程从零创建与旧项目衔接

## 状态

已接受（2026-10-29）

## 背景

设计包 `03_Codex_总任务说明.md` 要求：若存在旧 `flight_raffle_starter`，可迁移 13 条示例与原型思路并打上 `legacy_seed` / `verification_status=needs_review`；若不存在，则新建标准工程并写明原因。

## 决策

1. **未找到** `flight_raffle_starter` 项目目录或压缩包，因此**全新创建** FlightHunter 标准工程，不迁移旧数据。
2. 种子数据全部来自设计包中的 **安全 fixture**（`travel_plan.example.json`、`fare_signal.example.json` 及文档内 schema 示例），并明确标记 `demo_only=true` 或示例来源。
3. 技术选型严格按设计包：Python 3.12、uv、FastAPI、SQLAlchemy 2、Alembic、SQLite、Pydantic v2、Jinja2/HTMX、Playwright、pytest。
4. Git 默认在 `develop` 分支迭代；`main` 仅作稳定基线。

## 后果

- 无历史「当前有效抽奖」假设被继承。
- 所有活动/优惠/票价记录从 `candidate` / `needs_review` / `not_queried` 等保守状态起步。
- 后续若用户提供旧项目路径，可另开 ADR 评估选择性迁移。
