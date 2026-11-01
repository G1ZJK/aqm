"""Scheduled rollup job: daily / weekly / monthly pre-aggregation.

Reads raw readings and writes one document per (bucket_start) into the rollup
collections, with per-parameter stats embedded. Rollups are computed with the
pure-Python :mod:`aqm.stats` engine so results are deterministic and identical
to on-demand aggregation. Upserts keyed on ``_id = bucket_start`` make re-runs
idempotent.

Document shape (rollup_daily / weekly / monthly):
    {
      "_id": <bucket_start datetime>,
      "bucket": "daily",
      "params": {
        "pm25": {"count", "avg", "stddev", "min", "max"},
        ...
      }
    }
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from pymongo import UpdateOne
from pymongo.database import Database

from .config import MongoConfig, RollupConfig
from .parameters import ALL_KEYS
from .stats import bucket_param, truncate_to_bucket

logger = logging.getLogger("aqm.rollup")

_ROLLUP_BUCKETS = ("daily", "weekly", "monthly")


class RollupJob:
    """Computes and upserts daily/weekly/monthly rollups from raw readings."""

    def __init__(self, db: Database, cfg: MongoConfig, rollup_cfg: RollupConfig | None = None):
        self._db = db
        self._cfg = cfg
        self._rollup_cfg = rollup_cfg or RollupConfig()
        self._raw = db[cfg.raw_collection]
        self._targets = {
            "daily": db[cfg.rollup_daily_collection],
            "weekly": db[cfg.rollup_weekly_collection],
            "monthly": db[cfg.rollup_monthly_collection],
        }

    def _load_readings(
        self, start: datetime, end: datetime
    ) -> list[tuple[datetime, dict[str, float]]]:
        cursor = self._raw.find({"ts": {"$gte": start, "$lt": end}}).sort("ts", 1)
        out: list[tuple[datetime, dict[str, float]]] = []
        for doc in cursor:
            ts = doc["ts"]
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=UTC)
            out.append((ts, doc.get("values", {})))
        return out

    def run_bucket(self, bucket: str, start: datetime, end: datetime) -> int:
        """Compute one bucket type over [start, end) and upsert. Returns #docs."""
        if bucket not in _ROLLUP_BUCKETS:
            raise ValueError(f"not a rollup bucket: {bucket!r}")
        readings = self._load_readings(start, end)
        if not readings:
            return 0

        # Accumulate per-parameter stats keyed by bucket_start.
        docs: dict[datetime, dict] = {}
        for param in ALL_KEYS:
            for stat in bucket_param(readings, param, bucket):
                doc = docs.setdefault(
                    stat.bucket_start,
                    {"_id": stat.bucket_start, "bucket": bucket, "params": {}},
                )
                doc["params"][param] = {
                    "count": stat.count,
                    "avg": stat.avg,
                    "stddev": stat.stddev,
                    "min": stat.min,
                    "max": stat.max,
                }

        if not docs:
            return 0

        ops = [
            UpdateOne({"_id": d["_id"]}, {"$set": d}, upsert=True) for d in docs.values()
        ]
        self._targets[bucket].bulk_write(ops, ordered=False)
        logger.info("Rollup %s: upserted %d bucket(s).", bucket, len(ops))
        return len(docs)

    def run_all(self, start: datetime, end: datetime) -> dict[str, int]:
        """Run all three rollup buckets over [start, end)."""
        return {b: self.run_bucket(b, start, end) for b in _ROLLUP_BUCKETS}

    def run_recent(self, now: datetime | None = None, days: int | None = None) -> dict[str, int]:
        """Roll up a trailing window (default: configured backfill_days).

        Window starts at the monthly bucket boundary covering the lookback so
        the current partial month/week/day are fully (re)computed.
        """
        now = now or datetime.now(UTC)
        lookback = days if days is not None else max(self._rollup_cfg.backfill_days, 1)
        raw_start = now - timedelta(days=lookback)
        start = truncate_to_bucket(raw_start, "monthly")
        return self.run_all(start, now)
