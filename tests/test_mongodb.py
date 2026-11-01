"""Tests for the MongoDB connection layer and health check (Task 2)."""

from __future__ import annotations

import pytest

from aqm.config import MongoConfig
from aqm.mongodb import (
    MIN_TIMESERIES_VERSION,
    MongoUnavailableError,
    check_health,
    evaluate_health,
    parse_version,
)


@pytest.mark.parametrize(
    "version,expected",
    [
        ("7.0.14", (7, 0, 14)),
        ("5.0.0", (5, 0, 0)),
        ("4.4.29", (4, 4, 29)),
        ("6.0.1-rc0", (6, 0, 1)),
    ],
)
def test_parse_version(version, expected):
    assert parse_version(version) == expected


def test_evaluate_health_supports_timeseries():
    report = evaluate_health({"version": "7.0.14"})
    assert report.reachable
    assert report.supports_timeseries
    assert report.version == "7.0.14"
    assert report.version_tuple >= MIN_TIMESERIES_VERSION
    assert "supported" in report.message


def test_evaluate_health_too_old():
    report = evaluate_health({"version": "4.4.29"})
    assert report.reachable
    assert not report.supports_timeseries
    assert "require" in report.message


def test_evaluate_health_missing_version():
    report = evaluate_health({})
    assert report.reachable
    assert not report.supports_timeseries
    assert report.version is None


class _FakeClient:
    """Stand-in for pymongo.MongoClient driving check_health."""

    def __init__(self, info=None, raise_exc=None):
        self._info = info or {}
        self._raise = raise_exc
        self.closed = False

    def server_info(self):
        if self._raise is not None:
            raise self._raise
        return self._info

    def close(self):
        self.closed = True


def test_check_health_with_injected_client():
    cfg = MongoConfig()
    client = _FakeClient(info={"version": "7.0.14"})
    report = check_health(cfg, client=client)
    assert report.supports_timeseries
    # Injected client is not closed by check_health (caller owns it).
    assert client.closed is False


def test_check_health_unreachable():
    from pymongo.errors import ServerSelectionTimeoutError

    cfg = MongoConfig()
    client = _FakeClient(raise_exc=ServerSelectionTimeoutError("no server"))
    with pytest.raises(MongoUnavailableError) as excinfo:
        check_health(cfg, client=client)
    assert "Could not connect" in str(excinfo.value)
