"""Tests for the alerts engine (Task 12)."""

from __future__ import annotations

from datetime import UTC, datetime

import mongomock
import pytest

from aqm.alerts import (
    CRITICAL,
    OK,
    WARN,
    AlertManager,
    AlertStateMachine,
    evaluate_level,
)
from aqm.config import AlertsConfig, MongoConfig, ThresholdLevel
from aqm.reading import Reading

HIGH = ThresholdLevel(warn_high=35.0, critical_high=55.0, clear_margin=2.0)


def test_escalation_immediate():
    assert evaluate_level(10.0, HIGH, OK) == OK
    assert evaluate_level(40.0, HIGH, OK) == WARN
    assert evaluate_level(60.0, HIGH, WARN) == CRITICAL
    assert evaluate_level(60.0, HIGH, OK) == CRITICAL


def test_hysteresis_holds_within_margin():
    # Currently WARN (bound 35, margin 2). Value 34 is within the margin band
    # (>= 33) so it should NOT clear yet.
    assert evaluate_level(34.0, HIGH, WARN) == WARN
    # Value 32 is below 35-2=33 -> clears to OK.
    assert evaluate_level(32.0, HIGH, WARN) == OK


def test_critical_steps_down_to_warn_then_ok():
    # From CRITICAL (bound 55, margin 2): value 54 within margin -> stays CRIT.
    assert evaluate_level(54.0, HIGH, CRITICAL) == CRITICAL
    # value 52 clears critical (below 53) but still above warn band -> WARN.
    assert evaluate_level(52.0, HIGH, CRITICAL) == WARN
    # value 30 clears both -> OK.
    assert evaluate_level(30.0, HIGH, CRITICAL) == OK


def test_low_side_thresholds():
    low = ThresholdLevel(warn_low=18.0, critical_low=10.0, clear_margin=1.0)
    assert evaluate_level(20.0, low, OK) == OK
    assert evaluate_level(15.0, low, OK) == WARN
    assert evaluate_level(8.0, low, WARN) == CRITICAL
    # Recover: 10.5 within critical margin (<= 11) -> stays CRITICAL.
    assert evaluate_level(10.5, low, CRITICAL) == CRITICAL
    # 12 clears critical but still <= warn_low -> WARN.
    assert evaluate_level(12.0, low, CRITICAL) == WARN
    # 20 clears all -> OK.
    assert evaluate_level(20.0, low, CRITICAL) == OK


def _reading(pm25):
    return Reading(ts=datetime(2026, 1, 1, tzinfo=UTC), values={"pm25": pm25})


def test_state_machine_emits_transitions_only():
    cfg = AlertsConfig(thresholds={"pm25": HIGH})
    sm = AlertStateMachine(cfg)
    assert sm.evaluate(_reading(10.0)) == []       # stays OK, no event
    events = sm.evaluate(_reading(40.0))           # OK -> WARN
    assert len(events) == 1
    assert events[0]["new"] == WARN and events[0]["old"] == OK
    assert sm.evaluate(_reading(41.0)) == []       # still WARN, no event
    events = sm.evaluate(_reading(60.0))           # WARN -> CRITICAL
    assert events[0]["new"] == CRITICAL


def test_state_machine_disabled():
    cfg = AlertsConfig(enabled=False, thresholds={"pm25": HIGH})
    sm = AlertStateMachine(cfg)
    assert sm.evaluate(_reading(100.0)) == []


@pytest.fixture()
def manager():
    db = mongomock.MongoClient()["aqm_test"]
    cfg = AlertsConfig(thresholds={"pm25": HIGH})
    return AlertManager(db, MongoConfig(database="aqm_test"), cfg)


def test_manager_persists_active_alert(manager):
    events = manager.process(_reading(60.0))
    assert events and events[0]["new"] == CRITICAL
    active = manager.active_alerts()
    assert len(active) == 1
    assert active[0]["param"] == "pm25"
    assert active[0]["severity"] == CRITICAL
    assert active[0]["active"] is True


def test_manager_clears_alert(manager):
    manager.process(_reading(60.0))     # raise critical
    manager.process(_reading(10.0))     # clear
    assert manager.active_alerts() == []
