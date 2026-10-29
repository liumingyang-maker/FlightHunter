"""登录页与认证 API。"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel

from app.core.ids import new_id
from app.core.timeutils import utc_now
from app.web.auth import (
    create_session_cookie_value,
    ensure_runtime_secrets,
    revoke_session_cookie,
    token_matches,
)

router = APIRouter(tags=["auth"])


class LoginIn(BaseModel):
    token: str


@router.post("/auth/login")
def login(payload: LoginIn, request: Request, response: Response):
    settings = request.app.state.settings  # type: ignore[attr-defined]
    ensure_runtime_secrets(settings)
    if not settings.auth.allow_login_with_token:
        raise HTTPException(status_code=403, detail="token login disabled")
    if not token_matches(payload.token, settings):
        raise HTTPException(status_code=401, detail="invalid token")
    value = create_session_cookie_value(settings)
    response.set_cookie(
        key=settings.auth.session_cookie_name,
        value=value,
        httponly=True,
        samesite="strict",
        max_age=settings.auth.session_max_age_seconds,
        path="/",
    )
    return {
        "ok": True,
        "data": {"authenticated": True},
        "request_id": new_id(),
        "server_time_utc": utc_now().isoformat(),
    }


@router.post("/auth/logout")
def logout(request: Request, response: Response):
    settings = request.app.state.settings  # type: ignore[attr-defined]
    cookie_name = settings.auth.session_cookie_name
    revoke_session_cookie(request.cookies.get(cookie_name), settings)
    response.delete_cookie(key=cookie_name, path="/")
    return {
        "ok": True,
        "data": {"authenticated": False},
        "request_id": new_id(),
        "server_time_utc": utc_now().isoformat(),
    }


@router.get("/auth/me")
def me(request: Request):
    return {
        "ok": True,
        "data": {"authenticated": True, "mode": "local_single_user"},
        "request_id": new_id(),
        "server_time_utc": utc_now().isoformat(),
    }
