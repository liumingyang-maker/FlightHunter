"""API 鉴权测试。"""

from __future__ import annotations

from tests.conftest import TEST_TOKEN


def test_anon_profiles_rejected(anon_client):
    r = anon_client.get("/api/v1/profiles")
    assert r.status_code == 401
    body = r.json()
    assert body["ok"] is False
    assert body["error"]["code"] == "UNAUTHORIZED"


def test_anon_create_trip_rejected(anon_client):
    r = anon_client.post(
        "/api/v1/trips",
        json={
            "label": "x",
            "destination_country_code": "JP",
            "local_start_date": "2027-05-10",
            "local_end_date": "2027-05-30",
            "timezone": "Asia/Tokyo",
        },
    )
    assert r.status_code == 401


def test_anon_home_redirects(anon_client):
    r = anon_client.get("/", follow_redirects=False)
    assert r.status_code == 303
    assert "/login" in r.headers.get("location", "")


def test_health_is_public(anon_client):
    r = anon_client.get("/api/v1/health")
    assert r.status_code == 200


def test_login_with_token_sets_cookie_and_allows_access(anon_client):
    r = anon_client.post("/api/v1/auth/login", json={"token": TEST_TOKEN})
    assert r.status_code == 200
    assert r.json()["ok"] is True
    r2 = anon_client.get("/api/v1/profiles")
    assert r2.status_code == 200


def test_login_wrong_token(anon_client):
    r = anon_client.post("/api/v1/auth/login", json={"token": "wrong"})
    assert r.status_code == 401


def test_bearer_token_allows_private_api(app_client):
    r = app_client.get("/api/v1/profiles")
    assert r.status_code == 200
    assert r.json()["ok"] is True


def test_me_requires_auth_when_anonymous(anon_client):
    # /auth/me 在 PUBLIC_EXACT 之外？设计为需认证；登录后可用
    # 实际上 /api/v1/auth/me 不在公开列表 → 401
    r = anon_client.get("/api/v1/auth/me")
    # auth/me 不在 PUBLIC — 401 更安全
    assert r.status_code == 401
