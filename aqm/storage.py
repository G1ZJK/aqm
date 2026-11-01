"""MongoDB storage layer for raw readings (time-series collection).

Creates a native time-series collection (timeField=``ts``, metaField=``meta``)
with a TTL for retention, inserts normalized readings, and provides latest /
range queries. All methods use a synchronous pymongo client/database so the
poller and rollup jobs can share them; the async web layer has its own read
helpers.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from pymongo.database import Database
from pymongo.errors import CollectionInvalid

from .config import MongoConfig
from .reading import Reading

logger = logging.getLogger("aqm.storage")


class ReadingStore:
    """Raw readings persistence."""

    def __init__(self, db: Database, cfg: MongoConfig, device_id: str):
        self._db = db
        self._cfg = cfg
        self._device_id = device_id
        self._collection = db[cfg.raw_collection]

    @property
    def collection(self):
        return self._collection

    def ensure_collection(self) -> None:
        """Create the time-series collection + TTL if it does not exist.

        Idempotent: safe to call on every startup. Falls back cleanly if the
        collection already exists (as a time-series or otherwise).
        """
        name = self._cfg.raw_collection
        existing = self._db.list_collection_names()
        if name not in existing:
            try:
                self._db.create_collection(
                    name,
                    timeseries={
                        "timeField": "ts",
                        "metaField": "meta",
                        "granularity": "seconds",
                    },
                    expireAfterSeconds=self._cfg.raw_retention_seconds,
                )
                logger.info(
                    "Created time-series collection %r (TTL %ss).",
                    name,
                    self._cfg.raw_retention_seconds,
                )
            except CollectionInvalid:
                # Raced with another process; fine.
                logger.debug("Collection %r already exists.", name)
        self._collection = self._db[name]

    def insert(self, reading: Reading) -> None:
        """Insert a single normalized reading."""
        self._collection.insert_one(reading.to_storage_doc(self._device_id))

    def latest(self) -> Reading | None:
        """Return the most recent reading, or None if the store is empty."""
        doc = self._collection.find_one(sort=[("ts", -1)])
        if not doc:
            return None
        return Reading(ts=_as_utc(doc["ts"]), values=doc.get("values", {}))

    def range(self, start: datetime, end: datetime) -> list[Reading]:
        """Return readings with ``start <= ts < end`` ordered ascending."""
        cursor = self._collection.find(
            {"ts": {"$gte": start, "$lt": end}}
        ).sort("ts", 1)
        return [Reading(ts=_as_utc(d["ts"]), values=d.get("values", {})) for d in cursor]

    def count(self) -> int:
        return self._collection.count_documents({})


def _as_utc(ts: datetime) -> datetime:
    if ts.tzinfo is None:
        return ts.replace(tzinfo=UTC)
    return ts.astimezone(UTC)
