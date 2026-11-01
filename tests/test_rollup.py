"""Tests for the scheduled rollup job (Task 7)."""

from __future__ import annotations

from datetime import UTC, datetime

import mongomock
import pytest

from aqm.config import MongoConfig
from aqm.rollup import RollupJob


@pytest.fixture()
def db():
    return mongomock.MongoClient()["aqm_test"]


@pytest.fixture()
def cfg():
    return MongoConfig(database="aqm_test")


def _seed(db, rows):
    db["readings"].insert_many(
        [{"ts": ts, "meta": {"device": "d"}, "values": vals} for ts, vals in rows]
    )


def _ts(d, h=0, mi=0):
    return datetime(2026, 1, d, h, mi, 0, tzinfo=UTC)


def test_daily_rollup_values(db, cfg):
    _seed(
        db,
        [
            (_ts(1, 0), {"pm25": 10.0, "co2": 400.0}),
            (_ts(1, 12), {"pm25": 20.0, "co2": 600.0}),
            (_ts(2, 0), {"pm25": 30.0}),
        ],
    )
    job = RollupJob(db, cfg)
    n = job.run_bucket("daily", _ts(1), _ts(3))
    assert n == 2

    day1 = db["rollup_daily"].find_one({"_id": _ts(1)})
    assert day1["bucket"] == "daily"
    assert day1["params"]["pm25"]["avg"] == 15.0
    assert day1["params"]["pm25"]["count"] == 2
    assert day1["params"]["pm25"]["min"] == 10.0
    assert day1["params"]["pm25"]["max"] == 20.0
    assert day1["params"]["co2"]["avg"] == 500.0

    day2 = db["rollup_daily"].find_one({"_id": _ts(2)})
    assert day2["params"]["pm25"]["avg"] == 30.0
    assert "co2" not in day2["params"]  # co2 absent on day 2


def test_rollup_idempotent(db, cfg):
    _seed(db, [(_ts(1, 0), {"pm25": 10.0}), (_ts(1, 12), {"pm25": 20.0})])
    job = RollupJob(db, cfg)
    job.run_bucket("daily", _ts(1), _ts(2))
    job.run_bucket("daily", _ts(1), _ts(2))  # re-run
    assert db["rollup_daily"].count_documents({}) == 1
    doc = db["rollup_daily"].find_one({"_id": _ts(1)})
    assert doc["params"]["pm25"]["avg"] == 15.0


def test_run_all_populates_three_collections(db, cfg):
    _seed(db, [(_ts(1, 0), {"pm25": 10.0}), (_ts(5, 0), {"pm25": 20.0})])
    job = RollupJob(db, cfg)
    result = job.run_all(_ts(1), _ts(8))
    assert set(result) == {"daily", "weekly", "monthly"}
    assert db["rollup_daily"].count_documents({}) == 2
    assert db["rollup_monthly"].count_documents({}) == 1  # both in January
    # Monthly avg over [10, 20] = 15.
    month = db["rollup_monthly"].find_one({})
    assert month["params"]["pm25"]["avg"] == 15.0


def test_empty_range_no_docs(db, cfg):
    job = RollupJob(db, cfg)
    assert job.run_bucket("daily", _ts(1), _ts(2)) == 0
    assert db["rollup_daily"].count_documents({}) == 0


def test_rejects_non_rollup_bucket(db, cfg):
    job = RollupJob(db, cfg)
    with pytest.raises(ValueError):
        job.run_bucket("minute", _ts(1), _ts(2))
