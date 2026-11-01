"""Tests for on-demand aggregation (Task 6)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from aqm.aggregation import aggregate_python, build_pipeline


def _ts(h, mi, s=0):
    return datetime(2026, 1, 1, h, mi, s, tzinfo=UTC)


def test_pipeline_structure_minute():
    start, end = _ts(0, 0), _ts(1, 0)
    pipe = build_pipeline("pm25", "minute", start, end)
    # $match restricts range and requires the field.
    match = pipe[0]["$match"]
    assert match["ts"] == {"$gte": start, "$lt": end}
    assert match["values.pm25"] == {"$exists": True}
    # $group uses $dateTrunc minute and the right accumulators.
    group = pipe[1]["$group"]
    assert group["_id"]["$dateTrunc"]["unit"] == "minute"
    assert group["avg"] == {"$avg": "$values.pm25"}
    assert group["stddev"] == {"$stdDevPop": "$values.pm25"}
    assert group["min"] == {"$min": "$values.pm25"}
    assert group["max"] == {"$max": "$values.pm25"}
    assert group["count"] == {"$sum": 1}


def test_pipeline_weekly_starts_monday():
    pipe = build_pipeline("co2", "weekly", _ts(0, 0), _ts(1, 0))
    dt = pipe[1]["$group"]["_id"]["$dateTrunc"]
    assert dt["unit"] == "week"
    assert dt["startOfWeek"] == "monday"


def test_pipeline_hourly_unit():
    pipe = build_pipeline("pm10", "hourly", _ts(0, 0), _ts(2, 0))
    assert pipe[1]["$group"]["_id"]["$dateTrunc"]["unit"] == "hour"


def test_pipeline_rejects_unknown_bucket():
    with pytest.raises(ValueError):
        build_pipeline("pm25", "fortnight", _ts(0, 0), _ts(1, 0))


def test_python_aggregation_matches_hand_calc():
    readings = [
        (_ts(0, 0, 10), {"pm25": 10.0}),
        (_ts(0, 0, 40), {"pm25": 20.0}),
        (_ts(0, 1, 0), {"pm25": 100.0}),
    ]
    out = aggregate_python(readings, "pm25", "minute")
    assert len(out) == 2
    assert out[0].avg == 15.0
    assert out[0].count == 2
    assert out[1].avg == 100.0
    assert out[1].count == 1
