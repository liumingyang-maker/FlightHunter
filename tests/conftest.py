"""pytest 公共夹具：临时 SQLite + 认证客户端。"""

from __future__ import annotations

from pathlib import Path

import pytest
from app.config import (
    AppConfig,
    AuthConfig,
    Settings,
    StorageConfig,
    TripMonitoringConfig,
)
from app.db.session import create_db_engine, init_db, make_session_factory
from sqlalchemy.orm import Session

TEST_TOKEN = "test-flighthunter-token-0001"


@pytest.fixture()
def settings(tmp_path: Path) -> Settings:
    db_path = tmp_path / "test.db"
    s = Settings(
        app=AppConfig(demo_mode=True, web_port=8765),
        auth=AuthConfig(enabled=True, api_token=TEST_TOKEN),
        storage=StorageConfig(sqlite_path=str(db_path)),
        trip_monitoring=TripMonitoringConfig(enabled=True, auto_register_on_trip_save=True),
    )
    s.project_root = str(tmp_path)
    return s


@pytest.fixture()
def engine(settings: Settings):
    eng = create_db_engine(settings)
    init_db(eng)
    yield eng
    eng.dispose()


@pytest.fixture()
def db(engine) -> Session:
    factory = make_session_factory(engine)
    session = factory()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def app_client(settings: Settings, engine):
    from app.web.app import create_app
    from fastapi.testclient import TestClient

    application = create_app(settings)
    with TestClient(application) as client:
        client.headers.update({"Authorization": f"Bearer {TEST_TOKEN}"})
        yield client


@pytest.fixture()
def anon_client(settings: Settings, engine):
    """无认证客户端，用于验证 401。"""
    from app.web.app import create_app
    from fastapi.testclient import TestClient

    application = create_app(settings)
    with TestClient(application) as client:
        yield client
