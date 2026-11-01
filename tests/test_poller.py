"""Tests for the poller service (Task 8)."""

from __future__ import annotations

import mongomock
import pytest

from aqm.config import AppConfig, DeviceConfig, MongoConfig
from aqm.poller import Poller
from aqm.storage import ReadingStore


class FakeDevice:
    """Mock tinytuya device: returns queued statuses or raises."""

    def __init__(self, statuses):
        self._statuses = list(statuses)
        self.calls = 0

    def status(self):
        self.calls += 1
        item = self._statuses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


@pytest.fixture()
def app_config():
    return AppConfig(
        device=DeviceConfig(
            device_id="dev-1",
            local_key="key",
            ip="192.168.1.50",
            poll_interval_seconds=0.001,
            dps_map={"2": "pm25", "18": "pm10", "21": "co2"},
            scaling={},
        ),
        mongo=MongoConfig(database="aqm_test"),
    )


@pytest.fixture()
def store():
    db = mongomock.MongoClient()["aqm_test"]
    return ReadingStore(db, MongoConfig(database="aqm_test"), device_id="dev-1")


def test_poll_once_stores_reading(app_config, store):
    device = FakeDevice([{"dps": {"2": 12.0, "18": 20.0, "21": 650}}])
    poller = Poller(app_config, store, device)
    reading = poller.poll_once()
    assert reading is not None
    assert reading.values["pm25"] == 12.0
    assert "aqi" in reading.values  # computed from pm25/pm10
    assert store.count() == 1


def test_poll_once_handles_device_error(app_config, store):
    device = FakeDevice([RuntimeError("timeout")])
    poller = Poller(app_config, store, device)
    assert poller.poll_once() is None
    assert store.count() == 0


def test_poll_once_handles_empty_dps(app_config, store):
    device = FakeDevice([{"dps": {}}])
    poller = Poller(app_config, store, device)
    assert poller.poll_once() is None
    assert store.count() == 0


def test_on_reading_callback_invoked(app_config, store):
    seen = []
    device = FakeDevice([{"dps": {"2": 12.0}}])
    poller = Poller(app_config, store, device, on_reading=seen.append)
    poller.poll_once()
    assert len(seen) == 1
    assert seen[0].values["pm25"] == 12.0


def test_callback_error_does_not_break_poll(app_config, store):
    def boom(_reading):
        raise ValueError("callback failed")

    device = FakeDevice([{"dps": {"2": 12.0}}])
    poller = Poller(app_config, store, device, on_reading=boom)
    # Reading is still stored despite callback error.
    assert poller.poll_once() is not None
    assert store.count() == 1


def test_run_forever_bounded(app_config, store):
    device = FakeDevice([{"dps": {"2": float(i)}} for i in range(3)])
    poller = Poller(app_config, store, device)
    poller.run_forever(max_iterations=3)
    assert store.count() == 3
    assert device.calls == 3
