"""Tests for the FastAPI backend and dashboard (Tasks 9, 10, 11, 13)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from aqm.config import AppConfig, DeviceConfig
from aqm.parameters import ALL_KEYS
from aqm.web import create_app


class FakeQueryService:
    def __init__(self):
        self._current = {
            "ts": datetime(2026, 1, 1, 12, 0, tzinfo=UTC),
            "values": {"pm25": 12.0, "co2": 650.0, "aqi": 51.0},
        }
        self.calls = []

    async def current(self):
        return self._current

    async def history(self, param, bucket, start, end):
        self.calls.append((param, bucket, start, end))
        return [
            {
                "bucket_start": datetime(2026, 1, 1, 12, 0, tzinfo=UTC),
                "count": 3,
                "avg": 12.0,
                "stddev": 2.0,
                "min": 10.0,
                "max": 14.0,
            }
        ]


@pytest.fixture()
def config():
    return AppConfig(
        device=DeviceConfig(device_id="d", local_key="k", ip="192.168.1.5")
    )


@pytest.fixture()
def fake_qs():
    return FakeQueryService()


@pytest.fixture()
def client(config, fake_qs):
    app = create_app(
        config,
        query_service=fake_qs,
        alert_provider=lambda: [
            {"param": "pm25", "severity": "warn", "active": True, "value": 40.0}
        ],
    )
    return TestClient(app)


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_parameters_endpoint_lists_all(client):
    resp = client.get("/api/parameters")
    assert resp.status_code == 200
    keys = {p["key"] for p in resp.json()}
    assert keys == set(ALL_KEYS)


def test_current(client):
    resp = client.get("/api/current")
    assert resp.status_code == 200
    body = resp.json()
    assert body["values"]["pm25"] == 12.0
    assert body["values"]["aqi"] == 51.0


def test_history_hourly(client, fake_qs):
    resp = client.get("/api/history?metric=pm25&bucket=hourly")
    assert resp.status_code == 200
    body = resp.json()
    assert body["metric"] == "pm25"
    assert body["bucket"] == "hourly"
    assert body["series"][0]["avg"] == 12.0
    # Routed to the query service with the right bucket.
    assert fake_qs.calls[0][0] == "pm25"
    assert fake_qs.calls[0][1] == "hourly"


def test_history_rejects_bad_bucket(client):
    resp = client.get("/api/history?metric=pm25&bucket=decade")
    assert resp.status_code == 400


def test_history_rejects_bad_datetime(client):
    resp = client.get("/api/history?metric=pm25&bucket=hourly&from=not-a-date")
    assert resp.status_code == 400


def test_alerts_endpoint(client):
    resp = client.get("/api/alerts")
    assert resp.status_code == 200
    active = resp.json()["active"]
    assert active[0]["param"] == "pm25"
    assert active[0]["severity"] == "warn"


def test_dashboard_renders_all_cards(client):
    resp = client.get("/")
    assert resp.status_code == 200
    html = resp.text
    # One card placeholder per parameter.
    for key in ALL_KEYS:
        assert f'id="card-{key}"' in html
        assert f'id="val-{key}"' in html
    # Chart controls present.
    assert 'id="trend-chart"' in html
    assert 'id="chart-bucket"' in html


def test_dashboard_includes_bucket_options(client):
    html = client.get("/").text
    for bucket in ("minute", "hourly", "daily", "weekly", "monthly"):
        assert f'value="{bucket}"' in html
