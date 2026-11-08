"""API tests. These use the offline demo series and never touch the network."""

from __future__ import annotations

import pytest

from fastapi.testclient import TestClient

from tankwise.api import app

client = TestClient(app)


PLAN_BODY = {
    "latitude": -33.7667,
    "longitude": 151.1833,
    "roof_area_m2": 200,
    "occupants": 4,
    "garden_area_m2": 100,
    "tank_litres": 5000,
    "target_coverage": 0.9,
    "offline_demo": True,
    "years": 10,
}


def test_health():
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_index_serves_the_page():
    response = client.get("/")
    assert response.status_code == 200
    assert "tankwise" in response.text
    assert "Plan this tank" in response.text


def test_plan_returns_all_sections():
    response = client.post("/api/plan", json=PLAN_BODY)
    assert response.status_code == 200
    payload = response.json()

    for key in (
        "location",
        "roof",
        "rainfall_summary",
        "demand_summary",
        "result",
        "economics",
        "sweep",
        "recommendation",
        "monthly",
        "assumptions",
    ):
        assert key in payload

    assert 0.0 <= payload["result"]["coverage"] <= 1.0
    assert payload["result"]["dry_days_per_year"] >= 0
    assert len(payload["sweep"]) == 19
    assert payload["sweep"][0]["capacity_litres"] == 1000
    assert payload["sweep"][-1]["capacity_litres"] == 10000


def test_plan_rejects_bad_latitude():
    bad = dict(PLAN_BODY, latitude=99)
    response = client.post("/api/plan", json=bad)
    assert response.status_code == 422


def test_plan_kilolitre_balance_is_consistent():
    payload = client.post("/api/plan", json=PLAN_BODY).json()
    result = payload["result"]
    total = result["harvested_kl_per_year"] + result["mains_topup_kl_per_year"]
    assert total == pytest.approx(result["demand_kl_per_year"], abs=0.05)


def test_roof_falls_back_when_lookup_fails():
    payload = client.post("/api/plan", json=PLAN_BODY).json()
    assert payload["roof"]["area_m2"] == 200.0
    assert payload["roof"]["source"] == "user input"


def test_monthly_series_is_capped():
    payload = client.post("/api/plan", json=PLAN_BODY).json()
    assert 1 <= len(payload["monthly"]) <= 36


def test_static_assets_are_mounted():
    css = client.get("/static/styles.css")
    assert css.status_code == 200
    assert "--teal" in css.text