"""R22：session_scope 在 typer.Exit 时必须 commit 不回滚。"""

from __future__ import annotations

import typer
from app.config import Settings
from app.core.ids import new_id
from app.db.session import create_db_engine, init_db, make_session_factory, session_scope
from app.models import TaskRun
from sqlalchemy import select


def test_session_scope_commits_on_typer_exit(tmp_path, settings: Settings):
    settings.storage.sqlite_path = str(tmp_path / "t.db")
    engine = create_db_engine(settings)
    init_db(engine)
    factory = make_session_factory(engine)
    rid = new_id()

    def _work():
        with session_scope(factory) as s:
            s.add(
                TaskRun(
                    id=new_id(),
                    task_type="demo",
                    status="completed",
                    idempotency_key=rid,
                    dry_run=True,
                )
            )
            s.flush()
            raise typer.Exit(0)

    try:
        _work()
    except typer.Exit:
        pass
    with session_scope(factory) as s:
        rows = s.scalars(select(TaskRun)).all()
        assert any(r.idempotency_key == rid and r.status == "completed" for r in rows)
    engine.dispose()
