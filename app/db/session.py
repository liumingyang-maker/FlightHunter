"""数据库会话与引擎。"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine, event, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings, sqlite_path
from app.models import Base, Source


def _db_url(path: Path) -> str:
    return f"sqlite+pysqlite:///{path.as_posix()}"


def create_db_engine(settings: Settings) -> Engine:
    path = sqlite_path(settings)
    engine = create_engine(
        _db_url(path),
        echo=False,
        future=True,
        connect_args={"check_same_thread": False, "timeout": 30},
    )

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, connection_record):  # type: ignore[no-untyped-def]
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.close()

    return engine


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False, future=True)


def init_db(engine: Engine) -> None:
    """创建全部表（开发/测试用；生产用 Alembic）。"""
    Base.metadata.create_all(engine)


@contextmanager
def session_scope(factory: sessionmaker[Session]) -> Iterator[Session]:
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_session(factory: sessionmaker[Session]) -> Session:
    return factory()


def ensure_default_sources(session: Session, settings: Settings) -> list[Source]:
    """确保默认社区来源存在（access_policy 标明限制）。"""
    created: list[Source] = []
    defaults = [
        {
            "name": "什么值得买 · 国际机票",
            "base_url": "https://www.smzdm.com/fenlei/guowaijipiao/",
            "kind": "community",
            "language": "zh-Hans",
            "access_policy": "public_fetch",
            "allowed_fetch_mode": "httpx",
            "module": "fare",
            "notes": "公开列表；不可保证实时更新；遵守站点条款与限速",
        },
        {
            "name": "什么值得买 · 每日机票推荐",
            "base_url": "https://m.smzdm.com/theme/a788l7k/",
            "kind": "community",
            "language": "zh-Hans",
            "access_policy": "public_fetch",
            "allowed_fetch_mode": "httpx",
            "module": "fare",
            "notes": "主题订阅种子；不可直接把「XX元起」当可买价",
        },
        {
            "name": "北美票帝",
            "base_url": "https://piao.tips/",
            "kind": "community",
            "language": "zh-Hans",
            "access_policy": "public_fetch",
            "allowed_fetch_mode": "httpx",
            "module": "fare",
            "notes": "错价/促销情报案例；主要用于风险验证",
        },
    ]
    for item in defaults:
        existing = session.scalar(select(Source).where(Source.base_url == item["base_url"]))
        if existing is None:
            from app.core.ids import new_id

            src = Source(
                id=new_id(),
                name=item["name"],
                base_url=item["base_url"],
                kind=item["kind"],
                language=item["language"],
                access_policy=item["access_policy"],
                allowed_fetch_mode=item["allowed_fetch_mode"],
                module=item["module"],
                notes=item["notes"],
                status="active",
            )
            session.add(src)
            created.append(src)
    session.flush()
    return created
