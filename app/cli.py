"""FlightHunter CLI。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import typer
from rich.console import Console
from rich.table import Table

from app import __version__
from app.config import load_settings, sqlite_path

app = typer.Typer(
    name="flighthunter",
    help="FlightHunter V1.0 — 个人全球旅行机会平台",
    add_completion=False,
    pretty_exceptions_enable=False,
)
console = Console()


def _project_root() -> Path:
    return Path.cwd()


def _load():
    settings = load_settings(project_root=_project_root())
    return settings


@app.callback()
def main_callback() -> None:
    """FlightHunter 命令入口。"""


@app.command()
def version() -> None:
    """显示版本。"""
    console.print(f"FlightHunter {__version__}")


@app.command()
def doctor(
    config: str | None = typer.Option(None, "--config", help="配置文件路径"),
) -> None:
    """环境与配置体检。"""
    settings = load_settings(config, project_root=_project_root())
    table = Table(title="FlightHunter Doctor")
    table.add_column("检查项")
    table.add_column("结果")

    db_path = sqlite_path(settings)
    table.add_row("版本", __version__)
    table.add_row("项目根", settings.project_root)
    table.add_row("配置文件", settings.config_path or "（使用内置默认值）")
    table.add_row("SQLite 路径", str(db_path))
    table.add_row("SQLite 可写目录", "OK" if db_path.parent.exists() else "FAIL")
    table.add_row("Demo 模式", "ON" if settings.app.demo_mode else "OFF")
    table.add_row("AI 已启用", "是" if settings.ai.enabled else "否（可无 Key 运行）")
    table.add_row(
        "报价适配器",
        "已配置" if settings.airfare_radar.quote_provider_enabled else "未配置（情报模式）",
    )
    table.add_row("Web 绑定", f"{settings.app.web_host}:{settings.app.web_port}")
    table.add_row("行程监控", "启用" if settings.trip_monitoring.enabled else "停用")
    table.add_row("机票雷达", "启用" if settings.airfare_radar.enabled else "停用")

    # 引擎探测
    try:
        from app.db.session import create_db_engine, init_db

        engine = create_db_engine(settings)
        init_db(engine)
        table.add_row("数据库连接", "OK")
        engine.dispose()
    except Exception as exc:
        table.add_row("数据库连接", f"FAIL: {exc}")

    console.print(table)
    if not settings.app.demo_mode:
        console.print("[yellow]注意：demo_mode 已关闭，请确认已完成用户配置。[/yellow]")
    raise typer.Exit(0)


@app.command()
def seed(
    safe: bool = typer.Option(True, "--safe/--no-safe", help="仅写入安全 fixture"),
    config: str | None = typer.Option(None, "--config"),
    travel_plan: str | None = typer.Option(None, "--travel-plan", help="travel_plan.example.json"),
    fare_signal: str | None = typer.Option(None, "--fare-signal", help="fare_signal.example.json"),
) -> None:
    """初始化数据库并写入安全种子（demo fixture）。"""
    settings = load_settings(config, project_root=_project_root())
    from app.db.seed import import_design_fixtures, seed_safe_fixtures
    from app.db.session import create_db_engine, init_db, make_session_factory, session_scope

    engine = create_db_engine(settings)
    init_db(engine)
    factory = make_session_factory(engine)
    root = _project_root()

    with session_scope(factory) as session:
        summary = seed_safe_fixtures(session, settings, project_root=root)
        extras: dict[str, Any] = {}
        if travel_plan:
            extras["travel_plan"] = travel_plan
        if fare_signal:
            extras["fare_signal"] = fare_signal
        if extras:
            imported = import_design_fixtures(
                session,
                settings,
                travel_plan_path=Path(travel_plan) if travel_plan else None,
                fare_signal_path=Path(fare_signal) if fare_signal else None,
            )
            summary["imported"] = imported
        console.print_json(json.dumps(summary, ensure_ascii=False, default=str))
        console.print("[green]seed 完成（全部为 demo fixture）[/green]")
    engine.dispose()


@app.command()
def discover(
    dry_run: bool = typer.Option(True, "--dry-run/--execute", help="默认 dry-run"),
    module: str = typer.Option("fare", "--module", help="fare|trip|raffle|all"),
    config: str | None = typer.Option(None, "--config"),
    limit: int = typer.Option(5, "--limit", help="最多尝试的来源数"),
) -> None:
    """发现任务：dry-run 不联网；--execute 真实调用适配器并入库信号/匹配。"""
    import asyncio

    settings = load_settings(config, project_root=_project_root())
    from app.core.ids import idempotency_key, new_id
    from app.core.timeutils import utc_now
    from app.db.session import create_db_engine, init_db, make_session_factory, session_scope
    from app.models import TaskRun
    from app.services.discovery.service import run_discovery

    engine = create_db_engine(settings)
    init_db(engine)
    factory = make_session_factory(engine)

    with session_scope(factory) as session:
        console.print(f"发现模式: {'DRY-RUN' if dry_run else 'EXECUTE'} · 模块: {module}")
        results = asyncio.run(
            run_discovery(
                session,
                settings,
                module=module,
                dry_run=dry_run,
                limit=limit,
                persist_signals=not dry_run,
                after_fetch=not dry_run,
            )
        )
        table = Table(title="发现结果")
        table.add_column("来源/步骤")
        table.add_column("状态")
        table.add_column("详情")
        for r in results:
            sid = r.get("source_id") or "-"
            detail = r.get("message") or ""
            if r.get("signals_persisted") is not None:
                detail += (
                    f" | signals={r.get('signals_persisted')} offers={r.get('offers_persisted')}"
                )
            if r.get("status") == "post_match":
                detail = f"matches={r.get('matches')} alerts={r.get('alerts')}"
            table.add_row(str(sid)[:12], str(r.get("status")), detail)
        console.print(table)

        key = idempotency_key(
            "discover_batch", module, "dry" if dry_run else "exec", utc_now().strftime("%Y%m%d%H%M")
        )
        ok = sum(1 for r in results if r.get("status") == "ok")
        failed = sum(1 for r in results if r.get("status") in ("failed", "denied", "manual_only"))
        run_status = "completed"
        if results and ok == 0 and failed > 0:
            run_status = "failed"
        elif ok and failed:
            run_status = "partial"
        session.add(
            TaskRun(
                id=new_id(),
                task_type="source_discovery_batch",
                status="skipped" if dry_run else run_status,
                idempotency_key=key,
                dry_run=dry_run,
                message=json.dumps(
                    [
                        {
                            k: r.get(k)
                            for k in (
                                "source_id",
                                "status",
                                "signals_persisted",
                                "offers_persisted",
                            )
                        }
                        for r in results
                    ],
                    ensure_ascii=False,
                    default=str,
                )[:4000],
                started_at=utc_now(),
                finished_at=utc_now(),
            )
        )
        session.flush()
        console.print(
            f"[green]完成：ok={ok} failed={failed} · 总步骤={len(results)} · batch={run_status}[/green]"
        )
    engine.dispose()


@app.command()
def web(
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8765, "--port"),
    config: str | None = typer.Option(None, "--config"),
) -> None:
    """启动本地 Web 控制台。"""
    settings = load_settings(config, project_root=_project_root())
    if host not in ("127.0.0.1", "localhost", "::1"):
        console.print(
            "[yellow]警告：非本机绑定需要额外认证与 TLS，V1.0 默认仅建议 127.0.0.1。[/yellow]"
        )
    import uvicorn

    from app.web.app import create_app

    application = create_app(settings)
    console.print(f"[green]FlightHunter Web → http://{host}:{port}/[/green]")
    uvicorn.run(application, host=host, port=port, log_level="info")


@app.command()
def migrate(
    config: str | None = typer.Option(None, "--config"),
    revision: str = typer.Option("head", "--revision"),
) -> None:
    """运行 Alembic 迁移（或 create_all 兜底）。"""
    settings = load_settings(config, project_root=_project_root())
    from alembic.config import Config

    from alembic import command

    root = _project_root()
    ini = root / "alembic.ini"
    if ini.is_file():
        cfg = Config(str(ini))
        cfg.set_main_option("script_location", str(root / "app" / "alembic"))
        cfg.set_main_option(
            "sqlalchemy.url",
            f"sqlite+pysqlite:///{sqlite_path(settings).as_posix()}",
        )
        command.upgrade(cfg, revision)
        console.print("[green]Alembic 迁移完成[/green]")
    else:
        from app.db.session import create_db_engine, init_db

        engine = create_db_engine(settings)
        init_db(engine)
        console.print("[yellow]未找到 alembic.ini，已使用 metadata.create_all[/yellow]")
        engine.dispose()


@app.command("list-trips")
def list_trips(config: str | None = typer.Option(None, "--config")) -> None:
    """列出行程。"""
    settings = load_settings(config, project_root=_project_root())
    from sqlalchemy import select

    from app.db.session import create_db_engine, init_db, make_session_factory, session_scope
    from app.models import Trip

    engine = create_db_engine(settings)
    init_db(engine)
    factory = make_session_factory(engine)
    with session_scope(factory) as session:
        trips = session.scalars(select(Trip)).all()
        table = Table(title="行程")
        table.add_column("ID")
        table.add_column("名称")
        table.add_column("国家")
        table.add_column("日期")
        table.add_column("demo")
        table.add_column("扫描")
        for t in trips:
            table.add_row(
                t.id[:8],
                t.label,
                t.destination_country_code,
                f"{t.local_start_date} ~ {t.local_end_date}",
                "是" if t.demo_only else "否",
                t.scan_status,
            )
        console.print(table)
    engine.dispose()


@app.command("list-deals")
def list_deals(
    risk: str | None = typer.Option(None, "--risk"),
    config: str | None = typer.Option(None, "--config"),
) -> None:
    """列出机票机会。"""
    settings = load_settings(config, project_root=_project_root())
    from sqlalchemy import select

    from app.db.session import create_db_engine, init_db, make_session_factory, session_scope
    from app.models import FareDeal

    engine = create_db_engine(settings)
    init_db(engine)
    factory = make_session_factory(engine)
    with session_scope(factory) as session:
        stmt = select(FareDeal).order_by(FareDeal.last_seen_utc.desc())
        if risk:
            stmt = stmt.where(FareDeal.risk_tier == risk)
        deals = session.scalars(stmt.limit(50)).all()
        table = Table(title="机票机会")
        table.add_column("航线")
        table.add_column("子类型")
        table.add_column("风险")
        table.add_column("状态")
        table.add_column("购票")
        for d in deals:
            table.add_row(
                f"{d.origin}-{d.destination}",
                d.offer_subtypes,
                d.risk_tier,
                d.status,
                d.booking_status,
            )
        console.print(table)
    engine.dispose()


if __name__ == "__main__":
    app()
