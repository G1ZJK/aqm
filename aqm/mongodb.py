"""MongoDB connection layer and preflight health check.

Provides factory helpers for both synchronous (``pymongo``) clients — used by
the poller and rollup jobs — and asynchronous (``motor``) clients — used by the
FastAPI web layer. A preflight check verifies connectivity and confirms the
server supports native time-series collections (MongoDB 5.0+), which the raw
readings storage layer relies on.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import MongoClient
from pymongo.errors import PyMongoError

from .config import MongoConfig

logger = logging.getLogger("aqm.mongodb")

# Native time-series collections were introduced in MongoDB 5.0.
MIN_TIMESERIES_VERSION = (5, 0)


class MongoUnavailableError(RuntimeError):
    """Raised when MongoDB cannot be reached or is otherwise unusable."""


@dataclass(frozen=True)
class HealthReport:
    """Result of a preflight MongoDB health check."""

    reachable: bool
    version: str | None
    version_tuple: tuple[int, ...]
    supports_timeseries: bool
    message: str


def parse_version(version: str) -> tuple[int, ...]:
    """Parse a MongoDB version string like '7.0.14' into a comparable tuple."""
    parts: list[int] = []
    for chunk in version.split("."):
        num = ""
        for ch in chunk:
            if ch.isdigit():
                num += ch
            else:
                break
        if num == "":
            break
        parts.append(int(num))
    return tuple(parts)


def evaluate_health(server_info: dict) -> HealthReport:
    """Build a :class:`HealthReport` from a server ``buildInfo`` document.

    Separated from I/O so it can be unit-tested with a mocked ``server_info``.
    """
    version = server_info.get("version")
    if not version:
        return HealthReport(
            reachable=True,
            version=None,
            version_tuple=(),
            supports_timeseries=False,
            message="Connected, but server did not report a version.",
        )
    vt = parse_version(version)
    supports = vt >= MIN_TIMESERIES_VERSION
    if supports:
        message = f"MongoDB {version}: reachable, time-series collections supported."
    else:
        message = (
            f"MongoDB {version}: reachable, but time-series collections require "
            f">= {'.'.join(str(p) for p in MIN_TIMESERIES_VERSION)}. "
            "Install MongoDB 7.0 (official ARM64 on Raspberry Pi OS 64-bit)."
        )
    return HealthReport(
        reachable=True,
        version=version,
        version_tuple=vt,
        supports_timeseries=supports,
        message=message,
    )


def make_sync_client(cfg: MongoConfig) -> MongoClient:
    """Create a synchronous pymongo client (used by poller/rollup)."""
    return MongoClient(
        cfg.uri,
        serverSelectionTimeoutMS=cfg.server_selection_timeout_ms,
        tz_aware=True,
    )


def make_async_client(cfg: MongoConfig) -> AsyncIOMotorClient:
    """Create an asynchronous motor client (used by FastAPI)."""
    return AsyncIOMotorClient(
        cfg.uri,
        serverSelectionTimeoutMS=cfg.server_selection_timeout_ms,
        tz_aware=True,
    )


def check_health(cfg: MongoConfig, *, client: MongoClient | None = None) -> HealthReport:
    """Perform a preflight connectivity + capability check.

    Raises :class:`MongoUnavailableError` if the server cannot be reached.
    """
    owns_client = client is None
    client = client or make_sync_client(cfg)
    try:
        info = client.server_info()  # forces a connection, raises if unreachable
    except PyMongoError as exc:
        raise MongoUnavailableError(
            f"Could not connect to MongoDB at {cfg.uri}: {exc}. "
            "Is mongod running? On the Pi: 'sudo systemctl status mongod'."
        ) from exc
    finally:
        if owns_client:
            client.close()
    return evaluate_health(info)


def require_healthy(cfg: MongoConfig) -> HealthReport:
    """Check health and raise if time-series is unsupported. Returns the report."""
    report = check_health(cfg)
    if not report.supports_timeseries:
        raise MongoUnavailableError(report.message)
    logger.info(report.message)
    return report
