"""C14-05：CLI 迁移状态提示。只读展示，不自动迁移。"""

from __future__ import annotations


def report_migration(mig: dict | None, *, command: str = "") -> None:
    """输出迁移状态；needs_migration/outdated 时给可操作提示。"""
    if not mig:
        return
    action = mig.get("action")
    state = mig.get("state")
    if action in ("create_all_new_db", "ok", "migrated"):
        return
    try:
        from rich.console import console as _console  # type: ignore
    except Exception:
        _console = None
    msg = f"[migrate:{command}] action={action} state={state} version={mig.get('alembic_version')} head={mig.get('head')}"
    if action == "needs_migration":
        msg += " | 提示: 备份后执行 python -m alembic upgrade head（不会自动改正式库）"
    elif action == "outdated":
        msg += f" | 版本落后，备份后升级到 {mig.get('head')}"
    if _console is not None:
        _console.print(f"[yellow]{msg}[/yellow]")
    else:
        print(msg)
