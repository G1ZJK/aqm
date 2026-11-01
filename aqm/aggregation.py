"""On-demand aggregation for minute/hourly buckets.

Builds the MongoDB aggregation pipeline (``$dateTrunc`` + ``$group`` with
``$avg``/``$stdDevPop``/``$min``/``$max``/``$sum``) that runs on the Pi's
MongoDB 7.0. The pipeline math is identical to :mod:`aqm.stats`, which is used
to verify correctness in tests (mongomock lacks ``$dateTrunc``).
"""

from __future__ import annotations

from datetime import datetime

from pymongo.database import Database

from .stats import BucketStats, bucket_param

# MongoDB $dateTrunc units per app bucket. 'weekly' uses startOfWeek=monday.
_BUCKET_UNIT = {
    "minute": ("minute", 1),
    "hourly": ("hour", 1),
    "daily": ("day", 1),
    "weekly": ("week", 1),
    "monthly": ("month", 1),
}


def build_pipeline(
    param: str, bucket: str, start: datetime, end: datetime
) -> list[dict]:
    """Build the aggregation pipeline for one parameter + bucket + range.

    Produces documents: {_id: bucket_start, count, avg, stddev, min, max}
    sorted ascending. Readings missing ``values.<param>`` are excluded.
    """
    if bucket not in _BUCKET_UNIT:
        raise ValueError(f"unknown bucket: {bucket!r}")
    unit, bin_size = _BUCKET_UNIT[bucket]
    field = f"$values.{param}"

    date_trunc: dict = {"date": "$ts", "unit": unit, "binSize": bin_size}
    if bucket == "weekly":
        date_trunc["startOfWeek"] = "monday"

    return [
        {"$match": {"ts": {"$gte": start, "$lt": end}, f"values.{param}": {"$exists": True}}},
        {
            "$group": {
                "_id": {"$dateTrunc": date_trunc},
                "count": {"$sum": 1},
                "avg": {"$avg": field},
                "stddev": {"$stdDevPop": field},
                "min": {"$min": field},
                "max": {"$max": field},
            }
        },
        {"$sort": {"_id": 1}},
        {
            "$project": {
                "_id": 0,
                "bucket_start": "$_id",
                "count": 1,
                "avg": 1,
                "stddev": 1,
                "min": 1,
                "max": 1,
            }
        },
    ]


def aggregate_mongo(
    db: Database,
    collection: str,
    param: str,
    bucket: str,
    start: datetime,
    end: datetime,
) -> list[dict]:
    """Run the aggregation pipeline on MongoDB and return stat documents."""
    pipeline = build_pipeline(param, bucket, start, end)
    return list(db[collection].aggregate(pipeline))


def aggregate_python(
    readings: list[tuple[datetime, dict[str, float]]],
    param: str,
    bucket: str,
) -> list[BucketStats]:
    """Compute the same buckets in pure Python (verification / fallback)."""
    return bucket_param(readings, param, bucket)
