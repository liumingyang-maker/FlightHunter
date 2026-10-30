"""本地会话与 API Token 鉴权。

- 带时间戳签名 Cookie（URLSafeTimedSerializer + max_age）
- 服务端会话表（data/sessions.json）：登出即撤销
- 支持 Bearer / X-Api-Token
"""

from __future__ import annotations

import hmac
import json
import secrets
import time
from pathlib import Path

from itsdangerous import BadSignature, URLSafeTimedSerializer
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, RedirectResponse

from app.config import Settings
from app.core.url_safety import is_safe_local_next

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


def _state_dir(settings: Settings) -> Path:
    """鉴权/会话状态目录：隔离库旁路，避免测试复用正式 auth.json。"""
    auth_dir = getattr(settings.auth, "state_dir", None)
    if auth_dir:
        return Path(auth_dir)
    db = Path(settings.storage.sqlite_path)
    if not db.is_absolute():
        db = Path(settings.project_root) / db
    db = db.resolve()
    root = Path(settings.project_root).resolve()
    # SQLite 不在仓库 data/ 下 → 视为隔离环境，状态写在 DB 同目录
    if db.parent != root / "data" and root not in db.parents:
        return db.parent
    return root / "data"


def _auth_file_path(settings: Settings) -> Path:
    return _state_dir(settings) / "auth.json"


def _sessions_file_path(settings: Settings) -> Path:
    return _state_dir(settings) / "sessions.json"


def _load_auth_file(settings: Settings) -> dict:
    path = _auth_file_path(settings)
    if path.is_file():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


def ensure_runtime_secrets(settings: Settings) -> tuple[str, str]:
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


def _serializer(settings: Settings) -> URLSafeTimedSerializer:
    _, secret = ensure_runtime_secrets(settings)
    return URLSafeTimedSerializer(secret, salt="flighthunter-session-v2")


def _load_sessions(settings: Settings) -> dict:
    path = _sessions_file_path(settings)
    if path.is_file():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
    return {}


def _save_sessions(settings: Settings, data: dict) -> None:
    path = _sessions_file_path(settings)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _prune_sessions(settings: Settings, data: dict) -> dict:
    now = time.time()
    max_age = settings.auth.session_max_age_seconds
    return {k: v for k, v in data.items() if float(v.get("exp", 0)) > now and max_age > 0}


def create_session_cookie_value(settings: Settings) -> str:
    """创建带 sid 的时间戳 Cookie，并在服务端登记。"""
    sid = secrets.token_urlsafe(24)
    now = time.time()
    data = _load_sessions(settings)
    data = _prune_sessions(settings, data)
    data[sid] = {"exp": now + settings.auth.session_max_age_seconds, "iat": now}
    _save_sessions(settings, data)
    return _serializer(settings).dumps({"role": "local_user", "sid": sid})


def revoke_session_cookie(value: str | None, settings: Settings) -> bool:
    sid = _sid_from_cookie(value, settings)
    if not sid:
        return False
    data = _load_sessions(settings)
    if sid in data:
        del data[sid]
        _save_sessions(settings, data)
        return True
    return False


def _sid_from_cookie(value: str | None, settings: Settings) -> str | None:
    if not value:
        return None
    try:
        data = _serializer(settings).loads(value, max_age=settings.auth.session_max_age_seconds)
    except BadSignature:
        return None
    if data.get("role") != "local_user":
        return None
    sid = data.get("sid")
    return str(sid) if sid else None


def verify_session_cookie(value: str | None, settings: Settings) -> bool:
    sid = _sid_from_cookie(value, settings)
    if not sid:
        return False
    data = _prune_sessions(settings, _load_sessions(settings))
    return sid in data


def is_authenticated(request: Request, settings: Settings) -> bool:
    if not settings.auth.enabled:
        return True
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer ") and token_matches(auth[7:].strip(), settings):
        return True
    if token_matches(request.headers.get("x-api-token"), settings):
        return True
    cookie_name = settings.auth.session_cookie_name
    return verify_session_cookie(request.cookies.get(cookie_name), settings)


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
        nxt = is_safe_local_next(path)
        return RedirectResponse(url=f"/login?next={nxt}", status_code=303)
