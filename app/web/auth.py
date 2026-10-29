"""本地会话与 API Token 鉴权。

- 所有私人数据 API/页面默认要求认证（health/login/static/docs 除外）。
- 支持 Authorization: Bearer <token>、X-Api-Token，或登录后 HttpOnly Cookie。
- Token 存本地 data/auth.json（已 gitignore），不进入 Git。
"""

from __future__ import annotations

import hmac
import json
import secrets
from pathlib import Path
from urllib.parse import quote

from itsdangerous import BadSignature, URLSafeSerializer
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, RedirectResponse

from app.config import Settings

PUBLIC_EXACT = frozenset(
    {
        "/api/v1/health",
        "/api/v1/auth/login",
        "/api/docs",
        "/api/openapi.json",
        "/favicon.ico",
        "/login",
    }
)
PUBLIC_PREFIXES = ("/static",)


def _auth_file_path(settings: Settings) -> Path:
    return Path(settings.project_root) / "data" / "auth.json"


def _load_auth_file(settings: Settings) -> dict:
    path = _auth_file_path(settings)
    if path.is_file():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


def ensure_runtime_secrets(settings: Settings) -> tuple[str, str]:
    """返回 (api_token, session_secret)，必要时生成并落盘。"""
    cached_token = settings.auth.api_token
    cached_secret = getattr(settings.auth, "_session_secret", None)
    if cached_token and cached_secret:
        return cached_token, str(cached_secret)

    data = _load_auth_file(settings)
    token = cached_token or data.get("api_token")
    secret = cached_secret or data.get("session_secret")
    changed = False
    if not token:
        token = secrets.token_urlsafe(32)
        changed = True
    if not secret:
        secret = secrets.token_urlsafe(32)
        changed = True
    if changed or not _auth_file_path(settings).is_file():
        path = _auth_file_path(settings)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {"api_token": token, "session_secret": secret, "note": "local only"},
                indent=2,
            ),
            encoding="utf-8",
        )
    settings.auth.api_token = token
    object.__setattr__(settings.auth, "_session_secret", secret)
    return token, secret


def token_matches(provided: str | None, settings: Settings) -> bool:
    expected = settings.auth.api_token
    if not provided or not expected:
        return False
    return hmac.compare_digest(provided.encode(), expected.encode())


def _serializer(settings: Settings) -> URLSafeSerializer:
    _, secret = ensure_runtime_secrets(settings)
    return URLSafeSerializer(secret, salt="flighthunter-session")


def create_session_cookie_value(settings: Settings) -> str:
    return _serializer(settings).dumps({"role": "local_user"})


def verify_session_cookie(value: str | None, settings: Settings) -> bool:
    if not value:
        return False
    try:
        data = _serializer(settings).loads(value)
        return data.get("role") == "local_user"
    except BadSignature:
        return False


def is_authenticated(request: Request, settings: Settings) -> bool:
    if not settings.auth.enabled:
        return True
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer ") and token_matches(auth[7:].strip(), settings):
        return True
    if token_matches(request.headers.get("x-api-token"), settings):
        return True
    cookie_name = settings.auth.session_cookie_name
    return bool(verify_session_cookie(request.cookies.get(cookie_name), settings))


def is_public_path(path: str) -> bool:
    if path in PUBLIC_EXACT:
        return True
    return any(path.startswith(p) for p in PUBLIC_PREFIXES)


class AuthMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, settings: Settings):  # type: ignore[no-untyped-def]
        super().__init__(app)
        self.settings = settings

    async def dispatch(self, request: Request, call_next):  # type: ignore[no-untyped-def]
        path = request.url.path
        if is_public_path(path) or not self.settings.auth.enabled:
            return await call_next(request)
        if is_authenticated(request, self.settings):
            return await call_next(request)
        if path.startswith("/api/"):
            return JSONResponse(
                status_code=401,
                content={
                    "ok": False,
                    "error": {"code": "UNAUTHORIZED", "message": "需要登录或 Bearer Token"},
                    "request_id": "unauthorized",
                },
            )
        nxt = quote(path, safe="/")
        return RedirectResponse(url=f"/login?next={nxt}", status_code=303)
