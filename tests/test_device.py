"""Tests for DPS -> parameter mapping (Task 3)."""

from __future__ import annotations

from aqm.device import map_dps_to_parameters

DPS_MAP = {
    "2": "pm25",
    "18": "pm10",
    "21": "co2",
    "25": "temperature",
    "26": "humidity",
}


def test_maps_known_ids():
    raw = {"2": 12, "18": 20, "21": 650}
    out = map_dps_to_parameters(raw, DPS_MAP)
    assert out == {"pm25": 12.0, "pm10": 20.0, "co2": 650.0}
    assert all(isinstance(v, float) for v in out.values())


def test_ignores_unmapped_ids():
    raw = {"2": 12, "99": 1, "100": "on"}
    out = map_dps_to_parameters(raw, DPS_MAP)
    assert out == {"pm25": 12.0}


def test_handles_int_keys():
    raw = {2: 12, 21: 700}
    out = map_dps_to_parameters(raw, DPS_MAP)
    assert out == {"pm25": 12.0, "co2": 700.0}


def test_parses_numeric_strings():
    raw = {"25": "231", "26": "45"}
    out = map_dps_to_parameters(raw, DPS_MAP)
    assert out == {"temperature": 231.0, "humidity": 45.0}


def test_skips_booleans_and_non_numeric():
    raw = {"2": True, "18": "not-a-number", "21": None}
    out = map_dps_to_parameters(raw, DPS_MAP)
    assert out == {}


def test_empty_payload():
    assert map_dps_to_parameters({}, DPS_MAP) == {}
