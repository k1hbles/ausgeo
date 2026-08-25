"""API tests against the real load. Skipped unless G-NAF is present."""

from __future__ import annotations

import pytest

psycopg = pytest.importorskip("psycopg")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from geocoder.api import app  # noqa: E402
from geocoder.db import DATABASE_URL  # noqa: E402

MIN_REAL_ROWS = 1_000_000


@pytest.fixture(scope="module")
def client():
    try:
        c = psycopg.connect(DATABASE_URL, connect_timeout=3, autocommit=True)
    except Exception as exc:  # noqa: BLE001  # pragma: no cover
        pytest.skip(f"database unavailable: {exc}")
    with c:
        n = c.execute("select count(*) from address").fetchone()[0]
        if n < MIN_REAL_ROWS:
            pytest.skip(f"only {n:,} rows; real G-NAF not loaded")
        # Tests share the anonymous quota; clear it so repeat runs don't 429.
        c.execute("DELETE FROM anon_usage WHERE day = current_date")
        c.execute("DELETE FROM key_issuance WHERE day = current_date")
    with TestClient(app) as tc:
        yield tc


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
    assert r.json()["addresses"] > MIN_REAL_ROWS


def test_geocode_freetext(client):
    r = client.get("/v1/geocode", params={"q": "79 St Marys St Newtown NSW 2042", "limit": 2})
    assert r.status_code == 200
    d = r.json()
    assert d["parsed"]["number"] == "79"
    assert d["parsed"]["postcode"] == "2042"
    top = d["results"][0]
    assert top["components"]["locality"] == "NEWTOWN"
    assert top["components"]["unit"] is None
    assert -34 < top["location"]["lat"] < -33
    assert 150 < top["location"]["lon"] < 152
    assert 0 < top["score"] <= 1
    assert top["match"] == "postcode+number"


def test_geocode_structured(client):
    r = client.get("/v1/geocode", params={
        "number": "101", "street": "Collins St", "locality": "Melbourne",
        "state": "VIC", "postcode": "3000", "limit": 1,
    })
    assert r.status_code == 200
    top = r.json()["results"][0]
    assert top["components"]["locality"] == "MELBOURNE"
    assert top["components"]["number"] == "101"


def test_no_match_returns_empty_not_error(client):
    r = client.get("/v1/geocode", params={"q": "999999 Fakename Rd Nowhere NSW 2042"})
    assert r.status_code == 200
    assert r.json()["results"] == []


def test_missing_params_422(client):
    r = client.get("/v1/geocode")
    assert r.status_code == 422


def test_invalid_key_401(client):
    r = client.get("/v1/geocode", params={"q": "1 Macquarie St Sydney 2000"},
                   headers={"X-API-Key": "ausgeo_definitely_not_real"})
    assert r.status_code == 401


def test_ratelimit_headers_present(client):
    r = client.get("/v1/geocode", params={"q": "1 Macquarie St Sydney 2000"})
    assert r.headers["X-RateLimit-Limit"] == "100"          # anonymous tier
    assert int(r.headers["X-RateLimit-Remaining"]) < 100


def test_issue_key_and_use_it(client):
    r = client.post("/v1/keys", json={"label": "pytest"})
    assert r.status_code == 201
    key = r.json()["key"]
    assert key.startswith("ausgeo_")
    assert r.json()["daily_limit"] == 2500

    r2 = client.get("/v1/geocode", params={"q": "1 Macquarie Street Sydney NSW 2000", "limit": 1},
                    headers={"X-API-Key": key})
    assert r2.status_code == 200
    assert r2.headers["X-RateLimit-Limit"] == "2500"
    assert r2.json()["results"][0]["components"]["number"] == "1"


def test_bad_email_rejected(client):
    r = client.post("/v1/keys", json={"email": "not-an-email"})
    assert r.status_code == 422


def test_query_length_capped(client):
    r = client.get("/v1/geocode", params={"q": "x" * 500})
    assert r.status_code == 422
