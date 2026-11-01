"""Tests for pure-Python bucket statistics (Tasks 5-7 math)."""

from __future__ import annotations

import math
from datetime import UTC, datetime

from aqm.stats import bucket_param, truncate_to_bucket


def _ts(y, mo, d, h=0, mi=0, s=0):
    return datetime(y, mo, d, h, mi, s, tzinfo=UTC)


def test_truncate_minute_hourly_daily():
    t = _ts(2026, 3, 15, 13, 47, 29)
    assert truncate_to_bucket(t, "minute") == _ts(2026, 3, 15, 13, 47, 0)
    assert truncate_to_bucket(t, "hourly") == _ts(2026, 3, 15, 13, 0, 0)
    assert truncate_to_bucket(t, "daily") == _ts(2026, 3, 15, 0, 0, 0)
    assert truncate_to_bucket(t, "monthly") == _ts(2026, 3, 1, 0, 0, 0)


def test_truncate_weekly_starts_monday():
    # 2026-03-15 is a Sunday; the Monday of that week is 2026-03-09.
    t = _ts(2026, 3, 15, 10, 0, 0)
    assert truncate_to_bucket(t, "weekly") == _ts(2026, 3, 9, 0, 0, 0)
    # The Monday itself stays put.
    assert truncate_to_bucket(_ts(2026, 3, 9), "weekly") == _ts(2026, 3, 9)


def test_truncate_naive_treated_as_utc():
    t = datetime(2026, 3, 15, 13, 47, 29)  # naive
    assert truncate_to_bucket(t, "hourly") == _ts(2026, 3, 15, 13, 0, 0)


def test_bucket_param_hand_calculated():
    # Two minute-buckets. Values [10, 20] and [30, 40, 50].
    readings = [
        (_ts(2026, 1, 1, 0, 0, 5), {"pm25": 10.0}),
        (_ts(2026, 1, 1, 0, 0, 55), {"pm25": 20.0}),
        (_ts(2026, 1, 1, 0, 1, 0), {"pm25": 30.0}),
        (_ts(2026, 1, 1, 0, 1, 30), {"pm25": 40.0}),
        (_ts(2026, 1, 1, 0, 1, 59), {"pm25": 50.0}),
    ]
    out = bucket_param(readings, "pm25", "minute")
    assert len(out) == 2

    b0 = out[0]
    assert b0.bucket_start == _ts(2026, 1, 1, 0, 0, 0)
    assert b0.count == 2
    assert b0.avg == 15.0
    assert b0.min == 10.0
    assert b0.max == 20.0
    # population stddev of [10,20] = 5
    assert math.isclose(b0.stddev, 5.0)

    b1 = out[1]
    assert b1.count == 3
    assert b1.avg == 40.0
    # population stddev of [30,40,50]: var = ((10^2)+(0)+(10^2))/3 = 66.666..
    assert math.isclose(b1.stddev, math.sqrt(200.0 / 3.0))


def test_bucket_param_skips_missing_parameter():
    readings = [
        (_ts(2026, 1, 1, 0, 0, 0), {"co2": 500.0}),
        (_ts(2026, 1, 1, 0, 0, 30), {"pm25": 10.0}),
    ]
    out = bucket_param(readings, "pm25", "minute")
    assert len(out) == 1
    assert out[0].count == 1
    assert out[0].avg == 10.0


def test_bucket_param_hourly_grouping():
    readings = [
        (_ts(2026, 1, 1, 0, 10), {"pm25": 1.0}),
        (_ts(2026, 1, 1, 0, 50), {"pm25": 3.0}),
        (_ts(2026, 1, 1, 1, 5), {"pm25": 10.0}),
    ]
    out = bucket_param(readings, "pm25", "hourly")
    assert [b.bucket_start.hour for b in out] == [0, 1]
    assert out[0].avg == 2.0
    assert out[1].avg == 10.0
