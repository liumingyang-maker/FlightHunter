"""FlightHunter CLI。"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import typer
from rich.console import Console
from rich.table import Table

from app import __version__
from app.config import load_settings, sqlite_path
from app.db.cli_migrate_hint import report_migration

app = typer.Typer(
    name="flighthunter",
    help="FlightHunter V1.0 — 个人全球旅行机会平台",
    add_completion=False,
    pretty_exceptions_enable=False,
)
console = Console()


def _project_root() -> Path:
    """仓库根：基于 app 包位置，避免 cwd 不同导致锁/库路径错乱。"""
    return Path(__file__).resolve().parent.parent


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

    # C14-02：doctor 只读，不 create_all、不迁移；仅报告版本
    try:
        from app.db.session import check_alembic_head

        report = check_alembic_head(settings)
        table.add_row("数据库连接", "OK" if report.get("exists") else "OK（新库尚未创建）")
        table.add_row("迁移版本", str(report.get("alembic_version") or "（无版本表）"))
        table.add_row("Alembic head", str(report.get("head") or "unknown"))
        table.add_row("迁移状态", str(report.get("state") or "unknown"))
        if report.get("state") in ("no_version_table", "outdated"):
            table.add_row(
                "迁移提示",
                "请备份后显式执行: python -m alembic upgrade head（doctor 不改表）",
            )
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
    from app.db.session import (
        prepare_engine,
        session_scope,
    )

    engine, factory, mig = prepare_engine(settings)
    report_migration(mig)
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
    from app.db.session import (
        prepare_engine,
        session_scope,
    )
    from app.models import TaskRun
    from app.services.discovery.service import run_discovery

    engine, factory, mig = prepare_engine(settings)
    report_migration(mig)

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
            if r.get("signals_persisted") is not None or r.get("raffles_persisted") is not None:
                detail += (
                    f" | signals={r.get('signals_persisted')}"
                    f" offers={r.get('offers_persisted')}"
                    f" raffles={r.get('raffles_persisted')}"
                )
            if r.get("status") == "post_match":
                detail = f"matches={r.get('matches')} alerts={r.get('alerts')}"
            table.add_row(str(sid)[:12], str(r.get("status")), detail)
        console.print(table)

        key = idempotency_key(
            "discover_batch", module, "dry" if dry_run else "exec", utc_now().strftime("%Y%m%d%H%M")
        )
        ok = sum(1 for r in results if r.get("status") in {"ok", "ok_zero"})
        failed = sum(1 for r in results if r.get("status") in ("failed", "denied", "manual_only"))
        source_rows = [r for r in results if isinstance(r, dict) and r.get("source_id")]
        if dry_run:
            run_status = "skipped"
            skip_reason = "dry_run"
        elif not source_rows:
            # 冷却/过滤导致无来源可抓：预期跳过，不是失败
            run_status = "skipped"
            skip_reason = "cooldown_or_no_due_source"
        elif ok == 0 and failed and not source_rows:
            run_status = "blocked"
            skip_reason = "all_sources_blocked"
        elif failed and ok:
            run_status = "partial"
            skip_reason = "partial_source_failures"
        elif failed and not ok:
            run_status = "failed"
            skip_reason = "all_sources_failed"
        else:
            run_status = "completed"
            skip_reason = None
        if skip_reason:
            console.print(f"[yellow]batch_status={run_status} reason={skip_reason}[/yellow]")
        session.add(
            TaskRun(
                id=new_id(),
                task_type="source_discovery_batch",
                status="skipped" if dry_run else run_status,
                idempotency_key=key,
                dry_run=dry_run,
                message=json.dumps(
                    {
                        "skip_reason": skip_reason,
                        "steps": [
                            {
                                k: r.get(k)
                                for k in (
                                    "source_id",
                                    "status",
                                    "signals_persisted",
                                    "offers_persisted",
                                    "raffles_persisted",
                                    "message",
                                    "error_code",
                                )
                            }
                            for r in results
                        ],
                    },
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


@app.command("source-health")
def source_health_cmd(
    config: str | None = typer.Option(None, "--config"),
    module: str = typer.Option("fare", "--module"),
    window_hours: int = typer.Option(24, "--window-hours"),
) -> None:
    """来源健康：历史成功 vs 本轮成功/失败/冷却/零解析/有价值。"""
    settings = load_settings(config, project_root=_project_root())
    from app.db.session import (
        prepare_engine,
        session_scope,
    )
    from app.services.ops.source_health import source_health_report

    engine, factory, mig = prepare_engine(settings)
    report_migration(mig)
    with session_scope(factory) as session:
        report = source_health_report(session, module=module or None, window_hours=window_hours)
        console.print_json(json.dumps(report, ensure_ascii=False, default=str))
    engine.dispose()


@app.command("confirm-trip")
def confirm_trip_cmd(
    trip_id: str = typer.Argument(...),
    config: str | None = typer.Option(None, "--config"),
) -> None:
    """确认真实行程并启动正式福利/扫描（demo 不可）。"""
    settings = load_settings(config, project_root=_project_root())
    from app.db.session import (
        prepare_engine,
        session_scope,
    )
    from app.services.trips.service import confirm_trip

    engine, factory, mig = prepare_engine(settings)
    report_migration(mig)
    with session_scope(factory) as session:
        trip = confirm_trip(session, settings, trip_id)
        session.commit()
        console.print(f"[green]已确认行程 {trip.id} · {trip.label}[/green]")
        console.print(f"scan_registered={trip.scan_registered} confirmed={trip.confirmed}")
    engine.dispose()


@app.command("list-trips")
def list_trips(config: str | None = typer.Option(None, "--config")) -> None:
    """列出行程。"""
    settings = load_settings(config, project_root=_project_root())
    from sqlalchemy import select

    from app.db.session import (
        prepare_engine,
        session_scope,
    )
    from app.models import Trip

    engine, factory, mig = prepare_engine(settings)
    report_migration(mig)
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


@app.command("scan-due")
def scan_due(
    execute: bool = typer.Option(False, "--execute", help="真实执行发现（默认 dry-run）"),
    config: str | None = typer.Option(None, "--config"),
    limit: int = typer.Option(10, "--limit"),
) -> None:
    """执行到期的行程扫描订阅。--execute 才访问网络来源。"""
    settings = load_settings(config, project_root=_project_root())
    from app.db.session import (
        prepare_engine,
        session_scope,
    )
    from app.scheduler.jobs import run_due_scans

    engine, factory, mig = prepare_engine(settings)
    report_migration(mig)
    with session_scope(factory) as session:
        runs = run_due_scans(
            session,
            settings,
            dry_run=not execute,
            limit=limit,
            include_raffle_pipeline=execute,
        )
        table = Table(title="到期扫描结果")
        table.add_column("任务")
        table.add_column("状态")
        table.add_column("dry")
        for r in runs:
            table.add_row(r.task_type, r.status, "Y" if r.dry_run else "N")
        console.print(table)
        console.print(f"[green]完成 {len(runs)} 个订阅扫描[/green]")
    engine.dispose()


@app.command("intel-quality")
def intel_quality_cmd(
    config: str | None = typer.Option(None, "--config"),
) -> None:
    """国际机票情报质量统计（新发现/城市匹配/过期/重复/链接抽样）。"""
    settings = load_settings(config, project_root=_project_root())
    from app.db.session import (
        prepare_engine,
        session_scope,
    )
    from app.services.fare.intel import intel_quality_stats

    engine, factory, mig = prepare_engine(settings)
    report_migration(mig)
    with session_scope(factory) as session:
        console.print_json(json.dumps(intel_quality_stats(session), ensure_ascii=False, default=str))
    engine.dispose()


@app.command("worker-status")
def worker_status_cmd(
    config: str | None = typer.Option(None, "--config"),
) -> None:
    """查看 worker 单实例锁与心跳。"""
    settings = load_settings(config, project_root=_project_root())
    from app.services.ops.worker_lock import worker_status

    console.print_json(json.dumps(worker_status(settings), ensure_ascii=False, default=str))


@app.command("worker")
def worker(
    once: bool = typer.Option(False, "--once", help="只跑一轮后退出"),
    execute: bool = typer.Option(False, "--execute", help="真实抓取（默认 dry-run）"),
    interval: int = typer.Option(3600, "--interval-seconds", help="循环间隔秒"),
    config: str | None = typer.Option(None, "--config"),
    limit: int = typer.Option(10, "--limit"),
) -> None:
    """本地周期 worker：定期调用 scan-due。用 Windows 任务计划或前台循环启动。"""
    import time

    settings = load_settings(config, project_root=_project_root())
    from app.db.session import (
        prepare_engine,
        session_scope,
    )
    from app.scheduler.jobs import run_due_scans
    from app.services.ops.worker_lock import (
        acquire_worker_lock,
        heartbeat,
        release_worker_lock,
    )

    ok_lock, lock_path, msg = acquire_worker_lock(settings, interval_seconds=interval)
    if not ok_lock:
        console.print(f"[red]worker 已在运行，拒绝重复启动: {msg}[/red]")
        raise typer.Exit(2)

    engine, factory, mig = prepare_engine(settings)
    report_migration(mig)
    rounds = 0
    try:
        console.print(
            f"[green]worker lock {lock_path} pid={os.getpid()} db={settings.storage.sqlite_path}[/green]"
        )
        while True:
            rounds += 1
            with session_scope(factory) as session:
                runs = run_due_scans(
                    session,
                    settings,
                    dry_run=not execute,
                    limit=limit,
                    include_raffle_pipeline=True,
                )
            # N-FARE-WORKER：周期内同步抓机票情报（原仅扫行程订阅，fare 来源永不自动刷新）
            fare_runs: list = []
            if execute:
                try:
                    import asyncio as _asyncio

                    from app.services.discovery.service import run_discovery

                    with session_scope(factory) as session:
                        fare_runs = _asyncio.run(
                            run_discovery(
                                session,
                                settings,
                                module="fare",
                                dry_run=False,
                                limit=max(8, limit),
                                persist_signals=True,
                                after_fetch=True,
                                enforce_cooldown=True,
                            )
                        )
                except Exception as exc:
                    console.print(f"[yellow]fare discover error: {exc}[/yellow]")
            heartbeat(
                lock_path,
                interval_seconds=interval,
                rounds=rounds,
                last_scans=len(runs),
                last_fare=len(fare_runs),
                last_run_at=datetime.now(UTC).isoformat(timespec="seconds"),
            )
            fare_ok = sum(1 for r in fare_runs if str(r.get("status", "")).startswith("ok"))
            console.print(
                f"[worker #{rounds}] trip_scans={len(runs)} fare={len(fare_runs)} "
                f"fare_ok={fare_ok} execute={execute}"
            )
            if once:
                break
            time.sleep(max(30, interval))
    except KeyboardInterrupt:
        console.print("[yellow]worker interrupted[/yellow]")
    finally:
        release_worker_lock(lock_path, pid=os.getpid())
        engine.dispose()


@app.command("demo-browser-e2e")
def demo_browser_e2e(
    config: str | None = typer.Option(None, "--config"),
    submit: bool = typer.Option(
        False, "--submit", help="对本地模拟站提交（需安装 Playwright 浏览器）"
    ),
) -> None:
    """本地模拟站浏览器 E2E：prepare→预填→可选提交→回执/unknown→通知。"""
    settings = load_settings(config, project_root=_project_root())
    from sqlalchemy import select

    from app.core.ids import new_id
    from app.db.session import (
        prepare_engine,
        session_scope,
    )
    from app.models import Campaign, CampaignRound, Organizer, Profile
    from app.services.entry.browser_pipeline import execute_browser_entry

    mock = Path(_project_root()) / "fixtures" / "mock_campaign_site" / "index.html"
    if not mock.is_file():
        console.print("[red]缺少 fixtures/mock_campaign_site/index.html[/red]")
        raise typer.Exit(1)

    engine, factory, mig = prepare_engine(settings)
    report_migration(mig)
    with session_scope(factory) as session:
        profile = session.scalar(select(Profile).limit(1))
        if profile is None:
            profile = Profile(
                id=new_id(),
                display_name="演示用户",
                country_of_residence="CN",
                preferred_departure_airports='["CKG"]',
            )
            session.add(profile)
            session.flush()
        org = session.scalar(select(Organizer).limit(1))
        if org is None:
            org = Organizer(id=new_id(), name="模拟主办方", official_domain="example.org")
            session.add(org)
            session.flush()
        camp = session.scalar(select(Campaign).limit(1))
        if camp is None:
            camp = Campaign(
                id=new_id(),
                organizer_id=org.id,
                program_key="demo-e2e",
                name="模拟活动",
            )
            session.add(camp)
            session.flush()
        rnd = session.scalar(
            select(CampaignRound).where(CampaignRound.title.like("模拟%")).limit(1)
        )
        if rnd is None:
            rnd = CampaignRound(
                id=new_id(),
                campaign_id=camp.id,
                edition_key="demo",
                title="模拟抽奖报名（E2E）",
                organizer_name="模拟主办方",
                official_url="https://example.org/demo",
                verify_status="verified",
                automation_policy="PREFILL_AND_REVIEW",
                demo_only=True,
            )
            session.add(rnd)
            session.flush()
        result = execute_browser_entry(
            session,
            settings,
            rnd,
            profile,
            file_url=mock.resolve().as_uri(),
            submit=submit,
            explicit_submit_consent=submit,
        )
        payload = {
            "attempt_id": result.attempt_id,
            "status": result.status,
            "receipt_code": result.receipt_code,
            "browser_ok": result.browser_ok,
            "message": result.message,
            "requires_human": result.requires_human,
        }
        # 在 with 内 commit，避免 typer.Exit 触发回滚
        session.commit()
        console.print_json(json.dumps(payload, ensure_ascii=False))
    engine.dispose()
    if payload["status"] == "confirmed" and payload["browser_ok"]:
        raise typer.Exit(0)
    console.print("[yellow]演示未达成 confirmed（unknown/failed/未提交）[/yellow]")
    raise typer.Exit(2)


@app.command("reconcile-stuck")
def reconcile_stuck(
    config: str | None = typer.Option(None, "--config"),
) -> None:
    """将卡在 submitting 的报名尝试全部转为 unknown。"""
    settings = load_settings(config, project_root=_project_root())
    from app.db.session import (
        prepare_engine,
        session_scope,
    )
    from app.services.entry.detail import reconcile_all_stuck

    engine, factory, mig = prepare_engine(settings)
    report_migration(mig)
    with session_scope(factory) as session:
        n = reconcile_all_stuck(session)
        session.commit()
        console.print(f"[green]已恢复 {n} 条卡住的 submitting → unknown[/green]")
    engine.dispose()


@app.command("raffle-provenance")
def raffle_provenance(
    config: str | None = typer.Option(None, "--config"),
    limit: int = typer.Option(5, "--limit"),
) -> None:
    """对候选抽奖尝试只读抓取 official_url 并保存证据快照。"""
    import asyncio

    settings = load_settings(config, project_root=_project_root())
    from app.db.session import (
        prepare_engine,
        session_scope,
    )
    from app.services.raffle.provenance import attempt_official_evidence_batch

    engine, factory, mig = prepare_engine(settings)
    report_migration(mig)
    with session_scope(factory) as session:
        results = asyncio.run(
            attempt_official_evidence_batch(session, settings, limit=limit)
        )
        session.commit()
        table = Table(title="抽奖官方溯源尝试")
        table.add_column("标题")
        table.add_column("结果")
        for r in results:
            status = "evidence" if r.get("ok") else str(r.get("reason"))
            table.add_row(r.get("title", ""), status)
        console.print(table)
    engine.dispose()


@app.command("raffle-rules-check")
def raffle_rules_check(
    url: str = typer.Argument(..., help="已知官方活动页 URL（只读核验，不自动报名）"),
    config: str | None = typer.Option(None, "--config"),
) -> None:
    """第二步：已知官方目标回归 — 只读抓取并解析官方规则；不写入候选冒充自主发现。"""
    import asyncio
    import json as _json

    settings = load_settings(config, project_root=_project_root())
    from app.adapters.html_fetcher import HttpxFetchAdapter
    from app.core.url_safety import assert_public_http_url
    from app.services.raffle.official_rules import (
        eligibility_unknown_profile,
        parse_official_rules_html,
    )

    assert_public_http_url(url)
    adapter = HttpxFetchAdapter(settings)

    async def _run():
        return await adapter.fetch(url)

    result = asyncio.run(_run())
    if not result.ok:
        console.print(f"[red]页面读取失败: {result.error_code} {result.message}[/red]")
        raise typer.Exit(1)
    parse = parse_official_rules_html(
        result.text or "",
        page_url=result.final_url or url,
        expected_official_hosts=("visitkorea.or.kr", "knto.or.kr"),
    )
    payload = {
        "page_fetched": True,
        "final_url": result.final_url,
        "rules": parse.to_dict(),
        "eligibility_without_profile": eligibility_unknown_profile(parse),
        "note": "页面读取成功 ≠ 活动仍有效 ≠ 用户 eligible；不自动提交报名",
    }
    console.print_json(_json.dumps(payload, ensure_ascii=False, default=str))


@app.command("raffle-multi-round-check")
def raffle_multi_round_check(
    url: str = typer.Argument(...),
    config: str | None = typer.Option(None, "--config"),
    nationality: str | None = typer.Option(None, help="合成测试国籍，如 CN"),
    residence: str | None = typer.Option(None, help="合成测试居住国，如 CN"),
    age: int | None = typer.Option(None),
    poster_facts_json: str | None = typer.Option(
        None,
        "--poster-facts-json",
        help="人工复核渠道（非自主提取）；自主路径请用 raffle-auto-extract",
    ),
    auto: bool = typer.Option(True, "--auto/--no-auto", help="自动 OCR/HTML 证据提取"),
) -> None:
    """同页多活动/多期拆分核验；禁止跨期拼接机票奖品与截止日期。"""
    import asyncio
    import json as _json
    from datetime import UTC, datetime

    settings = load_settings(config, project_root=_project_root())
    from app.adapters.html_fetcher import HttpxFetchAdapter
    from app.core.url_safety import assert_public_http_url
    from app.services.raffle.multi_round import (
        eligibility_with_synthetic_profile,
        parse_multi_round_event_html,
    )

    assert_public_http_url(url)
    adapter = HttpxFetchAdapter(settings)

    async def _run():
        return await adapter.fetch(url)

    result = asyncio.run(_run())
    if not result.ok:
        console.print(f"[red]读取失败 {result.error_code}: {result.message}[/red]")
        raise typer.Exit(1)
    now = datetime.now(UTC).replace(tzinfo=None)
    poster = _json.loads(poster_facts_json) if poster_facts_json else None
    auto_payload = None
    if auto and not poster:
        from app.services.raffle.evidence_extract import extract_official_evidence

        async def _fetch_bytes(u: str) -> bytes:
            from app.core.safe_http import safe_get

            r = await safe_get(
                u,
                headers={"User-Agent": "FlightHunter-Bot/1.0 (evidence extract)"},
                timeout=40,
                check_robots=True,
                max_bytes=12_000_000,
            )
            if not r.ok or r.content is None:
                raise RuntimeError(r.error or "fetch_bytes_failed")
            return r.content

        ext = asyncio.run(
            extract_official_evidence(
                result.text or "",
                page_url=result.final_url or url,
                fetch_bytes=_fetch_bytes,
                now=now,
            )
        )
        auto_payload = ext.to_dict()
        auto_extract = {
            "title": ext.prize_summary or "auto extracted",
            "opens": ext.opens_raw,
            "closes": ext.closes_raw,
            "opens_iso": ext.opens_iso,
            "closes_iso": ext.closes_iso,
            "prize_summary": ext.prize_summary,
            "prize_is_flight": ext.prize_is_flight,
            "winners_count": ext.winners_count,
            "tickets_per_winner": ext.tickets_per_winner,
            "free_entry": ext.free_entry,
            "residency_text": ext.residency_text,
            "entry_channel": ext.entry_channel,
            "open_status": ext.open_status,
            "human_review_required": ext.human_review_required,
            "confidence": "high" if ext.opens_iso and ext.closes_iso else "medium",
            "evidence_quote": (ext.ocr_text_sample or "")[:500],
            "requires_login": "Join Now" in (ext.ocr_text_sample or "") or False,
        }
    else:
        auto_extract = None
    parsed = parse_multi_round_event_html(
        result.text or "",
        page_url=result.final_url or url,
        now=now,
        poster_facts=poster,
        auto_extract=auto_extract,
    )
    rounds_out = []
    for r in parsed.rounds:
        el = eligibility_with_synthetic_profile(
            r, nationality=nationality, residence=residence, age=age
        )
        rounds_out.append(
            {
                **r.to_dict(),
                "eligibility": el,
                "can_enter_now": bool(
                    r.open_status == "open" and el.get("state") == "eligible"
                ),
                "can_enter_now_note": (
                    "活动已结束，不计入真实可参加"
                    if r.open_status == "closed"
                    else "开放状态待核实（日期未知/需登录等），不按已结束处理"
                    if r.open_status == "pending_verification"
                    else "活动仍开放；用户资格 unknown，不自动报名"
                    if r.open_status == "open" and el.get("state") != "eligible"
                    else "规则允许且仍开放；仍须人工确认官方页后自愿报名"
                    if r.open_status == "open"
                    else "开放状态未知"
                ),
            }
        )
    payload = {
        "page_fetched": True,
        "now": now.isoformat(),
        **parsed.to_dict(),
        "rounds": rounds_out,
        "automated_evidence": auto_payload,
        "manual_poster_facts_used": bool(poster),
        "note": "有效≠eligible；eligible≠已报名；不自动提交；poster-facts-json 仅为人工复核",
    }
    # open_flight_rounds 依赖 rounds 字段在 to_dict 后仍可用
    payload["open_flight_rounds"] = [
        r["round_label"]
        for r in rounds_out
        if r.get("prize_is_flight") and r.get("open_status") == "open"
    ]
    payload["pending_verification_flight_rounds"] = [
        r["round_label"]
        for r in rounds_out
        if r.get("prize_is_flight") and r.get("open_status") == "pending_verification"
    ]
    payload["ended_flight_rounds"] = [
        r["round_label"]
        for r in rounds_out
        if r.get("prize_is_flight") and r.get("open_status") == "closed"
    ]
    console.print_json(_json.dumps(payload, ensure_ascii=False, default=str))


@app.command("jp-benefits-scan")
def jp_benefits_scan(
    config: str | None = typer.Option(None, "--config"),
) -> None:
    """日本演示行程：抓取公开活动页 → 优惠候选 → 匹配 → 中文指南。"""
    import asyncio

    settings = load_settings(config, project_root=_project_root())
    from app.db.session import (
        prepare_engine,
        session_scope,
    )
    from app.services.trips.jp_benefits import ensure_demo_japan_trip, scan_jp_public_page

    engine, factory, mig = prepare_engine(settings)
    report_migration(mig)
    with session_scope(factory) as session:
        trip = ensure_demo_japan_trip(session, settings)
        session.flush()
        result = asyncio.run(scan_jp_public_page(session, settings, trip))
        session.commit()
        console.print_json(json.dumps(result, ensure_ascii=False, default=str))
    engine.dispose()


@app.command("list-deals")
def list_deals(
    risk: str | None = typer.Option(None, "--risk"),
    config: str | None = typer.Option(None, "--config"),
) -> None:
    """列出机票机会。"""
    settings = load_settings(config, project_root=_project_root())
    from sqlalchemy import select

    from app.db.session import (
        prepare_engine,
        session_scope,
    )
    from app.models import FareDeal

    engine, factory, mig = prepare_engine(settings)
    report_migration(mig)
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
