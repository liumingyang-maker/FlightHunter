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
    """创建全部表（开发/测试用）；并尝试放宽旧库 official_url NOT NULL。"""
    Base.metadata.create_all(engine)
    try:
        from sqlalchemy import text

        with engine.connect() as conn:
            # 旧库可能仍为 NOT NULL：SQLite 无法简单 ALTER，跳过并记录
            row = conn.execute(
                text(
                    "SELECT sql FROM sqlite_master WHERE type='table' AND name='campaign_rounds'"
                )
            ).fetchone()
            if row and "official_url" in (row[0] or "") and "NOT NULL" in (row[0] or ""):
                # 提示性：新写入用空串兼容，代码侧 official 可为 None 但需列 nullable
                pass
            conn.commit()
    except Exception:
        pass


def _is_typer_exit(exc: BaseException) -> bool:
    """仅 typer/click Exit：业务已完成，commit；中断/错误一律 rollback。"""
    return type(exc).__name__ == "Exit" or exc.__class__.__qualname__ == "Exit"


@contextmanager
def session_scope(factory: sessionmaker[Session]) -> Iterator[Session]:
    session = factory()
    try:
        yield session
        session.commit()
    except BaseException as exc:
        if _is_typer_exit(exc):
            try:
                session.commit()
            except Exception:
                session.rollback()
        else:
            # KeyboardInterrupt / 真异常：不提交半成品
            session.rollback()
        raise
    finally:
        session.close()


def get_session(factory: sessionmaker[Session]) -> Session:
    return factory()


def ensure_default_sources(session: Session, settings: Settings) -> list[Source]:
    """确保默认来源：机票社区 + 行程福利 + 抽奖公开页种子。"""
    created: list[Source] = []
    defaults = [
        # fare
        {
            "name": "什么值得买 · 国际机票",
            "base_url": "https://www.smzdm.com/fenlei/guowaijipiao/",
            "kind": "community",
            "language": "zh-Hans",
            "country_code": None,
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
            "country_code": None,
            "access_policy": "public_fetch",
            "allowed_fetch_mode": "httpx",
            "module": "fare",
            "notes": "主题订阅种子；不可直接把「XX元起」当可买价",
        },
        {
            "name": "Secret Flying",
            "base_url": "https://www.secretflying.com/",
            "kind": "community",
            "language": "en",
            "country_code": None,
            "access_policy": "public_fetch",
            "allowed_fetch_mode": "httpx",
            "module": "fare",
            "notes": "P1 国际特价机票情报；非实时可买价",
        },
        {
            "name": "Fly4Free",
            "base_url": "https://www.fly4free.com/",
            "kind": "community",
            "language": "en",
            "country_code": None,
            "access_policy": "public_fetch",
            "allowed_fetch_mode": "httpx",
            "module": "fare",
            "notes": "P1 国际优惠情报；社区来源",
        },
        {
            "name": "北美票帝",
            "base_url": "https://piao.tips/",
            "kind": "community",
            "language": "zh-Hans",
            "country_code": None,
            "access_policy": "public_fetch",
            "allowed_fetch_mode": "httpx",
            "module": "fare",
            "notes": "错价/促销情报案例；主要用于风险验证",
        },
        # trip benefits — Japan default pack (public pages less robots-hostile)
        {
            "name": "Time Out Tokyo 优惠活动",
            "base_url": "https://www.timeout.com/tokyo/things-to-do",
            "kind": "community",
            "language": "en",
            "country_code": "JP",
            "access_policy": "public_fetch",
            "allowed_fetch_mode": "httpx",
            "module": "trip",
            "notes": "东京活动/优惠公开列表种子",
        },
        {
            "name": "Japan Guide 东京",
            "base_url": "https://www.japan-guide.com/e/e2164.html",
            "kind": "community",  # 独立旅游指南 ≠ 官方优惠来源
            "language": "en",
            "country_code": "JP",
            "access_policy": "public_fetch",
            "allowed_fetch_mode": "httpx",
            "module": "trip",
            "notes": "公开指南线索；非官方优惠，不可当已领券",
        },
        # raffle — public contest/giveaway style pages (read-only)
        {
            "name": "Sweepstakes Today · Travel",
            "base_url": "https://www.sweepstoday.com/category/travel/",
            "kind": "community",
            "language": "en",
            "country_code": None,
            "access_policy": "public_fetch",
            "allowed_fetch_mode": "httpx",
            "module": "raffle",
            "notes": "旅行类公开抽奖列表；候选线索须官网核实",
        },
        {
            "name": "Sweepstakes Today 列表",
            "base_url": "https://www.sweepstoday.com/",
            "kind": "community",
            "language": "en",
            "country_code": None,
            "access_policy": "public_fetch",
            "allowed_fetch_mode": "httpx",
            "module": "raffle",
            "notes": "公开抽奖聚合页种子；仅候选线索，必须官网核实",
        },
        {
            "name": "Contest Girl 列表",
            "base_url": "https://www.contestgirl.com/",
            "kind": "community",
            "language": "en",
            "country_code": None,
            "access_policy": "public_fetch",
            "allowed_fetch_mode": "httpx",
            "module": "raffle",
            "notes": "公开 sweepstakes 列表；不得视为官方已核实",
        },
        {
            "name": "Contest Girl Daily Sweeps",
            "base_url": "https://www.contestgirl.com/contests/contests.pl?f=d&c=us&b=nb&sort=p&ar=na&s=_",
            "kind": "community",
            "language": "en",
            "country_code": "US",
            "access_policy": "public_fetch",
            "allowed_fetch_mode": "httpx",
            "module": "raffle",
            "notes": "每日抽奖明细列表；候选须官网核实",
        },
        {
            "name": "Time Out Tokyo Free Museums",
            "base_url": "https://www.timeout.com/tokyo/museums/best-free-museums-in-tokyo",
            "kind": "community",
            "language": "en",
            "country_code": "JP",
            "access_policy": "public_fetch",
            "allowed_fetch_mode": "httpx",
            "module": "trip",
            "notes": "免费博物馆集合页；仅免费入场信息，非已领券",
        },
        # 官方旅游局站点（非具体活动 URL）— 自主发现入口
        {
            "name": "VISITKOREA EN 首页",
            "base_url": "https://english.visitkorea.or.kr/",
            "kind": "official_tourism_board",
            "language": "en",
            "country_code": "KR",
            "access_policy": "public_fetch",
            "allowed_fetch_mode": "httpx",
            "module": "raffle",
            "notes": "韩国旅游发展局英文站首页；活动链接自动发现，非注入具体活动URL",
        },
        {
            "name": "VISITKOREA 中文美食栏目",
            "base_url": "https://chinese.visitkorea.or.kr/svc/sp/food",
            "kind": "official_tourism_board",
            "language": "zh-Hans",
            "country_code": "KR",
            "access_policy": "public_fetch",
            "allowed_fetch_mode": "httpx",
            "module": "raffle",
            "notes": "官方美食栏目入口；可发现地方机场机票等活动，非注入详情URL",
        },
        {
            "name": "Japan National Tourism Org",
            "base_url": "https://www.japan.travel/en/",
            "kind": "official_tourism_board",
            "language": "en",
            "country_code": "JP",
            "access_policy": "public_fetch",
            "allowed_fetch_mode": "httpx",
            "module": "raffle",
            "notes": "日本国家旅游局；全球旅行抽奖/活动入口",
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
                language=item.get("language"),
                country_code=item.get("country_code"),
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
