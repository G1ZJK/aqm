"""Async read services for the web layer.

Routes bucket queries to the correct source: minute/hourly are computed on
demand from the raw time-series via the aggregation pipeline; daily/weekly/
monthly are served from the pre-aggregated rollup collections.
"""

from __future__ import annotations

from datetime import datetime

from motor.motor_asyncio import AsyncIOMotorDatabase

from .aggregation import build_pipeline
from .config import MongoConfig

ON_DEMAND_BUCKETS = ("minute", "hourly")
ROLLUP_BUCKETS = ("daily", "weekly", "monthly")
ALL_BUCKETS = ON_DEMAND_BUCKETS + ROLLUP_BUCKETS


class QueryService:
    """Read-side queries backed by motor (async)."""

    def __init__(self, db: AsyncIOMotorDatabase, cfg: MongoConfig):
        self._db = db
        self._cfg = cfg
        self._rollup_collections = {
            "daily": cfg.rollup_daily_collection,
            "weekly": cfg.rollup_weekly_collection,
            "monthly": cfg.rollup_monthly_collection,
        }

    async def current(self) -> dict | None:
        """Latest raw reading as {ts, values}."""
        doc = await self._db[self._cfg.raw_collection].find_one(sort=[("ts", -1)])
        if not doc:
            return None
        return {"ts": doc["ts"], "values": doc.get("values", {})}

    async def history(
        self, param: str, bucket: str, start: datetime, end: datetime
    ) -> list[dict]:
        """Return per-bucket stats for a parameter over [start, end)."""
        if bucket not in ALL_BUCKETS:
            raise ValueError(f"unknown bucket: {bucket!r}")
        if bucket in ON_DEMAND_BUCKETS:
            return await self._history_on_demand(param, bucket, start, end)
        return await self._history_rollup(param, bucket, start, end)

    async def _history_on_demand(
        self, param: str, bucket: str, start: datetime, end: datetime
    ) -> list[dict]:
        pipeline = build_pipeline(param, bucket, start, end)
        cursor = self._db[self._cfg.raw_collection].aggregate(pipeline)
        out = []
        async for d in cursor:
            out.append(_normalize_stat(d))
        return out

    async def _history_rollup(
        self, param: str, bucket: str, start: datetime, end: datetime
    ) -> list[dict]:
        collection = self._rollup_collections[bucket]
        cursor = self._db[collection].find(
            {"_id": {"$gte": start, "$lt": end}, f"params.{param}": {"$exists": True}}
        ).sort("_id", 1)
        out = []
        async for d in cursor:
            stat = d["params"][param]
            out.append(
                {
                    "bucket_start": d["_id"],
                    "count": stat["count"],
                    "avg": stat["avg"],
                    "stddev": stat["stddev"],
                    "min": stat["min"],
                    "max": stat["max"],
                }
            )
        return out


def _normalize_stat(doc: dict) -> dict:
    return {
        "bucket_start": doc.get("bucket_start"),
        "count": doc.get("count", 0),
        "avg": doc.get("avg"),
        "stddev": doc.get("stddev"),
        "min": doc.get("min"),
        "max": doc.get("max"),
    }
