"""FastAPI 应用工厂。"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session, sessionmaker

from app import __version__
from app.config import Settings, load_settings
from app.core.errors import FlightHunterError
from app.core.ids import new_id
from app.db.session import create_db_engine, init_db, make_session_factory
from app.web.auth import AuthMiddleware, ensure_runtime_secrets

TEMPLATES_DIR = Path(__file__).parent / "templates"
STATIC_DIR = Path(__file__).parent / "static"


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or load_settings()
    ensure_runtime_secrets(settings)
    engine = create_db_engine(settings)
    init_db(engine)
    factory: sessionmaker[Session] = make_session_factory(engine)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.settings = settings
        app.state.engine = engine
        app.state.session_factory = factory
        app.state.templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
        yield
        engine.dispose()

    app = FastAPI(
        title="FlightHunter",
        version=__version__,
        lifespan=lifespan,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
    )
    app.add_middleware(AuthMiddleware, settings=settings)
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    @app.exception_handler(FlightHunterError)
    async def _fh_error(request: Request, exc: FlightHunterError):
        return JSONResponse(
            status_code=400,
            content={
                "ok": False,
                "error": exc.to_dict(),
                "request_id": new_id(),
            },
        )

    from app.web.routes.api import router as api_router
    from app.web.routes.pages import router as pages_router

    app.include_router(api_router, prefix="/api/v1")
    app.include_router(pages_router)

    return app
