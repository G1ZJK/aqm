"""Alerts engine.

Evaluates each reading against per-parameter thresholds (warn/critical, high
and/or low) with hysteresis to prevent flapping, and persists alert state to
MongoDB. State transitions are pure (:func:`evaluate_level`,
:class:`AlertStateMachine`) so they can be unit-tested without a database.

Severity ordering: ok < warn < critical.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from pymongo.database import Database

from .config import AlertsConfig, MongoConfig, ThresholdLevel
from .reading import Reading

logger = logging.getLogger("aqm.alerts")

OK = "ok"
WARN = "warn"
CRITICAL = "critical"
_SEVERITY_RANK = {OK: 0, WARN: 1, CRITICAL: 2}


def _raw_level(value: float, threshold: ThresholdLevel) -> str:
    """Severity from thresholds alone, ignoring hysteresis."""
    level = OK
    if threshold.warn_high is not None and value >= threshold.warn_high:
        level = WARN
    if threshold.critical_high is not None and value >= threshold.critical_high:
        level = CRITICAL
    if threshold.warn_low is not None and value <= threshold.warn_low:
        level = _max_sev(level, WARN)
    if threshold.critical_low is not None and value <= threshold.critical_low:
        level = CRITICAL
    return level


def _max_sev(a: str, b: str) -> str:
    return a if _SEVERITY_RANK[a] >= _SEVERITY_RANK[b] else b


def _clears(value: float, threshold: ThresholdLevel, level: str) -> bool:
    """True if ``value`` has retreated past ``level``'s bound by clear_margin.

    i.e. the alert at ``level`` is allowed to step down.
    """
    margin = threshold.clear_margin
    high_bound = threshold.critical_high if level == CRITICAL else threshold.warn_high
    low_bound = threshold.critical_low if level == CRITICAL else threshold.warn_low
    high_ok = high_bound is None or value < high_bound - margin
    low_ok = low_bound is None or value > low_bound + margin
    return high_ok and low_ok


def evaluate_level(
    value: float, threshold: ThresholdLevel, current: str = OK
) -> str:
    """Return the new severity for a value given a threshold and current state.

    Escalation is immediate. De-escalation applies hysteresis: the value must
    retreat past the active level's bound by ``clear_margin`` before stepping
    down, and it only steps down one level at a time per evaluation unless the
    raw level is even lower and also clears.
    """
    raw = _raw_level(value, threshold)
    if _SEVERITY_RANK[raw] >= _SEVERITY_RANK[current]:
        return raw

    # De-escalating: must clear the current level's bound.
    if current == CRITICAL:
        if not _clears(value, threshold, CRITICAL):
            return CRITICAL
        # Dropped out of critical; can we also clear warn?
        if raw == OK and not _clears(value, threshold, WARN):
            return WARN
        return raw
    if current == WARN:
        if not _clears(value, threshold, WARN):
            return WARN
        return OK
    return raw


class AlertStateMachine:
    """Tracks per-parameter alert severity in memory (pure, no I/O)."""

    def __init__(self, config: AlertsConfig):
        self._config = config
        self._state: dict[str, str] = {}

    @property
    def state(self) -> dict[str, str]:
        return dict(self._state)

    def evaluate(self, reading: Reading) -> list[dict]:
        """Evaluate a reading. Returns a list of change events.

        Each event: {param, value, old, new, ts}. Only emitted on transitions.
        """
        events: list[dict] = []
        if not self._config.enabled:
            return events
        for param, threshold in self._config.thresholds.items():
            if param not in reading.values:
                continue
            value = reading.values[param]
            current = self._state.get(param, OK)
            new = evaluate_level(value, threshold, current)
            if new != current:
                self._state[param] = new
                events.append(
                    {
                        "param": param,
                        "value": value,
                        "old": current,
                        "new": new,
                        "ts": reading.ts,
                    }
                )
        return events


class AlertManager:
    """Evaluates readings and persists active alert state to MongoDB."""

    def __init__(self, db: Database, mongo_cfg: MongoConfig, alerts_cfg: AlertsConfig):
        self._db = db
        self._cfg = mongo_cfg
        self._machine = AlertStateMachine(alerts_cfg)
        self._collection = db[mongo_cfg.alerts_collection]

    def process(self, reading: Reading) -> list[dict]:
        """Evaluate a reading and upsert alert state. Returns change events."""
        events = self._machine.evaluate(reading)
        for event in events:
            self._persist(event)
        return events

    def _persist(self, event: dict) -> None:
        param = event["param"]
        if event["new"] == OK:
            self._collection.update_one(
                {"_id": param},
                {
                    "$set": {
                        "active": False,
                        "severity": OK,
                        "value": event["value"],
                        "cleared_at": event["ts"],
                    }
                },
                upsert=True,
            )
        else:
            self._collection.update_one(
                {"_id": param},
                {
                    "$set": {
                        "active": True,
                        "severity": event["new"],
                        "value": event["value"],
                        "raised_at": event["ts"],
                    }
                },
                upsert=True,
            )

    def active_alerts(self) -> list[dict]:
        """Return currently-active alert documents."""
        docs = self._collection.find({"active": True})
        out = []
        for d in docs:
            d["param"] = d.pop("_id")
            out.append(d)
        return out

    @property
    def state(self) -> dict[str, str]:
        return self._machine.state


def now_utc() -> datetime:
    return datetime.now(UTC)
