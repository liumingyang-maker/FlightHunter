"""Web 依赖。"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session


def get_settings(request: Request):
    return request.app.state.settings


def get_session_factory(request: Request):
    return request.app.state.session_factory


def get_db(request: Request):
    factory = request.app.state.session_factory
    session: Session = factory()
    try:
        yield session
    finally:
        session.close()


def get_templates(request: Request):
    return request.app.state.templates


DbDep = Annotated[Session, Depends(get_db)]
SettingsDep = Annotated[object, Depends(get_settings)]
