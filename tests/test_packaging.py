"""Smoke tests for packaging and startup wiring (Task 14)."""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

from aqm.config import load_config
from aqm.web import create_app
from tests.conftest import MINIMAL_VALID_CONFIG

ENTRY_POINTS = [
    "aqm.config_cli",
    "aqm.preflight",
    "aqm.discover",
    "aqm.poller_main",
    "aqm.rollup_main",
    "aqm.web_main",
]


@pytest.mark.parametrize("module", ENTRY_POINTS)
def test_entry_points_import_and_have_main(module):
    mod = importlib.import_module(module)
    assert hasattr(mod, "main"), f"{module} should expose main()"


def test_app_builds_from_fresh_config(write_config):
    path = write_config(MINIMAL_VALID_CONFIG)
    config = load_config(path)
    # Build the app without a live DB (query service lazily created only on use).
    app = create_app(config)
    routes = {r.path for r in app.routes}
    assert "/health" in routes
    assert "/api/current" in routes
    assert "/api/history" in routes
    assert "/api/alerts" in routes
    assert "/api/stream" in routes
    assert "/" in routes


def test_example_config_is_valid():
    example = Path(__file__).resolve().parent.parent / "config.example.yaml"
    config = load_config(example)
    # Example documents all expected sections with sane defaults.
    assert config.aqi.method in ("us_epa", "china_mee")
    assert config.mongo.raw_retention_seconds > 0
    assert "pm25" in config.alerts.thresholds


def test_systemd_units_present():
    deploy = Path(__file__).resolve().parent.parent / "deploy"
    for unit in ("aqm-poller.service", "aqm-rollup.service", "aqm-web.service"):
        assert (deploy / unit).is_file(), f"missing systemd unit {unit}"
