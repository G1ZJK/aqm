"""Pure-Python time-bucket statistics.

This module is the authoritative, dependency-free implementation of the
per-bucket statistics (avg, population stddev, min, max, count) the app
reports. It is used:

* by tests, to assert correctness against hand-calculated values;
* by the rollup job as the computation engine (so daily/weekly/monthly
  numbers are produced deterministically and identically to on-demand math).

The on-demand MongoDB aggregation pipeline (see ``aggregation.py``) mirrors
this exact math using ``$avg`` / ``$stdDevPop`` / ``$min`` / ``$max`` / ``$sum``.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

Bucket = str  # one of VALID_BUCKETS

_WEEK_ANCHOR = datetime(2024, 1, 1, tzinfo=UTC)  # a Monday


@dataclass
class BucketStats:
    """Statistics for one parameter in one time bucket."""

    bucket_start: datetime
    count: int = 0
    avg: float = 0.0
    stddev: float = 0.0
    min: float = 0.0
    max: float = 0.0

    def as_dict(self) -> dict:
        return {
            "bucket_start": self.bucket_start,
            "count": self.count,
            "avg": self.avg,
            "stddev": self.stddev,
            "min": self.min,
            "max": self.max,
        }


@dataclass
class _Accumulator:
    values: list[float] = field(default_factory=list)


def truncate_to_bucket(ts: datetime, bucket: Bucket) -> datetime:
    """Truncate a timestamp to the start of its bucket (UTC).

    Mirrors MongoDB ``$dateTrunc`` semantics for the units we use. Weekly
    buckets start on Monday 00:00 UTC.
    """
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=UTC)
    ts = ts.astimezone(UTC)
    if bucket == "minute":
        return ts.replace(second=0, microsecond=0)
    if bucket == "hourly":
        return ts.replace(minute=0, second=0, microsecond=0)
    if bucket == "daily":
        return ts.replace(hour=0, minute=0, second=0, microsecond=0)
    if bucket == "weekly":
        day = ts.replace(hour=0, minute=0, second=0, microsecond=0)
        delta_days = (day - _WEEK_ANCHOR).days % 7
        return day - timedelta(days=delta_days)
    if bucket == "monthly":
        return ts.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    raise ValueError(f"unknown bucket: {bucket!r}")


def _finalize(bucket_start: datetime, values: list[float]) -> BucketStats:
    n = len(values)
    mean = sum(values) / n
    variance = sum((v - mean) ** 2 for v in values) / n  # population variance
    return BucketStats(
        bucket_start=bucket_start,
        count=n,
        avg=mean,
        stddev=math.sqrt(variance),
        min=min(values),
        max=max(values),
    )


def bucket_param(
    readings: Iterable[tuple[datetime, dict[str, float]]],
    param: str,
    bucket: Bucket,
) -> list[BucketStats]:
    """Compute per-bucket stats for one parameter.

    ``readings`` yields ``(timestamp, values_dict)`` pairs. Readings missing the
    requested parameter are skipped. Returns buckets sorted by start time.
    """
    acc: dict[datetime, _Accumulator] = {}
    for ts, values in readings:
        if param not in values:
            continue
        start = truncate_to_bucket(ts, bucket)
        acc.setdefault(start, _Accumulator()).values.append(float(values[param]))
    return [_finalize(start, a.values) for start, a in sorted(acc.items())]
