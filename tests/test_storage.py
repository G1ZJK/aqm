"""Tests for the raw readings storage layer (Task 5).

mongomock cannot create time-series collections, so these tests exercise the
insert/latest/range query logic against a regular mongomock collection. The
time-series creation path (``ensure_collection``) is verified live on the Pi
and guarded to be idempotent; here we confirm it does not crash when the
collection already exists.
"""

from __future__ import annotations

from datetime import UTC, datetime

import mongomock
import pytest

from aqm.config import MongoConfig
from aqm.reading import Reading
from aqm.storage import ReadingStore


@pytest.fixture()
def store():
    client = mongomock.MongoClient()
    db = client["aqm_test"]
    cfg = MongoConfig(database="aqm_test")
    return ReadingStore(db, cfg, device_id="dev-123")


def _r(minute: int, pm25: float) -> Reading:
    return Reading(
        ts=datetime(2026, 1, 1, 12, minute, 0, tzinfo=UTC),
        values={"pm25": pm25},
    )


def test_insert_and_count(store):
    assert store.count() == 0
    store.insert(_r(0, 10.0))
    store.insert(_r(1, 20.0))
    assert store.count() == 2


def test_latest_returns_most_recent(store):
    store.insert(_r(0, 10.0))
    store.insert(_r(5, 50.0))
    store.insert(_r(2, 20.0))
    latest = store.latest()
    assert latest is not None
    assert latest.values["pm25"] == 50.0
    assert latest.ts == datetime(2026, 1, 1, 12, 5, 0, tzinfo=UTC)


def test_latest_empty_is_none(store):
    assert store.latest() is None


def test_range_filters_and_orders(store):
    for m, v in [(0, 10.0), (1, 20.0), (2, 30.0), (3, 40.0)]:
        store.insert(_r(m, v))
    start = datetime(2026, 1, 1, 12, 1, 0, tzinfo=UTC)
    end = datetime(2026, 1, 1, 12, 3, 0, tzinfo=UTC)
    got = store.range(start, end)
    # [1,3) -> minutes 1 and 2
    assert [r.values["pm25"] for r in got] == [20.0, 30.0]


def test_stores_device_in_meta(store):
    store.insert(_r(0, 10.0))
    doc = store.collection.find_one({})
    assert doc["meta"]["device"] == "dev-123"


def test_ensure_collection_idempotent_when_exists(store):
    # Pre-create a regular collection to simulate "already exists".
    store.collection.insert_one(
        {"ts": datetime.now(UTC), "meta": {"device": "x"}, "values": {}}
    )
    # Should not raise even though mongomock can't do timeseries options.
    store.ensure_collection()
    assert store.count() == 1
