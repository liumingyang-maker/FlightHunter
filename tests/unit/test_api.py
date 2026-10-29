"""API 集成测试（TestClient）。"""

from __future__ import annotations


def test_health(app_client):
    r = app_client.get("/api/v1/health")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["data"]["status"] == "up"


def test_home_page(app_client):
    r = app_client.get("/")
    assert r.status_code == 200
    assert "FlightHunter" in r.text


def test_create_trip_and_list(app_client):
    payload = {
        "label": "API日本行程",
        "destination_country_code": "JP",
        "local_start_date": "2027-05-10",
        "local_end_date": "2027-05-30",
        "timezone": "Asia/Tokyo",
        "demo_only": False,
        "segments": [],
    }
    r = app_client.post("/api/v1/trips", json=payload)
    assert r.status_code == 200, r.text
    trip_id = r.json()["data"]["id"]
    assert r.json()["data"]["scan_registered"] is True

    r2 = app_client.get("/api/v1/trips")
    assert r2.status_code == 200
    ids = [t["id"] for t in r2.json()["data"]]
    assert trip_id in ids

    r3 = app_client.get(f"/api/v1/trips/{trip_id}/matches")
    assert r3.status_code == 200


def test_trip_invalid_dates_400(app_client):
    payload = {
        "label": "坏",
        "destination_country_code": "JP",
        "local_start_date": "2027-05-30",
        "local_end_date": "2027-05-10",
        "timezone": "Asia/Tokyo",
    }
    r = app_client.post("/api/v1/trips", json=payload)
    assert r.status_code in (400, 422)


def test_import_signal_and_list(app_client):
    payload = {
        "title": "API导入爆料",
        "raw_claim_text": "测试",
        "origin_airport": "CKG",
        "destination_airport": "NRT",
        "reported_total": 999,
        "currency": "CNY",
        "party_size": 2,
        "deal_types": ["flash_sale"],
        "user_supplied": True,
    }
    r = app_client.post("/api/v1/fare-deals/import-signal", json=payload)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["status"] == "price_unconfirmed"

    r2 = app_client.get("/api/v1/fare-deals")
    assert r2.status_code == 200
    assert any(d["origin"] == "CKG" for d in r2.json()["data"])


def test_fare_watch_scan(app_client):
    r = app_client.post(
        "/api/v1/fare-watches",
        json={
            "name": "API watch",
            "origin_airports": ["CKG"],
            "destination_scope": "any",
            "adults": 2,
            "enabled": True,
        },
    )
    assert r.status_code == 200, r.text
    wid = r.json()["data"]["id"]
    r2 = app_client.post(f"/api/v1/fare-watches/{wid}/scan")
    assert r2.status_code == 200


def test_health_and_docs(app_client):
    r = app_client.get("/api/docs")
    assert r.status_code == 200
